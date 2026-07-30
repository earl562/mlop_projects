from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import Field

from plotlot.harness.contracts import (
    ApprovalId,
    ApprovalRequest,
    ApprovalStatus,
    JsonObject,
    PlotLotEvent,
    PlotLotEventSource,
    PlotLotEventStatus,
    PlotLotEventType,
    RiskLevel,
    RunId,
)
from plotlot.harness.contracts.base import HarnessContract, utc_now

APPROVAL_STORE_PATH_ENV = "PLOTLOT_HARNESS_APPROVAL_STORE_PATH"


@dataclass(frozen=True, slots=True)
class ApprovalNotFoundError(Exception):
    approval_id: ApprovalId

    def __str__(self) -> str:
        return f"Approval not found: {self.approval_id}"


@dataclass(frozen=True, slots=True)
class ApprovalAlreadyResolvedError(Exception):
    approval_id: ApprovalId
    status: ApprovalStatus

    def __str__(self) -> str:
        return f"Approval is already {self.status.value}: {self.approval_id}"


@dataclass(frozen=True, slots=True)
class InvalidApprovalDecisionError(Exception):
    decision: ApprovalStatus

    def __str__(self) -> str:
        return f"Invalid approval decision: {self.decision.value}"


class ApprovalLedgerSnapshot(HarnessContract):
    approvals: dict[str, ApprovalRequest] = Field(default_factory=dict)
    events_by_run: dict[str, list[PlotLotEvent]] = Field(default_factory=dict)


class LocalApprovalLedger:
    def __init__(self, path: Path) -> None:
        self._path = path

    def request_approval(
        self,
        *,
        run_id: RunId,
        requested_action: str,
        risk_level: RiskLevel,
        reason: str,
        source: PlotLotEventSource,
        approval_id: ApprovalId | None = None,
        policy_ids: list[str] | None = None,
        request_payload: JsonObject | None = None,
    ) -> ApprovalRequest:
        snapshot = self._read_snapshot()
        selected_id = approval_id or self._next_approval_id(snapshot, run_id, requested_action)
        approval = ApprovalRequest(
            approval_id=selected_id,
            run_id=run_id,
            requested_action=requested_action,
            risk_level=risk_level,
            reason=reason,
            policy_ids=policy_ids or [],
            request_payload=request_payload or {},
        )
        approvals = dict(snapshot.approvals)
        approvals[str(selected_id)] = approval
        updated = self._append_event(
            snapshot.model_copy(update={"approvals": approvals}),
            run_id=run_id,
            event_type=PlotLotEventType.APPROVAL_REQUESTED,
            source=source,
            payload=self._approval_payload(approval),
        )
        self._write_snapshot(updated)
        return approval

    def get_approval(self, approval_id: ApprovalId) -> ApprovalRequest:
        snapshot = self._read_snapshot()
        approval = snapshot.approvals.get(str(approval_id))
        if approval is None:
            raise ApprovalNotFoundError(approval_id=approval_id)
        return approval

    def list_approvals(
        self,
        *,
        run_id: RunId | None = None,
        status: ApprovalStatus | None = None,
    ) -> list[ApprovalRequest]:
        snapshot = self._read_snapshot()
        approvals = sorted(
            snapshot.approvals.values(),
            key=lambda approval: (approval.requested_at, str(approval.approval_id)),
        )
        if run_id is not None:
            approvals = [approval for approval in approvals if approval.run_id == run_id]
        if status is not None:
            approvals = [approval for approval in approvals if approval.status == status]
        return approvals

    def resolve_approval(
        self,
        approval_id: ApprovalId,
        *,
        decision: ApprovalStatus,
        resolved_by: str | None = None,
        response_payload: JsonObject | None = None,
        source: PlotLotEventSource = PlotLotEventSource.SYSTEM,
    ) -> ApprovalRequest:
        if decision not in {ApprovalStatus.APPROVED, ApprovalStatus.DENIED}:
            raise InvalidApprovalDecisionError(decision=decision)
        snapshot = self._read_snapshot()
        approval = snapshot.approvals.get(str(approval_id))
        if approval is None:
            raise ApprovalNotFoundError(approval_id=approval_id)
        if approval.status != ApprovalStatus.PENDING:
            raise ApprovalAlreadyResolvedError(approval_id=approval_id, status=approval.status)
        resolved = approval.model_copy(
            update={
                "status": decision,
                "resolved_by": resolved_by,
                "resolved_at": utc_now(),
                "response_payload": response_payload or {},
            }
        )
        approvals = dict(snapshot.approvals)
        approvals[str(approval_id)] = resolved
        updated = self._append_event(
            snapshot.model_copy(update={"approvals": approvals}),
            run_id=resolved.run_id,
            event_type=(
                PlotLotEventType.APPROVAL_GRANTED
                if decision == ApprovalStatus.APPROVED
                else PlotLotEventType.APPROVAL_DENIED
            ),
            source=source,
            payload=self._approval_payload(resolved),
        )
        self._write_snapshot(updated)
        return resolved

    def list_events(self, run_id: RunId) -> list[PlotLotEvent]:
        snapshot = self._read_snapshot()
        return list(snapshot.events_by_run.get(str(run_id), []))

    def _append_event(
        self,
        snapshot: ApprovalLedgerSnapshot,
        *,
        run_id: RunId,
        event_type: PlotLotEventType,
        source: PlotLotEventSource,
        payload: JsonObject,
    ) -> ApprovalLedgerSnapshot:
        events_by_run = {key: list(value) for key, value in snapshot.events_by_run.items()}
        run_events = events_by_run.setdefault(str(run_id), [])
        run_events.append(
            PlotLotEvent(
                run_id=run_id,
                sequence=len(run_events) + 1,
                type=event_type,
                payload=payload,
                source=source,
                status=PlotLotEventStatus.COMPLETED,
            )
        )
        return snapshot.model_copy(update={"events_by_run": events_by_run})

    def _read_snapshot(self) -> ApprovalLedgerSnapshot:
        if not self._path.exists():
            return ApprovalLedgerSnapshot()
        raw = self._path.read_text(encoding="utf-8")
        if not raw.strip():
            return ApprovalLedgerSnapshot()
        return ApprovalLedgerSnapshot.model_validate_json(raw)

    def _write_snapshot(self, snapshot: ApprovalLedgerSnapshot) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")

    def _next_approval_id(
        self,
        snapshot: ApprovalLedgerSnapshot,
        run_id: RunId,
        requested_action: str,
    ) -> ApprovalId:
        base = f"apr_{run_id}_{self._slug(requested_action)}"
        if base not in snapshot.approvals:
            return ApprovalId(base)
        index = 2
        while f"{base}_{index}" in snapshot.approvals:
            index += 1
        return ApprovalId(f"{base}_{index}")

    @staticmethod
    def _slug(value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
        return slug or "approval"

    @staticmethod
    def _approval_payload(approval: ApprovalRequest) -> JsonObject:
        return {
            "approval_id": str(approval.approval_id),
            "requested_action": approval.requested_action,
            "risk_level": approval.risk_level.value,
            "status": approval.status.value,
        }


def default_approval_ledger_path() -> Path:
    configured = os.environ.get(APPROVAL_STORE_PATH_ENV)
    if configured:
        return Path(configured).expanduser()
    state_home = os.environ.get("XDG_STATE_HOME")
    base = Path(state_home).expanduser() if state_home else Path.home() / ".local" / "state"
    return base / "plotlot" / "harness-approvals.json"


def default_approval_ledger() -> LocalApprovalLedger:
    return LocalApprovalLedger(default_approval_ledger_path())
