"""The harness risk budget must be a ledger, not a per-call ceiling.

`ToolPolicy` compares one tool's cost against `context.risk_budget_cents`. Nothing
ever decremented that value, so a run authorised with 100c could call a 25c
EXPENSIVE_READ tool an unlimited number of times — each call passed the same
comparison against the same untouched budget. `HarnessRuntime` now keeps a
per-run spend ledger and hands the policy the remaining balance.
"""

from __future__ import annotations

import pytest

from plotlot.harness.runtime import HarnessRuntime
from plotlot.harness.tool_registry import get_tool_contract
from plotlot.land_use.models import ToolContext

# analyze_property is EXPENSIVE_READ at 25c; geocode_address is READ_ONLY at 0c.
EXPENSIVE_TOOL = "analyze_property"
FREE_TOOL = "geocode_address"


def _ctx(run_id: str = "run-1", *, budget: int = 100) -> ToolContext:
    return ToolContext(
        workspace_id="ws-1",
        actor_user_id="user-1",
        run_id=run_id,
        risk_budget_cents=budget,
        live_network_allowed=True,
    )


def _runtime() -> HarnessRuntime:
    rt = HarnessRuntime()

    async def _ok(args: dict, context: ToolContext) -> dict:
        return {"status": "success"}

    rt.register(EXPENSIVE_TOOL, _ok)
    rt.register(FREE_TOOL, _ok)
    return rt


def test_expensive_tool_costs_what_its_contract_says():
    assert get_tool_contract(EXPENSIVE_TOOL).budget_cents == 25
    assert get_tool_contract(FREE_TOOL).budget_cents == 0


@pytest.mark.asyncio
async def test_repeated_expensive_calls_exhaust_the_run_budget():
    """The regression. A 100c budget buys four 25c calls, not unlimited calls."""
    rt = _runtime()
    ctx = _ctx(budget=100)

    for i in range(4):
        result = await rt.call_tool(tool_name=EXPENSIVE_TOOL, tool_args={}, context=ctx)
        assert result.status == "ok", f"call {i + 1} should be within budget"

    assert rt.spent_cents("run-1") == 100

    fifth = await rt.call_tool(tool_name=EXPENSIVE_TOOL, tool_args={}, context=ctx)
    assert fifth.status == "pending_approval"
    assert fifth.decision.allowed is False
    assert "risk budget" in (fifth.message or "")


@pytest.mark.asyncio
async def test_read_only_tools_are_free_and_never_exhaust_the_budget():
    rt = _runtime()
    ctx = _ctx(budget=25)
    for _ in range(50):
        assert (await rt.call_tool(tool_name=FREE_TOOL, tool_args={}, context=ctx)).status == "ok"
    assert rt.spent_cents("run-1") == 0
    # The one expensive call the budget does cover is still available.
    assert (await rt.call_tool(tool_name=EXPENSIVE_TOOL, tool_args={}, context=ctx)).status == "ok"


@pytest.mark.asyncio
async def test_spend_is_scoped_per_run():
    """One run exhausting its budget must not block an unrelated run."""
    rt = _runtime()
    exhausted = _ctx("run-a", budget=25)
    assert (
        await rt.call_tool(tool_name=EXPENSIVE_TOOL, tool_args={}, context=exhausted)
    ).status == "ok"
    blocked = await rt.call_tool(tool_name=EXPENSIVE_TOOL, tool_args={}, context=exhausted)
    assert blocked.status == "pending_approval"

    fresh = _ctx("run-b", budget=25)
    assert (
        await rt.call_tool(tool_name=EXPENSIVE_TOOL, tool_args={}, context=fresh)
    ).status == "ok"
    assert rt.spent_cents("run-a") == 25
    assert rt.spent_cents("run-b") == 25


@pytest.mark.asyncio
async def test_a_failing_handler_still_charges_the_run():
    """The provider call may have happened before the handler raised. Charging only
    on success would let a failing expensive tool be retried without limit."""
    rt = HarnessRuntime()

    async def _boom(args: dict, context: ToolContext) -> dict:
        raise RuntimeError("provider exploded")

    rt.register(EXPENSIVE_TOOL, _boom)
    result = await rt.call_tool(tool_name=EXPENSIVE_TOOL, tool_args={}, context=_ctx(budget=100))
    assert result.status == "error"
    assert rt.spent_cents("run-1") == 25


@pytest.mark.asyncio
async def test_blocked_and_unknown_calls_are_not_charged():
    """Nothing executed, so nothing was spent."""
    rt = _runtime()
    ctx = _ctx(budget=0)  # cannot afford a 25c tool

    blocked = await rt.call_tool(tool_name=EXPENSIVE_TOOL, tool_args={}, context=ctx)
    assert blocked.status == "pending_approval"

    unknown = await rt.call_tool(tool_name="no_such_tool", tool_args={}, context=ctx)
    assert unknown.status == "unknown_tool"

    assert rt.spent_cents("run-1") == 0


@pytest.mark.asyncio
async def test_an_approved_call_still_records_its_spend():
    """Approval overrides the budget CHECK; it does not make the call free. The
    ledger tracks money actually spent, so a later unapproved call sees the truth."""
    rt = _runtime()
    approval_id = f"apr_run-1_{EXPENSIVE_TOOL}"
    ctx = ToolContext(
        workspace_id="ws-1",
        actor_user_id="user-1",
        run_id="run-1",
        risk_budget_cents=0,
        live_network_allowed=True,
        approved_approval_ids={approval_id},
    )
    result = await rt.call_tool(
        tool_name=EXPENSIVE_TOOL, tool_args={}, context=ctx, approval_id=approval_id
    )
    assert result.status == "ok"
    assert rt.spent_cents("run-1") == 25
