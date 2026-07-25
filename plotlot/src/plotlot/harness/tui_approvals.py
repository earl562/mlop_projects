from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import assert_never

from plotlot.harness.approval_store import LocalApprovalLedger
from plotlot.harness.contracts import (
    ApprovalId,
    ApprovalStatus,
    PlotLotEventSource,
    RunId,
)
from plotlot.harness.contracts.base import HarnessContract
from plotlot.harness.tui import TuiPanel, TuiRenderRequest, TuiScreen, TuiScreenName


class TuiApprovalAction(StrEnum):
    LIST = "list"
    APPROVE = "approve"
    DENY = "deny"


class TuiApprovalRequest(HarnessContract):
    action: TuiApprovalAction = TuiApprovalAction.LIST
    run_id: RunId | None = None
    approval_id: ApprovalId | None = None
    resolved_by: str | None = None


@dataclass(frozen=True, slots=True)
class TuiApprovalRunRequiredError(Exception):
    def __str__(self) -> str:
        return "TUI approval listing requires --run-id"


@dataclass(frozen=True, slots=True)
class TuiApprovalIdRequiredError(Exception):
    action: TuiApprovalAction

    def __str__(self) -> str:
        return f"TUI approval action {self.action.value!r} requires an approval ID"


def render_tui_approval_screen(
    request: TuiApprovalRequest,
    ledger: LocalApprovalLedger,
) -> TuiScreen:
    match request.action:
        case TuiApprovalAction.LIST:
            return _approval_list_screen(request, ledger)
        case TuiApprovalAction.APPROVE:
            return _approval_decision_screen(request, ledger, ApprovalStatus.APPROVED)
        case TuiApprovalAction.DENY:
            return _approval_decision_screen(request, ledger, ApprovalStatus.DENIED)
        case unreachable:
            assert_never(unreachable)


def approval_list_screen(request: TuiRenderRequest, ledger: LocalApprovalLedger) -> TuiScreen:
    run_id = request.required_run_id()
    return _approval_list_for_run(run_id, ledger)


def _approval_list_screen(request: TuiApprovalRequest, ledger: LocalApprovalLedger) -> TuiScreen:
    run_id = _required_run_id(request)
    return _approval_list_for_run(run_id, ledger)


def _approval_list_for_run(run_id: RunId, ledger: LocalApprovalLedger) -> TuiScreen:
    approvals = ledger.list_approvals(run_id=run_id)
    events = ledger.list_events(run_id)
    return TuiScreen(
        screen=TuiScreenName.APPROVALS,
        title="Approvals",
        summary={
            "run_id": str(run_id),
            "approval_count": len(approvals),
            "event_count": len(events),
        },
        panels=[
            TuiPanel(title="Approval Requests", items=[item.model_dump(mode="json") for item in approvals]),
            TuiPanel(title="Approval Events", items=[item.model_dump(mode="json") for item in events]),
        ],
    )


def _approval_decision_screen(
    request: TuiApprovalRequest,
    ledger: LocalApprovalLedger,
    decision: ApprovalStatus,
) -> TuiScreen:
    approval_id = _required_approval_id(request)
    resolved = ledger.resolve_approval(
        approval_id,
        decision=decision,
        resolved_by=request.resolved_by,
        source=PlotLotEventSource.TUI,
    )
    events = ledger.list_events(resolved.run_id)
    return TuiScreen(
        screen=TuiScreenName.APPROVALS,
        title="Approvals",
        summary={
            "run_id": str(resolved.run_id),
            "approval_id": str(resolved.approval_id),
            "decision": resolved.status.value,
            "event_count": len(events),
        },
        panels=[
            TuiPanel(title="Approval Requests", items=[resolved.model_dump(mode="json")]),
            TuiPanel(title="Approval Events", items=[item.model_dump(mode="json") for item in events]),
        ],
    )


def _required_run_id(request: TuiApprovalRequest) -> RunId:
    if request.run_id is None:
        raise TuiApprovalRunRequiredError()
    return request.run_id


def _required_approval_id(request: TuiApprovalRequest) -> ApprovalId:
    if request.approval_id is None:
        raise TuiApprovalIdRequiredError(action=request.action)
    return request.approval_id
