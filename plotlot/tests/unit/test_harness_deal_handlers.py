"""Tests for the deterministic deal-analysis harness handlers.

These four handlers (analyze_property, calculate, analyze_upzoning,
screen_properties) are the pure cores of chat's `_execute_*` tools, registered
in the default runtime so chat/REST/MCP share one governed execution path.
Parity with the chat `_execute_*` output shape is load-bearing: the chat echo
builders and active-analysis context read these exact payloads.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from plotlot.harness.default_runtime import (
    _handle_analyze_property,
    _handle_analyze_upzoning,
    _handle_calculate,
    _handle_screen_properties,
    build_default_runtime,
)
from plotlot.harness.runtime import HarnessRuntime
from plotlot.harness.tool_registry import tool_exists
from plotlot.land_use.models import ToolContext


def _ctx(**overrides) -> ToolContext:
    defaults = dict(
        workspace_id="ws_test",
        actor_user_id="user_test",
        run_id="run_test",
        risk_budget_cents=0,
        approved_approval_ids=set(),
    )
    defaults.update(overrides)
    return ToolContext(**defaults)


# ---------------------------------------------------------------------------
# Registration: every deal-tool contract has a registered handler
# ---------------------------------------------------------------------------


def test_deal_tools_are_registered_with_contracts():
    runtime = build_default_runtime()
    for name in ("analyze_property", "calculate", "analyze_upzoning", "screen_properties"):
        assert tool_exists(name), f"{name} has no tool contract"
        assert runtime.has_handler(name), f"{name} has no registered handler"


def test_every_tool_contract_has_a_registered_handler():
    """A contract without a handler is an ungoverned gap: the tool is advertised
    (OpenAPI/MCP tools list) but unreachable through the runtime, so transports
    fall back to bespoke execution with no policy/evidence/audit. That exact gap
    is how analyze_property/calculate/analyze_upzoning/screen_properties ran
    ungoverned in chat."""

    from plotlot.harness.tool_registry import list_tool_contracts

    runtime = build_default_runtime()
    missing = [c.name for c in list_tool_contracts() if not runtime.has_handler(c.name)]
    assert not missing, f"tool contracts without a registered handler: {missing}"


# ---------------------------------------------------------------------------
# calculate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_calculate_success_and_whole_number_rendering():
    result = await _handle_calculate({"expression": "7 * 750000"}, _ctx())
    assert result == {"status": "success", "expression": "7 * 750000", "result": 5250000}
    assert isinstance(result["result"], int)

    fractional = await _handle_calculate({"expression": "10 / 3"}, _ctx())
    assert fractional["status"] == "success"
    assert fractional["result"] == round(10 / 3, 4)


@pytest.mark.asyncio
async def test_calculate_rejects_non_arithmetic():
    result = await _handle_calculate({"expression": "__import__('os')"}, _ctx())
    assert result["status"] == "error"
    assert "expression" in result


@pytest.mark.asyncio
async def test_calculate_parity_with_chat_execute():
    from plotlot.api.chat import _execute_calculate

    for expression in ("6489 / 900", "2 ** 10", "(1 + 2) * 3.5", "not math"):
        chat_payload = json.loads(_execute_calculate(expression))
        handler_payload = await _handle_calculate({"expression": expression}, _ctx())
        assert handler_payload == chat_payload


# ---------------------------------------------------------------------------
# analyze_upzoning
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_upzoning_requires_positive_lot_sqft():
    result = await _handle_analyze_upzoning({"lot_sqft": 0}, _ctx())
    assert result["status"] == "error"
    assert "lot_sqft" in result["message"]


@pytest.mark.asyncio
async def test_analyze_upzoning_parity_with_chat_execute():
    from plotlot.api.chat import _execute_analyze_upzoning

    args = {
        "lot_sqft": 21780.0,
        "value_per_lot": 90000,
        "purchase_price": 628000,
        "entitlement_soft_costs": 29000,
        "baseline_yield": 5,
        "upzoned_yield": 12,
    }
    chat_payload = json.loads(_execute_analyze_upzoning(args))
    handler_payload = await _handle_analyze_upzoning(args, _ctx())
    assert handler_payload == chat_payload
    assert handler_payload["status"] == "success"
    assert handler_payload["equity_created"] == chat_payload["equity_created"]


# ---------------------------------------------------------------------------
# analyze_property
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_property_requires_address():
    result = await _handle_analyze_property({"address": "   "}, _ctx())
    assert result == {"status": "error", "message": "An address is required."}


@pytest.mark.asyncio
async def test_analyze_property_returns_grounded_payload_unmodified():
    grounded = {"status": "success", "address": "1233 Hueneme St", "by_right": {"max_units": 7}}
    fake_report = SimpleNamespace(property_record=None)
    with (
        patch(
            "plotlot.pipeline.analyze.analyze_property_deep",
            new=AsyncMock(return_value=fake_report),
        ),
        # Patched where it now lives: the formatter moved to the pipeline layer so
        # the harness no longer imports the chat API module to serve MCP/CLI calls.
        patch("plotlot.pipeline.grounding._format_grounded_analysis", return_value=grounded) as fmt,
    ):
        result = await _handle_analyze_property({"address": "1233 Hueneme St"}, _ctx())

    fmt.assert_called_once_with(fake_report)
    # The flat payload IS the tool result — no re-nesting, so the chat echo
    # builders and session cache read the same shape as the legacy path.
    assert result == grounded


@pytest.mark.asyncio
async def test_analyze_property_not_found_and_error_paths():
    with patch(
        "plotlot.pipeline.analyze.analyze_property_deep",
        new=AsyncMock(return_value=None),
    ):
        result = await _handle_analyze_property({"address": "nowhere"}, _ctx())
    assert result["status"] == "not_found"

    with patch(
        "plotlot.pipeline.analyze.analyze_property_deep",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        result = await _handle_analyze_property({"address": "nowhere"}, _ctx())
    assert result["status"] == "error"
    assert "Analysis failed" in result["message"]


# ---------------------------------------------------------------------------
# screen_properties
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_screen_properties_requires_addresses():
    result = await _handle_screen_properties({"addresses": []}, _ctx())
    assert result["status"] == "error"


@pytest.mark.asyncio
async def test_screen_properties_returns_ranked_rows():
    qualified = SimpleNamespace(
        address="1233 Hueneme St",
        max_units=7,
        max_land_price=519000.4,
        zoning_district="RM-3-7",
        county="San Diego",
        state="CA",
        offer_is_provisional=False,
    )
    rejected = SimpleNamespace(address="2 Bad Rd", reasons=["below min_units"])
    batch = SimpleNamespace(
        total=2,
        qualified_count=1,
        qualified=[qualified],
        rejected=[rejected],
        errors=[],
    )
    with patch(
        "plotlot.pipeline.screening.screen_addresses",
        new=AsyncMock(return_value=batch),
    ):
        result = await _handle_screen_properties(
            {"addresses": ["1233 Hueneme St", "2 Bad Rd"]}, _ctx()
        )

    assert result["status"] == "success"
    assert result["qualified_count"] == 1
    assert result["qualified"][0]["max_land_price"] == 519000
    assert result["rejected_sample"] == [{"address": "2 Bad Rd", "reasons": ["below min_units"]}]
    assert "grounding_note" in result


# ---------------------------------------------------------------------------
# Governance: analyze_property is EXPENSIVE_READ (25¢) — it runs a ~minute
# pipeline of live geocode/GIS/LLM calls, so default-context (zero-budget,
# no-live-network) REST/MCP callers must be fail-closed. Chat's defaults
# (100¢ budget, live network on) still auto-run it.
# ---------------------------------------------------------------------------


def test_analyze_property_contract_is_expensive_read():
    from plotlot.harness.tool_registry import get_tool_contract

    contract = get_tool_contract("analyze_property")
    assert contract.risk_class == "expensive_read"
    assert contract.budget_cents == 25


@pytest.mark.asyncio
async def test_analyze_property_blocked_without_live_network():
    runtime = build_default_runtime()
    result = await runtime.call_tool(
        tool_name="analyze_property",
        tool_args={"address": "1233 Hueneme St"},
        context=_ctx(live_network_allowed=False, risk_budget_cents=100),
    )
    assert result.status == "blocked"


@pytest.mark.asyncio
async def test_analyze_property_requires_budget_or_approval():
    runtime = build_default_runtime()
    result = await runtime.call_tool(
        tool_name="analyze_property",
        tool_args={"address": "1233 Hueneme St"},
        context=_ctx(live_network_allowed=True, risk_budget_cents=0),
    )
    assert result.status == "pending_approval"
    assert result.decision.approval_id is not None


@pytest.mark.asyncio
async def test_analyze_property_executes_within_chat_default_budget():
    async def stub_handler(args, context):
        return {"status": "success", "by_right": {"max_units": 7}}

    runtime = HarnessRuntime(handlers={"analyze_property": stub_handler})
    result = await runtime.call_tool(
        tool_name="analyze_property",
        tool_args={"address": "1233 Hueneme St"},
        # Chat's ChatRequest defaults: risk_budget_cents=100, live_network_allowed=True.
        context=_ctx(live_network_allowed=True, risk_budget_cents=100),
    )
    assert result.status == "ok"


# ---------------------------------------------------------------------------
# Governance: screening is EXPENSIVE_READ and now sits behind the policy gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_screen_properties_blocked_without_live_network():
    runtime = build_default_runtime()
    result = await runtime.call_tool(
        tool_name="screen_properties",
        tool_args={"addresses": ["x"]},
        context=_ctx(live_network_allowed=False, risk_budget_cents=100),
    )
    assert result.status == "blocked"


@pytest.mark.asyncio
async def test_screen_properties_requires_budget_or_approval():
    runtime = build_default_runtime()
    result = await runtime.call_tool(
        tool_name="screen_properties",
        tool_args={"addresses": ["x"]},
        context=_ctx(live_network_allowed=True, risk_budget_cents=0),
    )
    assert result.status == "pending_approval"
    assert result.decision.approval_id is not None


@pytest.mark.asyncio
async def test_screen_properties_executes_within_budget():
    async def stub_handler(args, context):
        return {"status": "success", "qualified": []}

    runtime = HarnessRuntime(handlers={"screen_properties": stub_handler})
    result = await runtime.call_tool(
        tool_name="screen_properties",
        tool_args={"addresses": ["x"]},
        context=_ctx(live_network_allowed=True, risk_budget_cents=50),
    )
    assert result.status == "ok"
    assert result.result == {"status": "success", "qualified": []}
