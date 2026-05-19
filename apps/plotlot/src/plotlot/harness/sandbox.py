"""Sandbox execution seam for harness tools and generated workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class SandboxResult:
    status: str
    output: str = ""
    artifacts: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class SandboxRunner(Protocol):
    async def run(self, *, command: str, payload: dict[str, Any] | None = None) -> SandboxResult:
        """Execute a sandboxed action."""


class LocalNoopSandbox:
    """Non-executing placeholder until a real sandbox backend is wired in."""

    async def run(self, *, command: str, payload: dict[str, Any] | None = None) -> SandboxResult:
        return SandboxResult(
            status="not_implemented",
            output="Sandbox scaffolding is present but not yet wired to an executor.",
            metadata={"command": command, "payload": payload or {}},
        )


__all__ = ["LocalNoopSandbox", "SandboxResult", "SandboxRunner"]
