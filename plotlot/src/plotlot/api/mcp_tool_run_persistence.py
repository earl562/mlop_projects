from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.api.tool_artifact_persistence import (
    ToolArtifactContext,
    persist_tool_artifacts,
)
from plotlot.api.tool_run_trace import tool_run_output_json
from plotlot.api.tools import _ensure_project, _ensure_workspace
from plotlot.harness.events import HarnessEvent
from plotlot.land_use.evidence import persist_land_use_evidence
from plotlot.land_use.models import EvidenceItem as LandUseEvidenceItem
from plotlot.land_use.models import PolicyDecision, ToolContext
from plotlot.storage.models import ToolRun


@dataclass(frozen=True, slots=True)
class McpToolRunStartRequest:
    tool_name: str
    arguments: dict[str, Any]
    risk_class: str
    context: ToolContext


@dataclass(frozen=True, slots=True)
class McpToolRunStart:
    tool_run: ToolRun
    context: ToolContext


@dataclass(frozen=True, slots=True)
class McpPersistedResult:
    status: str
    message: str | None
    result_payload: dict[str, Any] | None
    evidence_ids: list[str]
    artifact_ids: dict[str, str]


@dataclass(frozen=True, slots=True)
class McpToolRunCompletion:
    run_id: str
    status: str
    decision: PolicyDecision
    result_payload: dict[str, Any] | None
    message: str | None
    evidence_ids: list[str]
    artifact_ids: dict[str, str]
    events: list[HarnessEvent]


def requires_mcp_persistence(result_payload: dict[str, Any] | None) -> bool:
    if result_payload is None:
        return False
    return bool(
        result_payload.get("evidence")
        or result_payload.get("evidence_ids")
        or result_payload.get("evidence_packets")
        or result_payload.get("artifacts")
    )


async def start_mcp_tool_run(
    session: AsyncSession,
    request: McpToolRunStartRequest,
) -> McpToolRunStart:
    await _ensure_workspace(
        session,
        request.context.workspace_id,
        owner_user_id=(
            request.context.actor_user_id if request.context.actor_user_id != "anonymous" else None
        ),
    )
    project_id = await _ensure_project(
        session,
        workspace_id=request.context.workspace_id,
        project_id=request.context.project_id,
    )
    tool_run_id = str(uuid4())
    context = request.context.model_copy(
        update={"project_id": project_id, "tool_run_id": tool_run_id}
    )
    tool_run = ToolRun(
        id=tool_run_id,
        workspace_id=context.workspace_id,
        project_id=project_id,
        site_id=context.site_id,
        analysis_id=context.analysis_id,
        analysis_run_id=context.analysis_run_id,
        tool_name=request.tool_name,
        risk_class=request.risk_class,
        status="running",
        input_json=request.arguments,
        output_json={},
        started_at=datetime.now(timezone.utc),
    )
    session.add(tool_run)
    await session.flush()
    return McpToolRunStart(tool_run=tool_run, context=context)


async def persist_mcp_result(
    session: AsyncSession,
    *,
    result_payload: dict[str, Any],
    context: ToolContext,
) -> McpPersistedResult:
    evidence_ids: list[str] = []
    for raw in result_payload.get("evidence", []) or []:
        evidence = LandUseEvidenceItem.model_validate(raw)
        await persist_land_use_evidence(session, evidence=evidence)
        evidence_ids.append(evidence.id)
    evidence_ids.extend(
        evidence_id
        for evidence_id in _payload_evidence_ids(result_payload)
        if evidence_id not in evidence_ids
    )

    artifact_result = await persist_tool_artifacts(
        session,
        result_payload,
        ToolArtifactContext(
            workspace_id=context.workspace_id,
            project_id=context.project_id or "",
            site_id=context.site_id,
            analysis_run_id=context.analysis_run_id,
        ),
    )
    if artifact_result.status == "blocked":
        return McpPersistedResult(
            status="blocked",
            message=artifact_result.message,
            result_payload=artifact_result.result_payload,
            evidence_ids=evidence_ids,
            artifact_ids=artifact_result.artifact_ids,
        )
    return McpPersistedResult(
        status="ok",
        message=None,
        result_payload=artifact_result.result_payload,
        evidence_ids=evidence_ids,
        artifact_ids=artifact_result.artifact_ids,
    )


def _payload_evidence_ids(result_payload: Mapping[str, Any]) -> list[str]:
    evidence_ids: list[str] = []
    raw_ids = result_payload.get("evidence_ids") or ()
    if isinstance(raw_ids, (list, tuple)):
        for raw_evidence_id in raw_ids:
            if not isinstance(raw_evidence_id, str):
                continue
            evidence_id = raw_evidence_id.strip()
            if evidence_id and evidence_id not in evidence_ids:
                evidence_ids.append(evidence_id)

    packets = result_payload.get("evidence_packets") or ()
    if not isinstance(packets, (list, tuple)):
        return evidence_ids
    for raw_packet in packets:
        if not isinstance(raw_packet, Mapping):
            continue
        raw_evidence_id = raw_packet.get("evidence_id")
        if not isinstance(raw_evidence_id, str):
            continue
        evidence_id = raw_evidence_id.strip()
        if evidence_id and evidence_id not in evidence_ids:
            evidence_ids.append(evidence_id)
    return evidence_ids


def complete_mcp_tool_run(
    tool_run: ToolRun,
    completion: McpToolRunCompletion,
) -> None:
    setattr(tool_run, "status", completion.status)
    if completion.status not in {"ok", "pending_approval"}:
        setattr(tool_run, "error_message", completion.message)
    setattr(
        tool_run,
        "output_json",
        tool_run_output_json(
            run_id=completion.run_id,
            tool_run_id=str(tool_run.id),
            status=completion.status,
            decision=completion.decision,
            result_payload=completion.result_payload,
            message=completion.message,
            evidence_ids=completion.evidence_ids,
            artifact_ids=completion.artifact_ids,
            events=completion.events,
        ),
    )
    setattr(tool_run, "completed_at", datetime.now(timezone.utc))
