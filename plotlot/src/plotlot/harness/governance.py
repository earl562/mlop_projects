"""Governance — permission modes, sandboxing, safety checks.

Per LangChain middleware posts: deterministic policy enforcement at every call.
Per OpenAI Harness Engineering: mechanical enforcement > prompted compliance.
Per Claude Code arch (2604.14228): 7-mode permission with ML classifier.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from plotlot.harness.middleware import AgentMiddleware, AgentState


class PermissionLevel(str, Enum):
    READ_ONLY = "read_only"
    ASK_TO_WRITE = "ask_to_write"
    AUTO_WITH_APPROVALS = "auto_with_approvals"
    UNRESTRICTED = "unrestricted"


class ToolRisk(str, Enum):
    READ_ONLY = "read_only"
    WRITE_INTERNAL = "write_internal"
    WRITE_EXTERNAL = "write_external"
    EXECUTION = "execution"


TOOL_RISK_MAP: dict[str, ToolRisk] = {
    "read_file": ToolRisk.READ_ONLY,
    "glob_files": ToolRisk.READ_ONLY,
    "grep_files": ToolRisk.READ_ONLY,
    "web_search": ToolRisk.READ_ONLY,
    "web_fetch": ToolRisk.READ_ONLY,
    "write_file": ToolRisk.WRITE_INTERNAL,
    "edit_file": ToolRisk.WRITE_INTERNAL,
    "generate_document": ToolRisk.WRITE_INTERNAL,
    "draft_email": ToolRisk.WRITE_INTERNAL,
    "create_spreadsheet": ToolRisk.WRITE_EXTERNAL,
    "create_document": ToolRisk.WRITE_EXTERNAL,
    "gmail_send_draft": ToolRisk.WRITE_EXTERNAL,
    "bash_execute": ToolRisk.EXECUTION,
}


@dataclass
class SandboxConfig:
    sandbox_type: str = "local"  # local, docker, microvm
    timeout_seconds: int = 60
    allowed_commands: list[str] = field(default_factory=list)
    network_access: bool = False

    @classmethod
    def development(cls) -> "SandboxConfig":
        return cls(sandbox_type="local", timeout_seconds=120, network_access=True)

    @classmethod
    def production(cls) -> "SandboxConfig":
        return cls(sandbox_type="docker", timeout_seconds=60, network_access=False)

    @classmethod
    def untrusted(cls) -> "SandboxConfig":
        return cls(sandbox_type="microvm", timeout_seconds=30, network_access=False)


class PermissionMiddleware(AgentMiddleware):
    """Gate tool execution based on risk level and permission mode."""

    def __init__(self, level: PermissionLevel = PermissionLevel.ASK_TO_WRITE):
        self._level = level
        self._pending_approvals: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "PermissionMiddleware"

    async def wrap_tool_call(
        self,
        state: AgentState,
        tool_name: str,
        tool_args: dict[str, Any],
        execute_tool: Any,
    ) -> dict[str, Any]:
        risk = TOOL_RISK_MAP.get(tool_name, ToolRisk.EXECUTION)
        if self._level == PermissionLevel.READ_ONLY and risk != ToolRisk.READ_ONLY:
            return {"ok": False, "error": f"Tool {tool_name} blocked: read-only mode", "risk": risk.value}
        if self._level == PermissionLevel.ASK_TO_WRITE and risk in (ToolRisk.WRITE_INTERNAL, ToolRisk.WRITE_EXTERNAL):
            approval = {"tool": tool_name, "args": tool_args, "risk": risk.value, "status": "pending"}
            self._pending_approvals.append(approval)
            state.custom["approval_required"] = True
            return {"ok": False, "error": f"Tool {tool_name} requires approval", "risk": risk.value, "approval_pending": True}
        if self._level == PermissionLevel.AUTO_WITH_APPROVALS and risk == ToolRisk.WRITE_EXTERNAL:
            approval = {"tool": tool_name, "args": tool_args, "risk": risk.value, "status": "pending"}
            self._pending_approvals.append(approval)
            state.custom["approval_required"] = True
            return {"ok": False, "error": f"External write {tool_name} requires approval", "risk": risk.value, "approval_pending": True}
        return await execute_tool(tool_name, tool_args)

    @property
    def pending_approvals(self) -> list[dict[str, Any]]:
        return list(self._pending_approvals)


class SandboxMiddleware(AgentMiddleware):
    """Wrap tool execution with sandbox config."""

    def __init__(self, config: SandboxConfig | None = None):
        self._config = config or SandboxConfig.development()

    @property
    def name(self) -> str:
        return "SandboxMiddleware"

    async def wrap_tool_call(self, state: AgentState, tool_name: str, tool_args: dict[str, Any], execute_tool: Any) -> dict[str, Any]:
        risk = TOOL_RISK_MAP.get(tool_name, ToolRisk.EXECUTION)
        if risk == ToolRisk.EXECUTION:
            state.custom["sandbox_active"] = True
            state.custom["sandbox_type"] = self._config.sandbox_type
        return await execute_tool(tool_name, tool_args)


DANGEROUS_COMMANDS = {"rm -rf /", "sudo ", "chmod 777 /", "mkfs.", "dd if=", ":(){ :|:& };:"}


def check_pii(text: str) -> list[str]:
    """Stub PII detection — replace with production PIIMiddleware."""
    found: list[str] = []
    for pattern in ["\\b\\d{3}-\\d{2}-\\d{4}\\b", "\\b\\d{16}\\b", "\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Z|a-z]{2,}\\b"]:
        import re
        if re.search(pattern, text):
            found.append(pattern)
    return found


def check_dangerous_commands(command: str) -> list[str]:
    return [c for c in DANGEROUS_COMMANDS if c in command]


def check_path_traversal(path: str) -> bool:
    import os
    resolved = os.path.abspath(path)
    cwd = os.path.abspath(os.getcwd())
    return resolved.startswith(cwd)