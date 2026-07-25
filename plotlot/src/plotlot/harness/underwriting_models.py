from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field

from plotlot.harness.contracts.base import HarnessContract


class GoNoGoSignal(StrEnum):
    GO = "go"
    NO_GO = "no_go"
    REVIEW = "review"


class CostGroup(StrEnum):
    HARD = "hard"
    SOFT = "soft"


class AsBuiltValueInput(HarnessContract):
    unit_count: int = Field(ge=0)
    monthly_rent_per_unit: float = Field(ge=0)
    vacancy_pct: float = Field(ge=0, le=1)
    operating_expense_pct: float = Field(ge=0, le=1)
    cap_rate: float = Field(gt=0, le=1)


class AsBuiltValueResult(HarnessContract):
    calculation_type: Literal["noi_valuation"] = "noi_valuation"
    formula_version: Literal["noi_valuation.v1"] = "noi_valuation.v1"
    gross_scheduled_income: float
    effective_gross_income: float
    operating_expenses: float
    annual_noi: float
    as_built_value: float
    warnings: list[str] = Field(default_factory=list)


class ProFormaInput(HarnessContract):
    state: str = Field(min_length=2, max_length=32)
    county: str = Field(default="", min_length=0, max_length=128)
    max_units: int = Field(gt=0)
    adv_per_unit: float | None = Field(default=None, ge=0)
    estimated_land_value: float | None = Field(default=None, ge=0)
    construction_cost_psf: float | None = Field(default=None, gt=0)
    avg_unit_size_sqft: float | None = Field(default=None, gt=0)
    soft_cost_pct: float | None = Field(default=None, ge=0)
    builder_margin_pct: float | None = Field(default=None, ge=0)
    impact_fees_per_unit: float | None = Field(default=None, ge=0)


class ProFormaResult(HarnessContract):
    calculation_type: Literal["pro_forma"] = "pro_forma"
    formula_version: Literal["pro_forma.v1"] = "pro_forma.v1"
    gross_development_value: float
    hard_costs: float
    soft_costs: float
    builder_margin: float
    impact_fees: float
    impact_fees_per_unit: float
    max_supportable_land_price: float
    cost_per_door: float
    construction_cost_psf: float
    avg_unit_size_sqft: float
    adv_per_unit: float
    max_units: int
    soft_cost_pct: float
    builder_margin_pct: float
    adv_source: str
    market: str
    notes: list[str] = Field(default_factory=list)


class ResidualLandValueInput(HarnessContract):
    as_built_value: float = Field(ge=0)
    desired_profit: float = Field(ge=0)
    hard_costs: float = Field(ge=0)
    soft_costs: float = Field(ge=0)
    contingency: float = Field(ge=0)
    developer_fee: float = Field(ge=0)
    closing_costs: float = Field(ge=0)
    financing_costs: float = Field(ge=0)
    holding_costs: float = Field(ge=0)
    selling_costs: float = Field(ge=0)
    asking_price: float | None = Field(default=None, ge=0)


class ResidualLandValueResult(HarnessContract):
    calculation_type: Literal["residual_land_value"] = "residual_land_value"
    formula_version: Literal["residual_land_value.v1"] = "residual_land_value.v1"
    total_project_costs_excluding_land: float
    max_supportable_land_price: float
    spread_to_asking_price: float | None
    go_no_go_signal: GoNoGoSignal
    warnings: list[str] = Field(default_factory=list)


class BRRRRRefinanceInput(HarnessContract):
    total_project_cost: float = Field(ge=0)
    stabilized_value: float = Field(ge=0)
    refinance_ltv: float = Field(ge=0, le=1)
    annual_interest_rate: float = Field(ge=0, le=1)
    amortization_years: int = Field(gt=0)
    annual_noi: float = Field(ge=0)
    cash_in_deal: float = Field(ge=0)


class BRRRRRefinanceResult(HarnessContract):
    calculation_type: Literal["brrrr_refinance"] = "brrrr_refinance"
    formula_version: Literal["brrrr_refinance.v1"] = "brrrr_refinance.v1"
    refinance_proceeds: float
    cash_left_in_deal: float
    annual_debt_service: float
    dscr: float | None
    cash_on_cash: float | None
    monthly_cash_flow: float
    warnings: list[str] = Field(default_factory=list)


class FeasibilityInput(HarnessContract):
    lot_area_sf: float = Field(gt=0)
    max_far: float | None = Field(default=None, gt=0)
    max_units: int | None = Field(default=None, ge=0)
    lot_frontage_ft: float | None = Field(default=None, gt=0)
    lot_depth_ft: float | None = Field(default=None, gt=0)
    setback_front_ft: float | None = Field(default=None, ge=0)
    setback_side_ft: float | None = Field(default=None, ge=0)
    setback_rear_ft: float | None = Field(default=None, ge=0)
    max_lot_coverage_pct: float | None = Field(default=None, gt=0, le=100)
    efficiency_factor: float = Field(gt=0, le=1)
    avg_unit_size_sf: float = Field(gt=0)
    parking_spaces_per_unit: float = Field(default=0, ge=0)


class FeasibilityResult(HarnessContract):
    calculation_type: Literal["feasibility"] = "feasibility"
    formula_version: Literal["feasibility.v2"] = "feasibility.v2"
    max_gross_buildable_sf: float
    net_rentable_sf: float
    estimated_units: int
    parking_required: int
    major_constraints: list[str]
    area_limiters: list[str] = Field(default_factory=list)
    lot_depth_ft: float | None = None
    buildable_envelope_sf: float | None = None
    lot_coverage_limited_sf: float | None = None
    feasibility_warnings: list[str] = Field(default_factory=list)


class ConstructionBudgetLineItem(HarnessContract):
    name: str = Field(min_length=1)
    group: CostGroup
    amount: float = Field(ge=0)


class ConstructionBudgetInput(HarnessContract):
    line_items: list[ConstructionBudgetLineItem] = Field(min_length=1)
    contingency_pct: float = Field(ge=0, le=1)
    developer_fee_pct: float = Field(ge=0, le=1)


class ConstructionBudgetGroups(HarnessContract):
    hard: float
    soft: float


class ConstructionBudgetResult(HarnessContract):
    calculation_type: Literal["construction_budget"] = "construction_budget"
    formula_version: Literal["construction_budget.v1"] = "construction_budget.v1"
    hard_costs: float
    soft_costs: float
    contingency: float
    developer_fee: float
    total_budget: float
    budget_by_group: ConstructionBudgetGroups
    warnings: list[str] = Field(default_factory=list)


class SensitivityInput(HarnessContract):
    base: ResidualLandValueInput
    value_adjustments_pct: list[float] = Field(default_factory=lambda: [-0.1, 0, 0.1], min_length=1)
    cost_adjustments_pct: list[float] = Field(default_factory=lambda: [-0.1, 0, 0.1], min_length=1)


class SensitivityCase(HarnessContract):
    value_adjustment_pct: float
    cost_adjustment_pct: float
    max_supportable_land_price: float


class SensitivityResult(HarnessContract):
    calculation_type: Literal["sensitivity"] = "sensitivity"
    formula_version: Literal["sensitivity.v1"] = "sensitivity.v1"
    cases: list[SensitivityCase]
    base_case: SensitivityCase
    downside_case: SensitivityCase
    upside_case: SensitivityCase
