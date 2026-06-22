"""HTTP surface for MCP-like tool semantics.

This is not the full MCP protocol implementation. It exposes the two core
operations (tools/list and tools/call) over HTTP so clients can integrate while
the full MCP transport layer is stabilized.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from plotlot.api.mcp_tool_run_persistence import (
    McpToolRunCompletion,
    McpToolRunStartRequest,
    complete_mcp_tool_run,
    persist_mcp_result,
    requires_mcp_persistence,
    start_mcp_tool_run,
)
from plotlot.api.recorded_evidence_context import recorded_evidence_ids
from plotlot.api.tool_run_trace import event_dicts
from plotlot.harness.events import HarnessEvent
from plotlot.harness.default_runtime import get_default_runtime
from plotlot.harness.mcp_adapter import MCPAdapter
from plotlot.harness.report_artifacts import requested_document_evidence_ids
from plotlot.harness.tool_registry import tool_risk_class
from plotlot.land_use.models import ToolContext
from plotlot.storage.db import get_session
from plotlot.storage.models import ApprovalRequest


logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/v1/mcp", tags=["mcp"])


class MCPCallRequest(BaseModel):
    name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    context: ToolContext
    approval_id: str | None = None


async def _validated_approved_ids(*, approval_ids: set[str], workspace_id: str) -> set[str]:
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
        logger.warning("MCP approval validation failed; failing closed", exc_info=True)
        return set()
    finally:
        await session.close()


@router.get("/tools/list")
async def tools_list() -> list[dict[str, Any]]:
    adapter = MCPAdapter(get_default_runtime())
    return adapter.list_tools()


@router.post("/tools/call")
async def tools_call(body: MCPCallRequest) -> dict[str, Any]:
    adapter = MCPAdapter(get_default_runtime())

    claimed = set(body.context.approved_approval_ids or set())
    risk_class = tool_risk_class(body.name)
    validated = claimed
    if risk_class in {"write_external", "execution", "write_internal", "expensive_read"}:
        validated = await _validated_approved_ids(
            approval_ids=claimed,
            workspace_id=body.context.workspace_id,
        )
        body = body.model_copy(
            update={"context": body.context.model_copy(update={"approved_approval_ids": validated})}
        )

    session = await get_session()
    try:
        recorded_ids = await recorded_evidence_ids(
            session,
            requested_document_evidence_ids(body.arguments)
            if body.name == "generate_document"
            else (),
        )
        body = body.model_copy(
            update={
                "context": body.context.model_copy(update={"recorded_evidence_ids": recorded_ids})
            }
        )
        tool_run_start = await start_mcp_tool_run(
            session,
            McpToolRunStartRequest(
                tool_name=body.name,
                arguments=body.arguments,
                risk_class=risk_class,
                context=body.context,
            ),
        )
        body = body.model_copy(update={"context": tool_run_start.context})

        event_buffer: list[HarnessEvent] = []
        result = await adapter.call_tool(
            name=body.name,
            arguments=body.arguments,
            context=body.context,
            approval_id=body.approval_id,
            events=event_buffer,
        )

        response_status = result.status
        response_message = result.message
        result_payload = result.result
        evidence_ids: list[str] = []
        artifact_ids: dict[str, str] = {}

        if result.status == "ok" and requires_mcp_persistence(result_payload):
            persisted = await persist_mcp_result(
                session,
                result_payload=result_payload or {},
                context=body.context,
            )
            response_status = persisted.status
            response_message = persisted.message
            result_payload = persisted.result_payload
            evidence_ids = persisted.evidence_ids
            artifact_ids = persisted.artifact_ids

        if result.status == "pending_approval" and result.decision.approval_id:
            existing = await session.get(ApprovalRequest, result.decision.approval_id)
            if existing is None:
                session.add(
                    ApprovalRequest(
                        id=result.decision.approval_id,
                        workspace_id=body.context.workspace_id,
                        project_id=body.context.project_id,
                        analysis_run_id=body.context.analysis_run_id,
                        tool_run_id=tool_run_start.tool_run.id,
                        status="pending",
                        risk_class=risk_class,
                        action_name=body.name,
                        reason=result.decision.reason,
                        request_json={
                            "tool": body.name,
                            "args": body.arguments,
                            "run_id": body.context.run_id,
                        },
                        response_json={},
                        requested_by=body.context.actor_user_id,
                    )
                )

        complete_mcp_tool_run(
            tool_run_start.tool_run,
            McpToolRunCompletion(
                run_id=body.context.run_id,
                status=response_status,
                decision=result.decision,
                result_payload=result_payload,
                message=response_message,
                evidence_ids=evidence_ids,
                artifact_ids=artifact_ids,
                events=event_buffer,
            ),
        )
        await session.commit()
        return {
            "tool_run_id": str(tool_run_start.tool_run.id),
            "tool_name": result.tool_name,
            "status": response_status,
            "decision": result.decision.model_dump(),
            "result": result_payload,
            "message": response_message,
            "evidence_ids": evidence_ids,
            "artifact_ids": artifact_ids,
            "events": event_dicts(event_buffer),
        }
    except Exception:
        logger.warning("Failed to persist MCP tool run", exc_info=True)
        try:
            await session.rollback()
        except Exception:
            logger.warning("Rollback failed", exc_info=True)
        raise
    finally:
        await session.close()
