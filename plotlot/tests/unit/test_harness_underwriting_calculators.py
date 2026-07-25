from __future__ import annotations

import pytest

from plotlot.harness.underwriting_calculators import (
    run_brrrr_refinance_analysis,
    run_construction_budget,
    run_feasibility,
    run_noi_valuation,
    run_pro_forma,
    run_residual_land_value,
    run_sensitivity_analysis,
)
from plotlot.harness.underwriting_models import (
    AsBuiltValueInput,
    BRRRRRefinanceInput,
    ConstructionBudgetInput,
    ConstructionBudgetLineItem,
    FeasibilityInput,
    ProFormaInput,
    ResidualLandValueInput,
    SensitivityInput,
)


def test_noi_valuation_calculates_as_built_value() -> None:
    # Given: a four-unit rental program with explicit income and cap-rate assumptions.
    request = AsBuiltValueInput(
        unit_count=4,
        monthly_rent_per_unit=2500,
        vacancy_pct=0.05,
        operating_expense_pct=0.35,
        cap_rate=0.06,
    )

    # When: the deterministic NOI valuation runs.
    result = run_noi_valuation(request)

    # Then: every output is derived from the typed inputs and formula version.
    assert result.calculation_type == "noi_valuation"
    assert result.gross_scheduled_income == 120_000
    assert result.effective_gross_income == 114_000
    assert result.operating_expenses == 39_900
    assert result.annual_noi == 74_100
    assert result.as_built_value == 1_235_000


def test_residual_land_value_compares_against_asking_price() -> None:
    # Given: a stabilized value, explicit project costs, profit, and asking price.
    request = ResidualLandValueInput(
        as_built_value=1_235_000,
        desired_profit=150_000,
        hard_costs=600_000,
        soft_costs=90_000,
        contingency=60_000,
        developer_fee=30_000,
        closing_costs=15_000,
        financing_costs=40_000,
        holding_costs=20_000,
        selling_costs=35_000,
        asking_price=175_000,
    )

    # When: the residual land value calculator runs.
    result = run_residual_land_value(request)

    # Then: max land price and spread are reproducible and decision-ready.
    assert result.max_supportable_land_price == 195_000
    assert result.spread_to_asking_price == 20_000
    assert result.go_no_go_signal == "go"
    assert result.total_project_costs_excluding_land == 890_000


def test_pro_forma_uses_comp_signals_with_market_defaults() -> None:
    # Given: a South Florida development program with max units and comp-derived exit values.
    request = ProFormaInput(
        state="FL",
        county="Broward",
        max_units=12,
        adv_per_unit=240_000,
        estimated_land_value=210_000,
        avg_unit_size_sqft=850,
    )

    # When: the shared pro forma calculator runs.
    result = run_pro_forma(request)

    # Then: it returns a residual-style max land price using the shared market defaults.
    assert result.calculation_type == "pro_forma"
    assert result.formula_version == "pro_forma.v1"
    assert result.market == "South Florida"
    assert result.max_units == 12
    assert result.adv_source == "override"
    assert result.gross_development_value == 2_880_000
    assert result.hard_costs == 2_295_000
    assert result.soft_costs == 459_000
    assert result.builder_margin == 720_000
    assert result.impact_fees == 300_000
    assert result.max_supportable_land_price == -894_000


def test_brrrr_refinance_calculates_dscr_and_cash_left() -> None:
    # Given: a stabilized rental refinance scenario.
    request = BRRRRRefinanceInput(
        total_project_cost=400_000,
        stabilized_value=500_000,
        refinance_ltv=0.75,
        annual_interest_rate=0.06,
        amortization_years=30,
        annual_noi=42_000,
        cash_in_deal=80_000,
    )

    # When: the BRRRR refinance calculator runs.
    result = run_brrrr_refinance_analysis(request)

    # Then: proceeds, remaining cash, debt service, DSCR, and cash flow are deterministic.
    assert result.refinance_proceeds == 375_000
    assert result.cash_left_in_deal == 25_000
    assert result.annual_debt_service == pytest.approx(26_979.77, abs=0.01)
    assert result.dscr == pytest.approx(1.56, abs=0.01)
    assert result.monthly_cash_flow == pytest.approx(1_251.69, abs=0.01)
    assert result.cash_on_cash == pytest.approx(0.60, abs=0.01)


def test_feasibility_calculates_units_and_parking() -> None:
    # Given: a lot, FAR, efficiency, unit size, max unit cap, and parking ratio.
    request = FeasibilityInput(
        lot_area_sf=10_000,
        max_far=1.5,
        max_units=12,
        efficiency_factor=0.85,
        avg_unit_size_sf=850,
        parking_spaces_per_unit=1.5,
    )

    # When: the feasibility calculator runs.
    result = run_feasibility(request)

    # Then: FAR area, rentable area, units, and parking are derived from inputs.
    assert result.max_gross_buildable_sf == 15_000
    assert result.net_rentable_sf == 12_750
    assert result.estimated_units == 12
    assert result.parking_required == 18
    assert result.major_constraints == ["max_units"]


def test_feasibility_uses_lot_coverage_and_setbacks_without_far() -> None:
    # Given: a single-family lot with manual frontage, setbacks, and coverage but no FAR.
    request = FeasibilityInput(
        lot_area_sf=10_105,
        max_units=1,
        lot_frontage_ft=75,
        setback_front_ft=25,
        setback_side_ft=7.5,
        setback_rear_ft=25,
        max_lot_coverage_pct=40,
        efficiency_factor=0.85,
        avg_unit_size_sf=1_700,
        parking_spaces_per_unit=2,
    )

    # When: the shared feasibility calculator runs.
    result = run_feasibility(request)

    # Then: lot coverage becomes the governing area cap and the manual unit cap still controls.
    assert result.formula_version == "feasibility.v2"
    assert result.max_gross_buildable_sf == pytest.approx(4_042, abs=0.01)
    assert result.lot_depth_ft == pytest.approx(134.73, abs=0.01)
    assert result.buildable_envelope_sf == pytest.approx(5_084.0, abs=0.01)
    assert result.lot_coverage_limited_sf == pytest.approx(4_042.0, abs=0.01)
    assert result.area_limiters == ["lot_coverage", "setback_envelope"]
    assert result.estimated_units == 1
    assert result.major_constraints == ["max_units"]


def test_feasibility_matches_miami_gardens_r1_single_family_typology() -> None:
    # Given: the Miami Gardens R-1 vacant-lot standards from the user's manual underwriting flow.
    request = FeasibilityInput(
        lot_area_sf=10_105,
        max_units=1,
        lot_frontage_ft=75,
        setback_front_ft=25,
        setback_side_ft=7.5,
        setback_rear_ft=25,
        max_lot_coverage_pct=40,
        efficiency_factor=0.85,
        avg_unit_size_sf=1_700,
        parking_spaces_per_unit=2,
    )

    # When: the shared feasibility calculator runs against that typology.
    result = run_feasibility(request)

    # Then: coverage governs the area cap while the by-right density still limits the program to one home.
    assert result.max_gross_buildable_sf == pytest.approx(4_042.0, abs=0.01)
    assert result.buildable_envelope_sf == pytest.approx(5_084.0, abs=0.01)
    assert result.net_rentable_sf == pytest.approx(3_435.7, abs=0.01)
    assert result.estimated_units == 1
    assert result.parking_required == 2
    assert result.area_limiters == ["lot_coverage", "setback_envelope"]
    assert result.major_constraints == ["max_units"]


def test_construction_budget_totals_line_items_and_reserves() -> None:
    # Given: hard and soft cost line items with percentage reserves.
    request = ConstructionBudgetInput(
        line_items=[
            ConstructionBudgetLineItem(name="site work", group="hard", amount=50_000),
            ConstructionBudgetLineItem(name="vertical", group="hard", amount=100_000),
            ConstructionBudgetLineItem(name="architecture", group="soft", amount=25_000),
        ],
        contingency_pct=0.10,
        developer_fee_pct=0.03,
    )

    # When: the construction budget calculator runs.
    result = run_construction_budget(request)

    # Then: budget groups, contingency, fee, and total are deterministic.
    assert result.hard_costs == 150_000
    assert result.soft_costs == 25_000
    assert result.contingency == 15_000
    assert result.developer_fee == 5_250
    assert result.total_budget == 195_250


def test_sensitivity_analysis_generates_base_case_grid() -> None:
    # Given: a residual valuation base case and explicit value/cost shocks.
    request = SensitivityInput(
        base=ResidualLandValueInput(
            as_built_value=1_000_000,
            desired_profit=100_000,
            hard_costs=500_000,
            soft_costs=80_000,
            contingency=50_000,
            developer_fee=20_000,
            closing_costs=10_000,
            financing_costs=30_000,
            holding_costs=15_000,
            selling_costs=25_000,
        ),
        value_adjustments_pct=[-0.05, 0, 0.05],
        cost_adjustments_pct=[-0.10, 0, 0.10],
    )

    # When: the sensitivity calculator runs.
    result = run_sensitivity_analysis(request)

    # Then: it produces all cases and identifies downside, base, and upside outputs.
    assert len(result.cases) == 9
    assert result.base_case.max_supportable_land_price == 170_000
    assert result.downside_case.max_supportable_land_price == 47_000
    assert result.upside_case.max_supportable_land_price == 293_000


def test_sensitivity_analysis_keeps_base_case_when_grid_omits_zero() -> None:
    # Given: a sensitivity grid with no neutral case.
    request = SensitivityInput(
        base=ResidualLandValueInput(
            as_built_value=1_000_000,
            desired_profit=100_000,
            hard_costs=500_000,
            soft_costs=80_000,
            contingency=50_000,
            developer_fee=20_000,
            closing_costs=10_000,
            financing_costs=30_000,
            holding_costs=15_000,
            selling_costs=25_000,
        ),
        value_adjustments_pct=[-0.05, 0.05],
        cost_adjustments_pct=[-0.10, 0.10],
    )

    # When: sensitivity analysis runs.
    result = run_sensitivity_analysis(request)

    # Then: base case remains the actual unadjusted residual, not a zero fallback.
    assert len(result.cases) == 4
    assert result.base_case.max_supportable_land_price == 170_000
