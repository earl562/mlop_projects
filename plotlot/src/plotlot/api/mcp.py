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

from plotlot.harness.default_runtime import get_default_runtime
from plotlot.harness.mcp_adapter import MCPAdapter
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

    result = await adapter.call_tool(
        name=body.name,
        arguments=body.arguments,
        context=body.context,
        approval_id=body.approval_id,
    )

    if result.status == "pending_approval" and result.decision.approval_id:
        session = await get_session()
        try:
            existing = await session.get(ApprovalRequest, result.decision.approval_id)
            if existing is None:
                session.add(
                    ApprovalRequest(
                        id=result.decision.approval_id,
                        workspace_id=body.context.workspace_id,
                        project_id=body.context.project_id,
                        analysis_run_id=body.context.analysis_run_id,
                        tool_run_id=body.context.tool_run_id,
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
                await session.commit()
        except Exception:
            logger.warning("Failed to persist approval request from MCP call", exc_info=True)
            try:
                await session.rollback()
            except Exception:
                logger.warning("Rollback failed", exc_info=True)
        finally:
            await session.close()
    return {
        "tool_name": result.tool_name,
        "status": result.status,
        "decision": result.decision.model_dump(),
        "result": result.result,
        "message": result.message,
    }
