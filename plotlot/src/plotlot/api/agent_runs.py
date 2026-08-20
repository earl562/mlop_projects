"""REST surface for governed PlotLot multi-agent workflows."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import ConfigDict, Field

from plotlot.domain.types import ToolContext
from plotlot.harness.agents import (
    AgentPlan,
    AgentSpec,
    MultiAgentCoordinator,
    MultiAgentRunRequest,
    MultiAgentRunResult,
    build_default_agent_registry,
)
from plotlot.harness.default_runtime import get_default_runtime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent-runs", tags=["multi-agent"])


class AgentRunCreateRequest(MultiAgentRunRequest):
    model_config = ConfigDict(frozen=True)

    workspace_id: str = Field(default="default-workspace", min_length=1, max_length=120)
    project_id: str | None = Field(default=None, max_length=36)
    site_id: str | None = Field(default=None, max_length=36)
    run_id: str | None = Field(default=None, min_length=1, max_length=120)
    risk_budget_cents: int = Field(default=100, ge=0, le=100_000)
    live_network_allowed: bool = True
    approved_approval_ids: list[str] = Field(default_factory=list, max_length=50)


def get_multi_agent_coordinator() -> MultiAgentCoordinator:
    return MultiAgentCoordinator(get_default_runtime())


Coordinator = Annotated[MultiAgentCoordinator, Depends(get_multi_agent_coordinator)]


def _actor_user_id(http_request: Request) -> str:
    user = getattr(http_request.state, "user", None)
    if isinstance(user, dict) and user.get("user_id"):
        return str(user["user_id"])
    actor = getattr(http_request.state, "actor", None)
    if actor is not None and getattr(actor, "user_id", None):
        return str(actor.user_id)
    return "anonymous"


async def _validated_approved_ids(
    *,
    approval_ids: set[str],
    workspace_id: str,
) -> set[str]:
    """Validate approvals against durable records; fail closed on storage errors."""

    if not approval_ids:
        return set()

    from plotlot.storage.db import get_session
    from plotlot.storage.models import ApprovalRequest

    session = None
    try:
        session = await get_session()
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
        logger.warning("Multi-agent approval validation failed; failing closed", exc_info=True)
        return set()
    finally:
        if session is not None:
            await session.close()


@router.get("/specialists", response_model=list[AgentSpec])
async def list_agents() -> tuple[AgentSpec, ...]:
    return build_default_agent_registry().list()


@router.post("/plan", response_model=AgentPlan)
async def plan_agent_run(
    request: AgentRunCreateRequest,
    coordinator: Coordinator,
) -> AgentPlan:
    return coordinator.plan(request)


@router.post("", response_model=MultiAgentRunResult)
async def execute_agent_run(
    request: AgentRunCreateRequest,
    http_request: Request,
    coordinator: Coordinator,
) -> MultiAgentRunResult:
    run_id = request.run_id or f"run_{uuid.uuid4().hex[:16]}"
    approved_ids = await _validated_approved_ids(
        approval_ids=set(request.approved_approval_ids),
        workspace_id=request.workspace_id,
    )
    context = ToolContext(
        workspace_id=request.workspace_id,
        actor_user_id=_actor_user_id(http_request),
        run_id=run_id,
        project_id=request.project_id,
        site_id=request.site_id,
        analysis_run_id=run_id,
        risk_budget_cents=request.risk_budget_cents,
        live_network_allowed=request.live_network_allowed,
        approved_approval_ids=approved_ids,
    )
    return await coordinator.run(request, context)


__all__ = [
    "AgentRunCreateRequest",
    "execute_agent_run",
    "get_multi_agent_coordinator",
    "list_agents",
    "plan_agent_run",
    "router",
]
