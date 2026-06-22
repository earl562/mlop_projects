from __future__ import annotations

from typing import Any

from fastapi import Request
from pydantic import BaseModel, Field


def actor_user_id(http_request: Request) -> str:
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
