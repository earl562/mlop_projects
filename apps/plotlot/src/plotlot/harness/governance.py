"""Tool governance and approval primitives.

This upgrades the current ``PLOTLOT_TOOL_PERMISSION_MODE`` check into a typed
boundary while preserving the existing read-only default.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from plotlot.config import settings


class ToolRisk(StrEnum):
    READ_ONLY = "read_only"
    EXPENSIVE_READ = "expensive_read"
    WRITE_INTERNAL = "write_internal"
    WRITE_EXTERNAL = "write_external"
    EXECUTION = "execution"


class ToolDecisionStatus(StrEnum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    APPROVAL_REQUIRED = "approval_required"


@dataclass(slots=True)
class ToolManifest:
    name: str
    risk: ToolRisk = ToolRisk.READ_ONLY
    description: str = ""


@dataclass(slots=True)
class ToolDecision:
    status: ToolDecisionStatus
    reason: str = ""

    @property
    def allowed(self) -> bool:
        return self.status == ToolDecisionStatus.ALLOWED


WRITE_TOOL_NAMES = {
    "create_spreadsheet",
    "create_document",
    "export_dataset",
    "generate_document",
}


DEFAULT_TOOL_MANIFESTS: dict[str, ToolManifest] = {
    name: ToolManifest(name=name, risk=ToolRisk.WRITE_EXTERNAL) for name in WRITE_TOOL_NAMES
}


class GovernanceMiddleware:
    """Evaluates tool calls before execution."""

    def __init__(self, manifests: dict[str, ToolManifest] | None = None) -> None:
        self._manifests = manifests or DEFAULT_TOOL_MANIFESTS

    def decide(self, tool_name: str) -> ToolDecision:
        manifest = self._manifests.get(tool_name, ToolManifest(name=tool_name))
        if settings.tool_permission_mode == "read_only" and manifest.risk in {
            ToolRisk.WRITE_EXTERNAL,
            ToolRisk.EXECUTION,
        }:
            return ToolDecision(
                status=ToolDecisionStatus.BLOCKED,
                reason=(
                    f"Tool '{tool_name}' is blocked by policy "
                    "(tool_permission_mode=read_only). Set "
                    "PLOTLOT_TOOL_PERMISSION_MODE=allow_writes to enable external write tools."
                ),
            )
        return ToolDecision(status=ToolDecisionStatus.ALLOWED)
