"""Policy decisions for PlotLot land-use tool calls."""

from __future__ import annotations

from dataclasses import dataclass, field

from plotlot.land_use.models import PolicyDecision, ToolContext, ToolContract, ToolRiskClass


@dataclass(frozen=True)
class ToolPolicy:
    """Small default policy for the first harness slice.

    The policy is intentionally independent from prompts/model output. It only
    considers static tool metadata, execution context, and explicit approvals.
    """

    approval_prefix: str = "apr"
    internal_write_tools: frozenset[str] = field(default_factory=frozenset)

    def authorize(
        self,
        tool: ToolContract,
        context: ToolContext,
        *,
        approval_id: str | None = None,
    ) -> PolicyDecision:
        """Authorize a tool call or return an approval/block decision."""

        risk = ToolRiskClass(tool.risk_class)
        if not context.live_network_allowed and risk in {
            ToolRiskClass.EXPENSIVE_READ,
            ToolRiskClass.WRITE_EXTERNAL,
            ToolRiskClass.EXECUTION,
        }:
            return PolicyDecision(
                allowed=False,
                reason="live network tools are disabled for this run",
            )
        if risk == ToolRiskClass.READ_ONLY:
            return PolicyDecision(allowed=True, reason="read-only tools are allowed by default")

        if risk == ToolRiskClass.EXPENSIVE_READ:
            requested = approval_id or self._approval_id(tool.name, context.run_id)
            if requested in context.approved_approval_ids:
                return PolicyDecision(allowed=True, reason="explicit approval is present")
            if context.risk_budget_cents >= tool.budget_cents:
                return PolicyDecision(allowed=True, reason="expensive read is within risk budget")
            return PolicyDecision(
                allowed=False,
                approval_required=True,
                approval_id=requested,
                reason="expensive read exceeds available risk budget",
            )

        if risk == ToolRiskClass.WRITE_INTERNAL:
            if tool.name in self.internal_write_tools:
                return PolicyDecision(allowed=True, reason="internal write tool is allowlisted")
            requested = approval_id or self._approval_id(tool.name, context.run_id)
            if requested in context.approved_approval_ids:
                return PolicyDecision(allowed=True, reason="explicit approval is present")
            return PolicyDecision(
                allowed=False,
                approval_required=True,
                approval_id=requested,
                reason="internal write requires allowlist or approval",
            )

        if risk in {ToolRiskClass.WRITE_EXTERNAL, ToolRiskClass.EXECUTION}:
            requested = approval_id or self._approval_id(tool.name, context.run_id)
            if requested in context.approved_approval_ids:
                return PolicyDecision(allowed=True, reason="explicit approval is present")
            return PolicyDecision(
                allowed=False,
                approval_required=True,
                approval_id=requested,
                reason=f"{risk.value} tools require explicit approval",
            )

        return PolicyDecision(allowed=False, reason=f"unsupported risk class: {risk}")

    def _approval_id(self, tool_name: str, run_id: str) -> str:
        safe_tool = tool_name.replace(".", "_")
        return f"{self.approval_prefix}_{run_id}_{safe_tool}"
