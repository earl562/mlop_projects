"""Behavioral tests for transport-neutral core decision tools."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from plotlot.core.types import (
    CompAnalysis,
    DensityAnalysis,
    ExtractionVerification,
    LandProForma,
    PropertyRecord,
    ZoningReport,
)
from plotlot.harness.core_decision_tools import (
    MAX_SCREEN_ADDRESSES,
    handle_analyze_property,
    handle_analyze_upzoning,
    handle_calculate,
    handle_screen_properties,
)
from plotlot.land_use import ToolContext


def _context(*, budget_cents: int = 0) -> ToolContext:
    return ToolContext(
        workspace_id="ws_test",
        actor_user_id="user_test",
        run_id="run_test",
        risk_budget_cents=budget_cents,
        approved_approval_ids=set(),
    )


def _report(
    address: str,
    *,
    max_units: int = 4,
    max_land_price: float = 700_000,
    provisional: bool = False,
) -> ZoningReport:
    return ZoningReport(
        address=address,
        formatted_address=f"{address}, Charlotte, NC",
        municipality="Charlotte",
        county="Mecklenburg",
        state="NC",
        zoning_district="N1-C",
        zoning_description="Neighborhood 1",
        property_record=PropertyRecord(
            address=address,
            municipality="Charlotte",
            county="Mecklenburg",
            owner="Example Owner LLC",
            lot_size_sqft=10_000,
            lot_size_source="assessor",
        ),
        density_analysis=DensityAnalysis(
            max_units=max_units,
            governing_constraint="min_lot_area",
            constraints=[],
            confidence="high",
            origin="local_authority",
        ),
        extraction_verification=ExtractionVerification(
            overall="verified" if not provisional else "partial",
            offer_is_provisional=provisional,
        ),
        comp_analysis=CompAnalysis(
            estimated_land_value=500_000,
            estimated_land_value_low=450_000,
            estimated_land_value_high=550_000,
            adv_per_unit=650_000,
            adv_source="comps",
        ),
        pro_forma=LandProForma(
            gross_development_value=2_600_000,
            max_land_price=max_land_price,
            impact_fees_per_unit=20_000,
            adv_per_unit=650_000,
            max_units=max_units,
            adv_source="comps",
            market="Charlotte",
        ),
        sources=["Charlotte UDO"],
        confidence="high",
    )


@pytest.mark.asyncio
async def test_handle_calculate_returns_clean_whole_number():
    result = await handle_calculate({"expression": "12 * 450000"}, _context())

    assert result == {
        "status": "success",
        "expression": "12 * 450000",
        "result": 5_400_000,
    }


@pytest.mark.asyncio
async def test_handle_calculate_rejects_non_arithmetic_expression():
    expression = "__import__('os').system('id')"

    result = await handle_calculate({"expression": expression}, _context())

    assert result["status"] == "error"
    assert result["expression"] == expression
    assert "arithmetic" in result["message"].lower()


@pytest.mark.asyncio
async def test_handle_analyze_upzoning_prices_only_supplied_scenario_inputs():
    result = await handle_analyze_upzoning(
        {
            "lot_sqft": 20_000,
            "value_per_lot": 300_000,
            "purchase_price": 500_000,
            "entitlement_soft_costs": 50_000,
            "baseline_yield": 2,
            "upzoned_yield": 4,
            "yield_basis": "lots",
        },
        _context(),
    )

    assert result["status"] == "success"
    assert result["all_in_basis"] == 550_000
    assert result["value_source"] == "override"
    assert result["baseline"]["yield_count"] == 2
    assert result["upzoned"]["yield_count"] == 4
    assert result["value_uplift"] == 600_000
    assert result["equity_created"] == 650_000
    assert result["cost_per_yield"] == 137_500


@pytest.mark.asyncio
async def test_handle_analyze_upzoning_requires_positive_lot_area():
    result = await handle_analyze_upzoning({"lot_sqft": 0}, _context())

    assert result == {
        "status": "error",
        "message": "A positive lot_sqft is required for upzoning analysis.",
    }


@pytest.mark.asyncio
async def test_handle_analyze_property_serializes_grounded_decision_fields(monkeypatch):
    report = _report("123 Main St")
    analyze = AsyncMock(return_value=report)
    monkeypatch.setattr("plotlot.pipeline.analyze.analyze_property_deep", analyze)

    result = await handle_analyze_property({"address": "123 Main St"}, _context())

    analyze.assert_awaited_once_with("123 Main St")
    assert result["status"] == "success"
    assert result["address"] == "123 Main St, Charlotte, NC"
    assert result["zoning_code"] == "N1-C"
    assert result["owner"] == "Example Owner LLC"
    assert result["lot_size_sqft"] == 10_000
    assert result["lot_size_source"] == "assessor"
    assert result["by_right"]["max_units"] == 4
    assert result["by_right"]["verification"] == "verified"
    assert result["by_right"]["offer_is_provisional"] is False
    assert result["valuation"]["max_land_price_residual"] == 700_000
    assert result["valuation"]["adv_per_unit"] == 650_000
    assert result["sources"] == ["Charlotte UDO"]


@pytest.mark.asyncio
async def test_handle_analyze_property_requires_address():
    result = await handle_analyze_property({"address": " "}, _context())

    assert result == {"status": "error", "message": "An address is required."}


@pytest.mark.asyncio
async def test_handle_screen_properties_deduplicates_caps_and_ranks(monkeypatch):
    addresses = [f"{index} Test St" for index in range(MAX_SCREEN_ADDRESSES + 5)]
    requested = [addresses[0], addresses[0], *addresses[1:]]

    async def fake_analyze(address: str, *, with_comps: bool):
        assert with_comps is False
        index = int(address.split(" ", 1)[0])
        return _report(address, max_land_price=100_000 + index * 10_000)

    analyze = AsyncMock(side_effect=fake_analyze)
    monkeypatch.setattr("plotlot.pipeline.analyze.analyze_property_full", analyze)

    result = await handle_screen_properties(
        {"addresses": requested, "max_results": 500},
        _context(budget_cents=50),
    )

    assert analyze.await_count == MAX_SCREEN_ADDRESSES
    assert result["status"] == "success"
    assert result["screened"] == MAX_SCREEN_ADDRESSES
    assert result["qualified_count"] == MAX_SCREEN_ADDRESSES
    assert result["qualified"][0]["address"] == f"{MAX_SCREEN_ADDRESSES - 1} Test St"
    assert result["qualified"][0]["max_land_price"] == 290_000
    assert result["error_count"] == 0


@pytest.mark.asyncio
async def test_handle_screen_properties_requires_addresses():
    result = await handle_screen_properties({"addresses": []}, _context(budget_cents=50))

    assert result == {
        "status": "error",
        "message": "Provide at least one address to screen.",
    }
