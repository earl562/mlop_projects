"""Tool discovery + governed tool execution (REST surface).

This is the REST equivalent of the MCP adapter: it exposes a stable contract for
listing tools and calling tools, while ensuring calls route through harness
policy and are durably audited.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request

from plotlot.api.recorded_evidence_context import recorded_evidence_ids
from plotlot.api.tool_artifact_persistence import (
    ToolArtifactContext,
    persist_tool_artifacts,
)
from plotlot.api.tool_approval_validation import validated_approved_ids
from plotlot.api.tool_call_models import ToolCallRequest, ToolCallResponse, actor_user_id
from plotlot.api.tool_run_trace import event_dicts, tool_run_output_json
from plotlot.harness.default_runtime import get_default_runtime
from plotlot.harness.report_artifacts import requested_document_evidence_ids
from plotlot.harness.tool_registry import list_tool_contracts, tool_risk_class
from plotlot.harness.events import HarnessEvent
from plotlot.land_use.evidence import persist_land_use_evidence
from plotlot.land_use.models import EvidenceItem as LandUseEvidenceItem
from plotlot.land_use.models import ToolContext
from plotlot.storage.db import get_session
from plotlot.storage.models import (
    ApprovalRequest,
    Project,
    ToolRun,
    Workspace,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


async def _ensure_workspace(session, workspace_id: str, owner_user_id: str | None) -> None:
    existing = await session.get(Workspace, workspace_id)
    if existing is None:
        session.add(
            Workspace(
                id=workspace_id,
                name="Default Workspace",
                owner_user_id=owner_user_id,
            )
        )
        await session.flush()


def _default_project_id(workspace_id: str) -> str:
    # Deterministic, stable per workspace, and always 36 chars.
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"plotlot:{workspace_id}:default_project"))


async def _ensure_project(session, *, workspace_id: str, project_id: str | None) -> str:
    pid = project_id or _default_project_id(workspace_id)
    existing = await session.get(Project, pid)
    if existing is None:
        session.add(
            Project(
                id=pid,
                workspace_id=workspace_id,
                name="Default Project",
                description="Auto-created for tool runs without an explicit project.",
            )
        )
        await session.flush()
    return pid


@router.get("")
async def list_tools() -> list[dict[str, Any]]:
    runtime = get_default_runtime()
    return [tool.model_dump() for tool in list_tool_contracts() if runtime.has_handler(tool.name)]


@router.post("/call", response_model=ToolCallResponse)
async def call_tool(req: ToolCallRequest, http_request: Request):
    runtime = get_default_runtime()

    run_id = req.run_id or str(uuid.uuid4())
    actor_user = actor_user_id(http_request)
    claimed_approvals = set(req.approved_approval_ids or [])

    # Only treat approvals as valid if the DB says so (fail-closed).
    risk_class = tool_risk_class(req.tool_name)
    validated = claimed_approvals
    if risk_class in {"write_external", "execution", "write_internal", "expensive_read"}:
        validated = await validated_approved_ids(
            approval_ids=claimed_approvals,
            workspace_id=req.workspace_id,
        )

    session = await get_session()
    tool_run = None
    try:
        await _ensure_workspace(
            session,
            req.workspace_id,
            owner_user_id=actor_user if actor_user != "anonymous" else None,
        )

        project_id = await _ensure_project(
            session,
            workspace_id=req.workspace_id,
            project_id=req.project_id,
        )

        tool_run = ToolRun(
            id=str(uuid.uuid4()),
            workspace_id=req.workspace_id,
            project_id=project_id,
            site_id=req.site_id,
            analysis_id=req.analysis_id,
            analysis_run_id=req.analysis_run_id,
            tool_name=req.tool_name,
            risk_class=risk_class,
            status="running",
            input_json=req.arguments,
            output_json={},
            started_at=datetime.now(timezone.utc),
        )
        session.add(tool_run)
        await session.flush()
        recorded_ids = await recorded_evidence_ids(
            session,
            requested_document_evidence_ids(req.arguments)
            if req.tool_name == "generate_document"
            else (),
        )

        context = ToolContext(
            workspace_id=req.workspace_id,
            actor_user_id=actor_user,
            run_id=run_id,
            tool_run_id=str(tool_run.id),
            project_id=project_id,
            site_id=req.site_id,
            analysis_id=req.analysis_id,
            analysis_run_id=req.analysis_run_id,
            risk_budget_cents=req.risk_budget_cents,
            live_network_allowed=req.live_network_allowed,
            approved_approval_ids=validated,
            recorded_evidence_ids=recorded_ids,
        )

        event_buffer: list[HarnessEvent] = []
        call_result = await runtime.call_tool(
            tool_name=req.tool_name,
            tool_args=req.arguments,
            context=context,
            approval_id=req.approval_id,
            events=event_buffer,
        )

        evidence_ids: list[str] = []
        artifact_ids: dict[str, str] = {}
        result_payload: dict[str, Any] | None = call_result.result
        persisted_payload = result_payload
        response_status = call_result.status
        response_message = call_result.message

        match call_result.status:  # noqa: E501  # noqa: MATCH_OK
            case "pending_approval":
                setattr(tool_run, "status", "pending_approval")
                persisted_payload = {
                    "status": "pending_approval",
                    "approval_id": call_result.decision.approval_id,
                    "reason": call_result.decision.reason,
                }
                approval = ApprovalRequest(
                    id=call_result.decision.approval_id or f"apr_{run_id}_{req.tool_name}",
                    workspace_id=req.workspace_id,
                    project_id=project_id,
                    analysis_run_id=req.analysis_run_id,
                    tool_run_id=tool_run.id,
                    status="pending",
                    risk_class=risk_class,
                    action_name=req.tool_name,
                    reason=call_result.decision.reason,
                    request_json={"tool": req.tool_name, "args": req.arguments, "run_id": run_id},
                    response_json={},
                    requested_by=actor_user,
                )
                session.add(approval)
            case "ok":
                setattr(tool_run, "status", "ok")

                evidence_payloads: list[Any] = []
                if isinstance(result_payload, dict):
                    evidence_payloads = result_payload.get("evidence", []) or []

                    for raw in evidence_payloads:
                        evidence = LandUseEvidenceItem.model_validate(raw)
                        await persist_land_use_evidence(session, evidence=evidence)
                        evidence_ids.append(evidence.id)

                    artifact_result = await persist_tool_artifacts(
                        session,
                        result_payload,
                        ToolArtifactContext(
                            workspace_id=req.workspace_id,
                            project_id=project_id,
                            site_id=req.site_id,
                            analysis_run_id=req.analysis_run_id,
                        ),
                    )
                    artifact_ids = artifact_result.artifact_ids
                    result_payload = artifact_result.result_payload
                    persisted_payload = result_payload
                    if artifact_result.status == "blocked":
                        response_status = "blocked"
                        response_message = artifact_result.message
                        setattr(tool_run, "status", "blocked")
                        setattr(tool_run, "error_message", response_message)
            case _:
                setattr(tool_run, "status", call_result.status)
                setattr(tool_run, "error_message", call_result.message)

        setattr(
            tool_run,
            "output_json",
            tool_run_output_json(
                run_id=run_id,
                tool_run_id=str(tool_run.id),
                status=response_status,
                decision=call_result.decision,
                result_payload=persisted_payload,
                message=response_message,
                evidence_ids=evidence_ids,
                artifact_ids=artifact_ids,
                events=event_buffer,
            ),
        )
        setattr(tool_run, "completed_at", datetime.now(timezone.utc))
        await session.commit()

        return ToolCallResponse(
            run_id=run_id,
            tool_run_id=str(tool_run.id),
            tool_name=call_result.tool_name,
            status=response_status,
            decision=call_result.decision.model_dump(),
            result=result_payload,
            message=response_message,
            evidence_ids=evidence_ids,
            artifact_ids=artifact_ids,
            events=event_dicts(event_buffer),
        )
    except Exception:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK
        try:
            await session.rollback()
        except Exception:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK
            logger.warning("Rollback failed", exc_info=True)
        raise
    finally:
        await session.close()
