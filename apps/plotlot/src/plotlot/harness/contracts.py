"""Typed contracts for the PlotLot agent harness.

The harness layer is intentionally small at first: it gives the existing
pipeline a stable place to plug into workspace/project/evidence state without
rewriting the lookup and chat endpoints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:  # pragma: no cover
    from plotlot.harness.runtime import HarnessRuntime


@dataclass(slots=True)
class HarnessContext:
    """Request-scoped context passed through skills and tools."""

    workspace_id: str | None = None
    project_id: str | None = None
    site_id: str | None = None
    user_id: str | None = None
    session_id: str | None = None


@dataclass(slots=True)
class SkillInput:
    """Input envelope for a harness skill."""

    prompt: str
    payload: dict[str, Any] = field(default_factory=dict)
    context: HarnessContext = field(default_factory=HarnessContext)


@dataclass(slots=True)
class SkillOutput:
    """Structured result returned by a harness skill."""

    status: str
    summary: str
    data: dict[str, Any] = field(default_factory=dict)
    evidence_ids: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)


class Skill(Protocol):
    """Protocol implemented by repo-owned skills."""

    name: str
    triggers: tuple[str, ...]

    async def run(self, runtime: "HarnessRuntime", skill_input: SkillInput) -> SkillOutput:
        """Execute the skill."""


@dataclass(slots=True)
class ToolResult:
    """Common shape for deterministic tool output."""

    status: str
    data: dict[str, Any] = field(default_factory=dict)
    sources: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    confidence: str = "medium"


class Tool(Protocol):
    """Protocol for deterministic tools exposed to the harness."""

    name: str
    description: str

    async def invoke(self, **kwargs: Any) -> ToolResult:
        """Invoke the tool."""
