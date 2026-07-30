"""Policy seam for harness tool execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import assert_never

from plotlot.harness.contracts import PolicyPermission, ToolSpec
from plotlot.land_use.models import PolicyDecision, ToolContext
from plotlot.land_use.policy import ToolPolicy

from plotlot.harness.tool_registry import get_tool_contract


@dataclass(frozen=True, slots=True)
class HarnessPolicyRequest:
    tool_spec: ToolSpec
    context: ToolContext
    approval_id: str | None = None


class HarnessPolicyEngine:
    """Authorize tool calls using ToolPolicy + tool contracts."""

    def __init__(self, policy: ToolPolicy | None = None) -> None:
        self._policy = policy or ToolPolicy()

    def authorize(
        self,
        *,
        tool_name: str,
        context: ToolContext,
        approval_id: str | None = None,
    ) -> PolicyDecision:
        contract = get_tool_contract(tool_name)
        return self._policy.authorize(contract, context, approval_id=approval_id)

    def authorize_tool_spec(self, request: HarnessPolicyRequest) -> PolicyDecision:
        match request.tool_spec.permission:
            case PolicyPermission.ALLOW:
                try:
                    contract = get_tool_contract(request.tool_spec.name)
                except KeyError:
                    return PolicyDecision(
                        allowed=False,
                        reason=f"tool contract missing for tool spec: {request.tool_spec.name}",
                    )
                return self._policy.authorize(
                    contract,
                    request.context,
                    approval_id=request.approval_id,
                )
            case PolicyPermission.ASK:
                requested = request.approval_id or _approval_id(
                    request.tool_spec.name,
                    request.context.run_id,
                )
                if requested in request.context.approved_approval_ids:
                    try:
                        contract = get_tool_contract(request.tool_spec.name)
                    except KeyError:
                        return PolicyDecision(
                            allowed=False,
                            reason=f"tool contract missing for tool spec: {request.tool_spec.name}",
                        )
                    return self._policy.authorize(
                        contract,
                        request.context,
                        approval_id=requested,
                    )
                return PolicyDecision(
                    allowed=False,
                    approval_required=True,
                    approval_id=requested,
                    reason="tool spec permission requires approval",
                )
            case PolicyPermission.DENY:
                return PolicyDecision(
                    allowed=False,
                    reason=f"tool spec permission denied: {request.tool_spec.name}",
                )
            case unreachable:
                assert_never(unreachable)


def _approval_id(tool_name: str, run_id: str) -> str:
    safe_tool = tool_name.replace(".", "_")
    return f"apr_{run_id}_{safe_tool}"
