"""Agent harness runtime boundary.

Architecture: middleware-based (not role-based). Supported by research:
- LangChain middleware posts (2026), AHE paper (2604.25850),
- Claude Code arch (2604.14228), OpenDev v3 (2603.05344)

Use AgentConfig + AgentLoop as the entry point.
Compose behavior via AgentMiddleware subclasses.
"""

from plotlot.harness.agent_loop import AgentConfig, AgentLoop
from plotlot.harness.builtin_middleware import (
    LocalContextMiddleware, LoopDetectionMiddleware, SaveStateMiddleware,
    TokenAwareMiddleware, ToolCallOffloadMiddleware,
)
from plotlot.harness.context import ContextBroker, ContextPacket
from plotlot.harness.events import HarnessEvent
from plotlot.harness.evidence import AuditTrail, ClaimSurvivalTracker, EvidenceClaim, EvidenceLedger, EvidenceMiddleware
from plotlot.harness.filesystem_tools import FILESYSTEM_TOOLS, edit_file, glob_files, grep_files, read_file, write_file
from plotlot.harness.governance import PermissionLevel, PermissionMiddleware, SandboxConfig, SandboxMiddleware, ToolRisk, check_dangerous_commands, check_path_traversal, check_pii
from plotlot.harness.interpreter_skills import INTERPRETER_SKILLS, ComplianceResult, ParcelZoning, ProposedUse, ProFormaInputs, SitePlan, ZoningCode, calculate_fees, calculate_pro_forma, check_zoning, identify_permits, validate_setbacks
from plotlot.harness.mcp_adapter import MCPAdapter
from plotlot.harness.mcp_augmentation import AugmentedDescription, MCPAugmentationPipeline
from plotlot.harness.memory_store import MemoryEntry, MemoryMiddleware, MemoryStore, MemoryTier
from plotlot.harness.middleware import AgentMiddleware, AgentState, MiddlewarePipeline
from plotlot.harness.model_adapter import OPENROUTER_FREE_MODELS, create_model_caller
from plotlot.harness.policy import HarnessPolicyEngine
from plotlot.harness.rubric_middleware import RubricMiddleware
from plotlot.harness.runtime import HarnessRuntime, ToolCallResult
from plotlot.harness.skill_registry import SkillManifest, SkillRegistry
from plotlot.harness.subagent import SubAgent, SubAgentMiddleware, SubAgentResult, isolated_tools
from plotlot.harness.tool_registry import get_tool_contract, list_tool_contracts

__all__ = [
    "AgentConfig", "AgentLoop", "AgentMiddleware", "AgentState",
    "AuditTrail", "AugmentedDescription",
    "ClaimSurvivalTracker", "ComplianceResult", "ContextBroker", "ContextPacket",
    "EvidenceClaim", "EvidenceLedger", "EvidenceMiddleware",
    "FILESYSTEM_TOOLS",
    "HarnessPolicyEngine", "HarnessEvent", "HarnessRuntime",
    "INTERPRETER_SKILLS",
    "LocalContextMiddleware", "LoopDetectionMiddleware",
    "MCPAdapter", "MCPAugmentationPipeline",
    "MemoryEntry", "MemoryMiddleware", "MemoryStore", "MemoryTier",
    "MiddlewarePipeline",
    "OPENROUTER_FREE_MODELS",
    "ParcelZoning", "PermissionLevel", "PermissionMiddleware",
    "ProFormaInputs", "ProposedUse",
    "RubricMiddleware",
    "SandboxConfig", "SandboxMiddleware", "SaveStateMiddleware",
    "SitePlan", "SkillManifest", "SkillRegistry",
    "SubAgent", "SubAgentMiddleware", "SubAgentResult",
    "TokenAwareMiddleware", "ToolCallOffloadMiddleware", "ToolCallResult", "ToolRisk",
    "ZoningCode",
    "calculate_fees", "calculate_pro_forma", "check_dangerous_commands",
    "check_path_traversal", "check_pii", "check_zoning",
    "create_model_caller",
    "edit_file",
    "get_tool_contract", "glob_files", "grep_files",
    "identify_permits", "isolated_tools",
    "list_tool_contracts",
    "read_file",
    "validate_setbacks",
    "write_file",
]