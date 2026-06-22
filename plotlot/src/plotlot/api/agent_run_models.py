from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from plotlot.harness.agent_run_responses import (
    AgentRunAssignmentResponse,
    AgentRunEscalationResponse,
    AgentRunResponse,
    AgentRunTraceStepResponse,
    agent_run_response,
)

__all__ = [
    "AgentRunAssignmentResponse",
    "AgentRunEscalationResponse",
    "AgentRunResponse",
    "AgentRunStartRequest",
    "AgentRunTraceStepResponse",
    "agent_run_response",
]


class AgentRunStartRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    lookup_snapshot_id: str = Field(min_length=1)
    workspace_id: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    project_id: str | None = None
    site_id: str | None = None
    run_id: str | None = None
    open_questions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
