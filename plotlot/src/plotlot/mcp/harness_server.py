"""Governed PlotLot MCP server (stdio) — every tool routes through the harness.

Run via:
    plotlot-mcp-harness         # stdio transport (Claude Code / Claude Desktop)

This is the MCP face of the same `HarnessRuntime` that backs the REST surface
and the CLI, so an external agent gets the identical policy gate, risk budget,
approval requirement, and evidence that PlotLot's own chat does. Tools are
registered dynamically from the tool registry, so a contract added there shows
up here automatically with its real input schema.

Contrast with `plotlot.mcp.server` (the original `plotlot-mcp`): that one calls
domain functions directly and therefore bypasses policy, budgets, approvals,
evidence, and the audit trail. Prefer this server for anything that can write.

Governance is configured per-process by environment variable, because an MCP
client has no way to pass execution context:

    PLOTLOT_MCP_WORKSPACE      workspace id for audit rows   (default "mcp")
    PLOTLOT_MCP_ACTOR          actor id for audit rows       (default "mcp-client")
    PLOTLOT_MCP_BUDGET_CENTS   risk budget per call          (default 1000)
    PLOTLOT_MCP_LIVE_NETWORK   allow live-network tools      (default "1")
    PLOTLOT_MCP_APPROVALS      comma-separated approval ids to present
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

import fastmcp
from fastmcp.tools.function_tool import FunctionTool

from plotlot.harness.default_runtime import get_default_runtime
from plotlot.harness.tool_registry import list_tool_contracts
from plotlot.land_use.models import ToolContext

logger = logging.getLogger(__name__)

INSTRUCTIONS = (
    "PlotLot: governed land-deal intelligence. Every tool here executes through "
    "PlotLot's policy harness.\n\n"
    "HOW RESULTS ARE SHAPED — each call returns a `status` field:\n"
    "  ok                -> `result` holds the tool output; cite it verbatim.\n"
    "  pending_approval  -> a human must approve before this runs. Report the "
    "`approval_id` and stop; do NOT retry or work around it.\n"
    "  blocked           -> policy refused (budget exhausted or live network "
    "disabled). Report `message` honestly.\n"
    "  error/unavailable -> report the failure; never substitute a guess.\n\n"
    "GROUNDING RULES (strict):\n"
    "1. Report ONLY values present in tool output. Never invent zoning codes, "
    "dimensional standards, fees, comps, owners, or citations.\n"
    "2. analyze_property is the grounded engine — prefer it for any question "
    "about units, valuation, or feasibility, and repeat its numbers exactly.\n"
    "3. Use `calculate` for arithmetic instead of computing mentally.\n"
    "4. A verification field marked provisional must be presented as "
    "provisional, never as firm.\n"
    "5. If a value is absent, say it is not available and offer the tool that "
    "would retrieve it — do not fill the gap from general knowledge."
)


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", ""}


def _build_context() -> ToolContext:
    """Per-call execution context. Each call is its own run for audit purposes."""
    approvals = {
        a.strip() for a in os.environ.get("PLOTLOT_MCP_APPROVALS", "").split(",") if a.strip()
    }
    try:
        budget = int(os.environ.get("PLOTLOT_MCP_BUDGET_CENTS", "1000"))
    except ValueError:
        budget = 1000
    return ToolContext(
        workspace_id=os.environ.get("PLOTLOT_MCP_WORKSPACE", "mcp") or "mcp",
        actor_user_id=os.environ.get("PLOTLOT_MCP_ACTOR", "mcp-client") or "mcp-client",
        run_id=str(uuid.uuid4()),
        risk_budget_cents=budget,
        live_network_allowed=_env_flag("PLOTLOT_MCP_LIVE_NETWORK", True),
        approved_approval_ids=approvals,
    )


def _make_handler(tool_name: str):
    """Bind one registry tool to a governed MCP callable.

    Built in a factory so each closure captures its own `tool_name` rather than
    the loop variable.
    """

    async def handler(**kwargs: Any) -> dict[str, Any]:
        runtime = get_default_runtime()
        result = await runtime.call_tool(
            tool_name=tool_name,
            tool_args=kwargs,
            context=_build_context(),
        )
        payload: dict[str, Any] = {
            "status": result.status,
            "tool_name": result.tool_name,
            "policy_reason": result.decision.reason,
        }
        if result.result is not None:
            payload["result"] = result.result
        if result.message:
            payload["message"] = result.message
        if result.decision.approval_required:
            payload["approval_id"] = result.decision.approval_id
            payload["next_step"] = (
                "A human must approve this action. Report the approval_id and stop."
            )
        return payload

    return handler


def build_server() -> fastmcp.FastMCP:
    """Create the MCP server with every governed tool that has a handler."""
    server = fastmcp.FastMCP(name="plotlot-harness", instructions=INSTRUCTIONS, version="1.0.0")
    runtime = get_default_runtime()

    registered = 0
    for contract in list_tool_contracts():
        if not runtime.has_handler(contract.name):
            # A contract without a handler would fail every call; don't advertise it.
            continue
        server.add_tool(
            FunctionTool(
                name=contract.name,
                description=f"[{contract.risk_class}] {contract.description}",
                parameters=contract.input_schema,
                fn=_make_handler(contract.name),
            )
        )
        registered += 1

    logger.info("PlotLot governed MCP server exposing %d tools", registered)
    return server


def run() -> None:
    """Start the governed MCP server over stdio."""
    # stdout is the MCP transport — logs must never be written there.
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    build_server().run()


if __name__ == "__main__":
    run()
