"""Typed events emitted by the harness runtime.

Transport adapters (REST/chat/MCP/frontend) should render these events as a
timeline with approvals, tool calls, evidence, artifacts, and specialist-agent
progress.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


EventKind = Literal[
    "run_started",
    "plan_created",
    "agent_started",
    "agent_completed",
    "task_started",
    "task_completed",
    "task_skipped",
    "tool_call",
    "tool_result",
    "approval_required",
    "evidence_recorded",
    "run_failed",
    "run_completed",
]


@dataclass(frozen=True)
class HarnessEvent:
    kind: EventKind
    id: str
    payload: dict[str, Any]
