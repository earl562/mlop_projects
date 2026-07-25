from __future__ import annotations

import math
from typing import assert_never

from plotlot.core.types import CompAnalysis
from plotlot.pipeline.cost_model import get_cost_model
from plotlot.pipeline.proforma import calculate_land_pro_forma
from plotlot.harness.underwriting_models import (
    AsBuiltValueInput,
    AsBuiltValueResult,
    BRRRRRefinanceInput,
    BRRRRRefinanceResult,
    ConstructionBudgetGroups,
    ConstructionBudgetInput,
    ConstructionBudgetResult,
    CostGroup,
    FeasibilityInput,
    FeasibilityResult,
    GoNoGoSignal,
    ProFormaInput,
    ProFormaResult,
    ResidualLandValueInput,
    ResidualLandValueResult,
    SensitivityCase,
    SensitivityInput,
    SensitivityResult,
)


def run_noi_valuation(request: AsBuiltValueInput) -> AsBuiltValueResult:
    gross_scheduled_income = request.unit_count * request.monthly_rent_per_unit * 12
    effective_gross_income = gross_scheduled_income * (1 - request.vacancy_pct)
    operating_expenses = effective_gross_income * request.operating_expense_pct
    annual_noi = effective_gross_income - operating_expenses
    return AsBuiltValueResult(
        gross_scheduled_income=round_money(gross_scheduled_income),
        effective_gross_income=round_money(effective_gross_income),
        operating_expenses=round_money(operating_expenses),
        annual_noi=round_money(annual_noi),
        as_built_value=round_money(annual_noi / request.cap_rate),
    )


def run_pro_forma(request: ProFormaInput) -> ProFormaResult:
    comps = CompAnalysis(
        estimated_land_value=request.estimated_land_value or 0.0,
        adv_per_unit=request.adv_per_unit,
    )
    cost_model = get_cost_model(request.state, request.county)
    result = calculate_land_pro_forma(
        comps=comps,
        max_units=request.max_units,
        adv_per_unit=request.adv_per_unit,
        cost_model=cost_model,
        construction_cost_psf=request.construction_cost_psf,
        avg_unit_size_sqft=request.avg_unit_size_sqft,
        soft_cost_pct=request.soft_cost_pct,
        builder_margin_pct=request.builder_margin_pct,
        impact_fees_per_unit=request.impact_fees_per_unit,
    )
    return ProFormaResult(
        gross_development_value=round_money(result.gross_development_value),
        hard_costs=round_money(result.hard_costs),
        soft_costs=round_money(result.soft_costs),
        builder_margin=round_money(result.builder_margin),
        impact_fees=round_money(result.impact_fees),
        impact_fees_per_unit=round_money(result.impact_fees_per_unit),
        max_supportable_land_price=round_money(result.max_land_price),
        cost_per_door=round_money(result.cost_per_door),
        construction_cost_psf=round_money(result.construction_cost_psf),
        avg_unit_size_sqft=round_money(result.avg_unit_size_sqft),
        adv_per_unit=round_money(result.adv_per_unit),
        max_units=result.max_units,
        soft_cost_pct=round_money(result.soft_cost_pct),
        builder_margin_pct=round_money(result.builder_margin_pct),
        adv_source=result.adv_source,
        market=result.market,
        notes=list(result.notes),
    )


def run_residual_land_value(request: ResidualLandValueInput) -> ResidualLandValueResult:
    total_project_costs = _residual_project_costs(request)
    max_land_price = request.as_built_value - request.desired_profit - total_project_costs
    spread = None if request.asking_price is None else max_land_price - request.asking_price
    warnings: list[str] = []
    if max_land_price < 0:
        warnings.append("Negative residual land value: costs and profit exceed as-built value.")
    return ResidualLandValueResult(
        total_project_costs_excluding_land=round_money(total_project_costs),
        max_supportable_land_price=round_money(max_land_price),
        spread_to_asking_price=None if spread is None else round_money(spread),
        go_no_go_signal=_go_no_go_signal(max_land_price, request.asking_price),
        warnings=warnings,
    )


def run_brrrr_refinance_analysis(request: BRRRRRefinanceInput) -> BRRRRRefinanceResult:
    refinance_proceeds = request.stabilized_value * request.refinance_ltv
    cash_left = request.total_project_cost - refinance_proceeds
    annual_debt_service = _annual_debt_service(
        principal=refinance_proceeds,
        annual_interest_rate=request.annual_interest_rate,
        amortization_years=request.amortization_years,
    )
    annual_cash_flow = request.annual_noi - annual_debt_service
    warnings: list[str] = []
    if cash_left <= 0:
        warnings.append("Refinance proceeds recover all project cost before reserves and closing friction.")
    return BRRRRRefinanceResult(
        refinance_proceeds=round_money(refinance_proceeds),
        cash_left_in_deal=round_money(cash_left),
        annual_debt_service=round_money(annual_debt_service),
        dscr=None if annual_debt_service == 0 else round(request.annual_noi / annual_debt_service, 4),
        cash_on_cash=None if cash_left <= 0 else round(annual_cash_flow / cash_left, 4),
        monthly_cash_flow=round_money(annual_cash_flow / 12),
        warnings=warnings,
    )


def run_feasibility(request: FeasibilityInput) -> FeasibilityResult:
    warnings: list[str] = []
    area_limiters: list[tuple[str, float]] = []
    if request.max_far is not None:
        area_limiters.append(("floor_area_ratio", request.lot_area_sf * request.max_far))
    if request.max_lot_coverage_pct is not None:
        area_limiters.append(
            ("lot_coverage", request.lot_area_sf * (request.max_lot_coverage_pct / 100.0))
        )
    lot_depth = request.lot_depth_ft
    if lot_depth is None and request.lot_frontage_ft is not None and request.lot_frontage_ft > 0:
        lot_depth = request.lot_area_sf / request.lot_frontage_ft
    buildable_envelope_sf: float | None = None
    if (
        request.lot_frontage_ft is not None
        and lot_depth is not None
        and request.setback_front_ft is not None
        and request.setback_side_ft is not None
        and request.setback_rear_ft is not None
    ):
        buildable_width = max(request.lot_frontage_ft - (2 * request.setback_side_ft), 0.0)
        buildable_depth = max(lot_depth - request.setback_front_ft - request.setback_rear_ft, 0.0)
        buildable_envelope_sf = buildable_width * buildable_depth
        area_limiters.append(("setback_envelope", buildable_envelope_sf))
    elif request.lot_frontage_ft is not None and lot_depth is not None:
        warnings.append(
            "Setback envelope was not calculated because one or more setback dimensions were missing."
        )
    if not area_limiters:
        warnings.append("No FAR, lot coverage, or setback envelope supplied; buildable area is zero.")
    max_gross_buildable_sf = 0.0 if not area_limiters else min(limit for _, limit in area_limiters)
    net_rentable_sf = max_gross_buildable_sf * request.efficiency_factor
    area_units = math.floor(net_rentable_sf / request.avg_unit_size_sf)
    estimated_units = area_units
    constraints: list[str] = []
    if request.max_units is not None and request.max_units < area_units:
        estimated_units = request.max_units
        constraints.append("max_units")
    elif area_limiters:
        limiting_area = min(area_limiters, key=lambda limiter: limiter[1])[0]
        constraints.append(limiting_area)
    return FeasibilityResult(
        max_gross_buildable_sf=round_money(max_gross_buildable_sf),
        net_rentable_sf=round_money(net_rentable_sf),
        estimated_units=estimated_units,
        parking_required=math.ceil(estimated_units * request.parking_spaces_per_unit),
        major_constraints=constraints,
        area_limiters=[name for name, _ in area_limiters],
        lot_depth_ft=None if lot_depth is None else round_money(lot_depth),
        buildable_envelope_sf=None if buildable_envelope_sf is None else round_money(buildable_envelope_sf),
        lot_coverage_limited_sf=(
            None
            if request.max_lot_coverage_pct is None
            else round_money(request.lot_area_sf * (request.max_lot_coverage_pct / 100.0))
        ),
        feasibility_warnings=warnings,
    )


def run_construction_budget(request: ConstructionBudgetInput) -> ConstructionBudgetResult:
    hard_costs = 0.0
    soft_costs = 0.0
    for item in request.line_items:
        match item.group:
            case CostGroup.HARD:
                hard_costs += item.amount
            case CostGroup.SOFT:
                soft_costs += item.amount
            case unreachable:
                assert_never(unreachable)
    contingency = hard_costs * request.contingency_pct
    developer_fee = (hard_costs + soft_costs) * request.developer_fee_pct
    total_budget = hard_costs + soft_costs + contingency + developer_fee
    return ConstructionBudgetResult(
        hard_costs=round_money(hard_costs),
        soft_costs=round_money(soft_costs),
        contingency=round_money(contingency),
        developer_fee=round_money(developer_fee),
        total_budget=round_money(total_budget),
        budget_by_group=ConstructionBudgetGroups(
            hard=round_money(hard_costs),
            soft=round_money(soft_costs),
        ),
    )


def run_sensitivity_analysis(request: SensitivityInput) -> SensitivityResult:
    cases = [
        _sensitivity_case(request.base, value_adjustment, cost_adjustment)
        for value_adjustment in request.value_adjustments_pct
        for cost_adjustment in request.cost_adjustments_pct
    ]
    base_case = _sensitivity_case(request.base, 0, 0)
    return SensitivityResult(
        cases=cases,
        base_case=base_case,
        downside_case=min(cases, key=lambda case: case.max_supportable_land_price),
        upside_case=max(cases, key=lambda case: case.max_supportable_land_price),
    )


def round_money(value: float) -> float:
    return round(value, 2)


def _residual_project_costs(request: ResidualLandValueInput) -> float:
    return (
        request.hard_costs
        + request.soft_costs
        + request.contingency
        + request.developer_fee
        + request.closing_costs
        + request.financing_costs
        + request.holding_costs
        + request.selling_costs
    )


def _go_no_go_signal(max_land_price: float, asking_price: float | None) -> GoNoGoSignal:
    if asking_price is None:
        return GoNoGoSignal.REVIEW
    if max_land_price >= asking_price:
        return GoNoGoSignal.GO
    return GoNoGoSignal.NO_GO


def _annual_debt_service(
    *,
    principal: float,
    annual_interest_rate: float,
    amortization_years: int,
) -> float:
    if principal == 0:
        return 0.0
    monthly_payments = amortization_years * 12
    if annual_interest_rate == 0:
        return principal / amortization_years
    monthly_rate = annual_interest_rate / 12
    factor = (1 + monthly_rate) ** monthly_payments
    return principal * monthly_rate * factor / (factor - 1) * 12


def _sensitivity_case(
    base: ResidualLandValueInput,
    value_adjustment: float,
    cost_adjustment: float,
) -> SensitivityCase:
    result = run_residual_land_value(
        ResidualLandValueInput(
            as_built_value=base.as_built_value * (1 + value_adjustment),
            desired_profit=base.desired_profit,
            hard_costs=base.hard_costs * (1 + cost_adjustment),
            soft_costs=base.soft_costs * (1 + cost_adjustment),
            contingency=base.contingency * (1 + cost_adjustment),
            developer_fee=base.developer_fee * (1 + cost_adjustment),
            closing_costs=base.closing_costs * (1 + cost_adjustment),
            financing_costs=base.financing_costs * (1 + cost_adjustment),
            holding_costs=base.holding_costs * (1 + cost_adjustment),
            selling_costs=base.selling_costs * (1 + cost_adjustment),
            asking_price=base.asking_price,
        )
    )
    return SensitivityCase(
        value_adjustment_pct=value_adjustment,
        cost_adjustment_pct=cost_adjustment,
        max_supportable_land_price=result.max_supportable_land_price,
    )
