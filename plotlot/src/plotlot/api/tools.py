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
from pydantic import BaseModel, Field

from plotlot.domain.types import ToolContext as FullHarnessToolContext
from plotlot.harness.contracts import ExecutionMode, SourceMode
from plotlot.harness.default_runtime import get_default_runtime
from plotlot.harness.full_harness_registry import RegistryLookupError, get_tool_spec
from plotlot.harness.run_store import HarnessRunNotFoundError, default_harness_run_store
from plotlot.harness.tool_registry import list_tool_contracts, tool_risk_class
from plotlot.harness.tool_call_store import default_tool_call_ledger, tool_call_from_result
from plotlot.harness.tool_router import HarnessToolCallRequest, default_tool_router
from plotlot.harness.web_lookup import enrich_web_search_payload
from plotlot.harness.events import HarnessEvent
from plotlot.land_use.evidence import persist_land_use_evidence
from plotlot.land_use.models import EvidenceItem as LandUseEvidenceItem
from plotlot.land_use.models import ToolContext
from plotlot.storage.db import get_session
from plotlot.storage.models import (
    ApprovalRequest,
    Document,
    Project,
    Report,
    ToolRun,
    Workspace,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


def _actor_user_id(http_request: Request) -> str:
    user = getattr(http_request.state, "user", None)
    if isinstance(user, dict) and user.get("user_id"):
        return str(user["user_id"])
    return "anonymous"


class ToolCallRequest(BaseModel):
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)

    workspace_id: str = Field(default="default-workspace", min_length=1)
    project_id: str | None = Field(default=None, max_length=36)
    site_id: str | None = Field(default=None, max_length=36)
    analysis_id: str | None = Field(default=None, max_length=36)
    analysis_run_id: str | None = Field(default=None, max_length=36)

    run_id: str | None = Field(
        default=None,
        description="Optional caller-provided run ID to group multiple tool calls.",
    )
    risk_budget_cents: int = Field(default=0, ge=0)
    live_network_allowed: bool = False
    approved_approval_ids: list[str] = Field(default_factory=list)
    approval_id: str | None = None
    source_mode: SourceMode = SourceMode.FIXTURE


class ToolCallResponse(BaseModel):
    run_id: str
    tool_run_id: str
    tool_name: str
    status: str
    decision: dict[str, Any]
    result: dict[str, Any] | None = None
    message: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_ids: dict[str, str] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)
    source_mode: str | None = None


async def _validated_approved_ids(
    *,
    approval_ids: set[str],
    workspace_id: str,
) -> set[str]:
    """Return subset actually approved in DB; fail-closed on DB errors."""

    if not approval_ids:
        return set()

    session = await get_session()
    try:
        now = datetime.now(timezone.utc)
        approved: set[str] = set()
        for approval_id in approval_ids:
            row = await session.get(ApprovalRequest, approval_id)
            if (
                row
                and row.workspace_id == workspace_id
                and row.status == "approved"
                and (row.expires_at is None or row.expires_at > now)
            ):
                approved.add(approval_id)
        return approved
    except Exception:
        logger.warning("Approval validation failed; failing closed", exc_info=True)
        return set()
    finally:
        await session.close()


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


async def _upsert_pending_approval(
    session,
    *,
    approval_id: str,
    workspace_id: str,
    project_id: str,
    analysis_run_id: str | None,
    tool_run_id: str,
    risk_class: str,
    action_name: str,
    reason: str,
    request_json: dict[str, Any],
    requested_by: str,
) -> None:
    existing = await session.get(ApprovalRequest, approval_id)
    if existing is not None:
        existing.workspace_id = workspace_id
        existing.project_id = project_id
        existing.analysis_run_id = analysis_run_id
        existing.tool_run_id = tool_run_id
        existing.status = "pending"
        existing.risk_class = risk_class
        existing.action_name = action_name
        existing.reason = reason
        existing.request_json = request_json
        existing.response_json = {}
        existing.requested_by = requested_by
        return

    session.add(
        ApprovalRequest(
            id=approval_id,
            workspace_id=workspace_id,
            project_id=project_id,
            analysis_run_id=analysis_run_id,
            tool_run_id=tool_run_id,
            status="pending",
            risk_class=risk_class,
            action_name=action_name,
            reason=reason,
            request_json=request_json,
            response_json={},
            requested_by=requested_by,
        )
    )


@router.get("")
async def list_tools() -> list[dict[str, Any]]:
    runtime = get_default_runtime()
    return [tool.model_dump() for tool in list_tool_contracts() if runtime.has_handler(tool.name)]


@router.post("/call", response_model=ToolCallResponse)
async def call_tool(req: ToolCallRequest, http_request: Request):
    runtime = get_default_runtime()

    run_id = req.run_id or str(uuid.uuid4())
    actor_user_id = _actor_user_id(http_request)
    claimed_approvals = set(req.approved_approval_ids or [])

    # Only treat approvals as valid if the DB says so (fail-closed).
    risk_class = tool_risk_class(req.tool_name)
    validated = claimed_approvals
    if risk_class in {"write_external", "execution", "write_internal", "expensive_read"}:
        validated = await _validated_approved_ids(
            approval_ids=claimed_approvals,
            workspace_id=req.workspace_id,
        )

    session = await get_session()
    tool_run = None
    try:
        await _ensure_workspace(
            session,
            req.workspace_id,
            owner_user_id=actor_user_id if actor_user_id != "anonymous" else None,
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

        context = ToolContext(
            workspace_id=req.workspace_id,
            actor_user_id=actor_user_id,
            run_id=run_id,
            tool_run_id=str(tool_run.id),
            project_id=project_id,
            site_id=req.site_id,
            analysis_id=req.analysis_id,
            analysis_run_id=req.analysis_run_id,
            risk_budget_cents=req.risk_budget_cents,
            live_network_allowed=req.live_network_allowed,
            approved_approval_ids=validated,
        )

        if _is_full_harness_tool(req.tool_name):
            response = await _call_full_harness_tool(
                req=req,
                context=context,
                source_mode=req.source_mode,
            )
            response.tool_run_id = str(tool_run.id)
            if response.status == "pending_approval":
                tool_run.status = "pending_approval"  # type: ignore[assignment]
                tool_run.output_json = {  # type: ignore[assignment]
                    "status": "pending_approval",
                    "approval_id": response.decision.get("approval_id"),
                    "reason": response.decision.get("reason"),
                }
                await _upsert_pending_approval(
                    session,
                    approval_id=str(
                        response.decision.get("approval_id") or f"apr_{run_id}_{req.tool_name}"
                    ),
                    workspace_id=req.workspace_id,
                    project_id=project_id,
                    analysis_run_id=req.analysis_run_id,
                    tool_run_id=str(tool_run.id),
                    risk_class=risk_class,
                    action_name=req.tool_name,
                    reason=str(response.decision.get("reason") or ""),
                    request_json={"tool": req.tool_name, "args": req.arguments, "run_id": run_id},
                    requested_by=actor_user_id,
                )
            else:
                tool_run.status = response.status  # type: ignore[assignment]
                tool_run.output_json = response.result or {}  # type: ignore[assignment]
                if response.status != "ok":
                    tool_run.error_message = response.message  # type: ignore[assignment]
            tool_run.completed_at = datetime.now(timezone.utc)  # type: ignore[assignment]
            await session.commit()
            return response

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
        result_payload = dict(call_result.result or {}) if call_result.result is not None else None

        if call_result.status == "pending_approval":
            tool_run.status = "pending_approval"  # type: ignore[assignment]
            tool_run.output_json = {  # type: ignore[assignment]
                "status": "pending_approval",
                "approval_id": call_result.decision.approval_id,
                "reason": call_result.decision.reason,
            }
            await _upsert_pending_approval(
                session,
                approval_id=call_result.decision.approval_id or f"apr_{run_id}_{req.tool_name}",
                workspace_id=req.workspace_id,
                project_id=project_id,
                analysis_run_id=req.analysis_run_id,
                tool_run_id=str(tool_run.id),
                risk_class=risk_class,
                action_name=req.tool_name,
                reason=call_result.decision.reason,
                request_json={"tool": req.tool_name, "args": req.arguments, "run_id": run_id},
                requested_by=actor_user_id,
            )
        elif call_result.status == "ok":
            if (
                req.tool_name == "web_search"
                and isinstance(result_payload, dict)
                and not result_payload.get("evidence")
            ):
                result_payload = enrich_web_search_payload(
                    result_payload,
                    query=str(req.arguments.get("query", "") or "").strip(),
                    context=context,
                    project_id=project_id,
                )
            tool_run.status = "ok"  # type: ignore[assignment]
            tool_run.output_json = result_payload or {}  # type: ignore[assignment]

            evidence_payloads: list[Any] = []
            if isinstance(result_payload, dict):
                evidence_payloads = result_payload.get("evidence", []) or []

                artifacts = result_payload.get("artifacts") or {}
                if isinstance(artifacts, dict):
                    report_spec = artifacts.get("report")
                    if isinstance(report_spec, dict):
                        report_id = str(uuid.uuid4())
                        session.add(
                            Report(
                                id=report_id,
                                workspace_id=req.workspace_id,
                                project_id=project_id,
                                site_id=req.site_id,
                                analysis_run_id=req.analysis_run_id,
                                status=str(report_spec.get("status") or "draft"),
                                report_json=dict(report_spec.get("report_json") or {}),
                                evidence_ids=list(report_spec.get("evidence_ids") or []),
                                version=1,
                            )
                        )
                        # Ensure the report row exists before inserting any document that references it.
                        await session.flush()
                        artifact_ids["report_id"] = report_id

                    document_spec = artifacts.get("document")
                    if isinstance(document_spec, dict):
                        document_id = str(uuid.uuid4())
                        session.add(
                            Document(
                                id=document_id,
                                workspace_id=req.workspace_id,
                                project_id=project_id,
                                site_id=req.site_id,
                                report_id=artifact_ids.get("report_id"),
                                document_type=str(document_spec.get("document_type") or "document"),
                                status=str(document_spec.get("status") or "draft"),
                                storage_url=document_spec.get("storage_url"),
                                metadata_json=dict(document_spec.get("metadata_json") or {}),
                            )
                        )
                        artifact_ids["document_id"] = document_id

            for raw in evidence_payloads:
                evidence = LandUseEvidenceItem.model_validate(raw)
                await persist_land_use_evidence(session, evidence=evidence)
                evidence_ids.append(evidence.id)
        else:
            tool_run.status = call_result.status  # type: ignore[assignment]
            tool_run.output_json = result_payload or {}  # type: ignore[assignment]
            tool_run.error_message = call_result.message  # type: ignore[assignment]

        tool_run.completed_at = datetime.now(timezone.utc)  # type: ignore[assignment]
        await session.commit()

        return ToolCallResponse(
            run_id=run_id,
            tool_run_id=str(tool_run.id),
            tool_name=call_result.tool_name,
            status=call_result.status,
            decision=call_result.decision.model_dump(),
            result=result_payload,
            message=call_result.message,
            evidence_ids=evidence_ids,
            artifact_ids=artifact_ids,
            events=[{"kind": e.kind, "id": e.id, "payload": e.payload} for e in event_buffer],
        )
    except Exception:
        try:
            await session.rollback()
        except Exception:
            logger.warning("Rollback failed", exc_info=True)
        raise
    finally:
        await session.close()


def _is_full_harness_tool(tool_name: str) -> bool:
    try:
        get_tool_spec(tool_name)
    except RegistryLookupError:
        return False
    return True


async def _call_full_harness_tool(
    *,
    req: ToolCallRequest,
    context: ToolContext,
    source_mode: SourceMode,
) -> ToolCallResponse:
    result = await default_tool_router().call_async(
        HarnessToolCallRequest(
            tool_name=req.tool_name,
            args=req.arguments,
            context=FullHarnessToolContext(
                workspace_id=context.workspace_id,
                actor_user_id=context.actor_user_id,
                run_id=context.run_id,
                project_id=context.project_id,
                site_id=context.site_id,
                risk_budget_cents=context.risk_budget_cents,
                live_network_allowed=context.live_network_allowed,
                approved_approval_ids=context.approved_approval_ids,
            ),
            source_mode=source_mode,
            execution_mode=ExecutionMode.API,
            approval_id=req.approval_id,
        )
    )
    default_tool_call_ledger().save_tool_call(tool_call_from_result(result))
    try:
        default_harness_run_store().append_events(result.run_id, result.events)
    except HarnessRunNotFoundError:
        pass
    return ToolCallResponse(
        run_id=context.run_id,
        tool_run_id=str(result.tool_call_id),
        tool_name=result.tool_name,
        status=_legacy_status(result.status.value),
        decision=result.policy_decision.model_dump(mode="json"),
        result=result.payload,
        message=_legacy_message(result),
        evidence_ids=[str(value) for value in result.evidence_ids],
        artifact_ids={},
        events=[event.model_dump(mode="json") for event in result.events],
        source_mode=result.source_mode.value,
    )


def _legacy_message(result) -> str | None:  # noqa: ANN001
    if result.error is not None:
        return result.error.message
    if result.policy_decision.approval_required:
        return result.policy_decision.reason
    return None


def _legacy_status(status: str) -> str:
    match status:
        case "completed":
            return "ok"
        case "approval_required":
            return "pending_approval"
        case "denied":
            return "blocked"
        case _:
            return "error"
