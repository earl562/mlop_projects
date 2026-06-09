"""Commercial & industrial interpreter skills — NOI, cap rate, CRE formulas.

Extends interpreter_skills.py with commercial real estate (CRE) analysis:
- NOI calculation (Effective Gross Income - Operating Expenses)
- Cap rate valuation (NOI / Cap Rate)
- DCF analysis (discounted cash flow over hold period)
- Industrial property analysis (floor area ratio, clear height, dock doors)
- Mixed-use analysis (residential + commercial split)

Per AutoHarness (arXiv 2603.03329): deterministic procedures as code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from plotlot.harness.interpreter_skills import ComplianceResult


# ==========================================================================
# Commercial Real Estate — NOI + Cap Rate + DCF
# ==========================================================================

@dataclass
class CommercialInputs:
    property_type: str  # office, retail, industrial, mixed_use, multifamily
    gross_sqft: float
    leasable_sqft: float
    avg_rent_per_sqft: float
    vacancy_rate: float = 0.08
    operating_expense_ratio: float = 0.35
    cap_rate: float = 0.07
    hold_years: int = 5
    exit_cap_rate: float = 0.075
    rent_growth_rate: float = 0.03
    expense_growth_rate: float = 0.025
    discount_rate: float = 0.10
    land_value: float = 0.0


def calculate_noi(inputs: CommercialInputs) -> ComplianceResult:
    """Net Operating Income: EGI - Operating Expenses."""
    potential_gross = inputs.leasable_sqft * inputs.avg_rent_per_sqft
    vacancy_loss = potential_gross * inputs.vacancy_rate
    effective_gross = potential_gross - vacancy_loss
    operating_expenses = effective_gross * inputs.operating_expense_ratio
    noi = effective_gross - operating_expenses
    cap_value = noi / inputs.cap_rate if inputs.cap_rate > 0 else 0
    return ComplianceResult(
        passed=True,
        criteria_checked=["potential_gross", "effective_gross", "operating_expenses", "noi", "cap_valuation"],
        evidence={
            "inputs": {
                "property_type": inputs.property_type,
                "gross_sqft": inputs.gross_sqft,
                "leasable_sqft": inputs.leasable_sqft,
                "avg_rent_per_sqft": inputs.avg_rent_per_sqft,
                "vacancy_rate": inputs.vacancy_rate,
                "opex_ratio": inputs.operating_expense_ratio,
                "cap_rate": inputs.cap_rate,
            },
            "outputs": {
                "potential_gross_income": round(potential_gross, 2),
                "vacancy_loss": round(vacancy_loss, 2),
                "effective_gross_income": round(effective_gross, 2),
                "operating_expenses": round(operating_expenses, 2),
                "net_operating_income": round(noi, 2),
                "cap_rate_valuation": round(cap_value, 2),
                "value_per_sqft": round(cap_value / inputs.gross_sqft, 2) if inputs.gross_sqft > 0 else 0,
            },
        },
    )


def calculate_dcf(inputs: CommercialInputs) -> ComplianceResult:
    """Discounted Cash Flow over hold period with terminal cap rate exit."""
    cash_flows: list[float] = []
    noi = inputs.leasable_sqft * inputs.avg_rent_per_sqft * (1 - inputs.vacancy_rate) * (1 - inputs.operating_expense_ratio)
    current_noi = noi
    npv = 0.0
    for year in range(1, inputs.hold_years + 1):
        current_noi *= (1 + inputs.rent_growth_rate)
        cash_flows.append(current_noi)
        npv += current_noi / ((1 + inputs.discount_rate) ** year)
    terminal_noi = current_noi * (1 + inputs.rent_growth_rate)
    terminal_value = terminal_noi / inputs.exit_cap_rate
    terminal_pv = terminal_value / ((1 + inputs.discount_rate) ** inputs.hold_years)
    total_npv = npv + terminal_pv
    return ComplianceResult(
        passed=True,
        criteria_checked=["cash_flows", "terminal_value", "npv", "total_investment_value"],
        evidence={
            "inputs": {
                "hold_years": inputs.hold_years,
                "exit_cap_rate": inputs.exit_cap_rate,
                "rent_growth": inputs.rent_growth_rate,
                "discount_rate": inputs.discount_rate,
            },
            "outputs": {
                "annual_cash_flows": [round(cf, 2) for cf in cash_flows],
                "npv_of_cash_flows": round(npv, 2),
                "terminal_value": round(terminal_value, 2),
                "terminal_present_value": round(terminal_pv, 2),
                "total_npv": round(total_npv, 2),
                "value_per_sqft": round(total_npv / inputs.gross_sqft, 2) if inputs.gross_sqft > 0 else 0,
            },
        },
    )


# ==========================================================================
# Industrial Property Analysis
# ==========================================================================

@dataclass
class IndustrialInputs:
    gross_sqft: float
    warehouse_sqft: float
    office_sqft: float
    clear_height_ft: float  # e.g. 28, 32, 36
    dock_doors: int
    drive_in_doors: int
    power_capacity_kva: int
    floor_area_ratio: float  # FAR = building_sqft / lot_sqft
    lot_sqft: float
    avg_rent_per_sqft: float
    vacancy_rate: float = 0.06
    operating_expense_ratio: float = 0.25
    cap_rate: float = 0.065


def analyze_industrial(inputs: IndustrialInputs) -> ComplianceResult:
    """Industrial property analysis with warehouse-specific metrics."""
    potential_gross = inputs.gross_sqft * inputs.avg_rent_per_sqft
    effective_gross = potential_gross * (1 - inputs.vacancy_rate)
    noi = effective_gross * (1 - inputs.operating_expense_ratio)
    cap_value = noi / inputs.cap_rate if inputs.cap_rate > 0 else 0
    warehouse_ratio = inputs.warehouse_sqft / inputs.gross_sqft if inputs.gross_sqft > 0 else 1
    office_ratio = inputs.office_sqft / inputs.gross_sqft if inputs.gross_sqft > 0 else 0
    dock_door_ratio = inputs.dock_doors / (inputs.gross_sqft / 10000) if inputs.gross_sqft > 0 else 0
    score = 0
    if inputs.clear_height_ft >= 30:
        score += 1
    if dock_door_ratio >= 1:
        score += 1
    if inputs.floor_area_ratio >= 0.4:
        score += 1
    if inputs.power_capacity_kva >= 500:
        score += 1
    return ComplianceResult(
        passed=True,
        criteria_checked=["clear_height", "dock_door_coverage", "far", "power", "warehouse_ratio"],
        evidence={
            "property": {
                "gross_sqft": inputs.gross_sqft,
                "warehouse_ratio_pct": round(warehouse_ratio * 100, 1),
                "office_ratio_pct": round(office_ratio * 100, 1),
                "clear_height_ft": inputs.clear_height_ft,
                "dock_doors": inputs.dock_doors,
                "dock_per_10k_sqft": round(dock_door_ratio, 1),
                "floor_area_ratio": inputs.floor_area_ratio,
            },
            "financial": {
                "noi": round(noi, 2),
                "cap_value": round(cap_value, 2),
                "value_per_sqft": round(cap_value / inputs.gross_sqft, 2) if inputs.gross_sqft > 0 else 0,
            },
            "quality_score": f"{score}/4",
            "institutional_grade": "YES" if score >= 3 else "NO" if score < 2 else "BORDERLINE",
        },
    )


# ==========================================================================
# Mixed-Use Analysis
# ==========================================================================

@dataclass
class MixedUseInputs:
    residential_sqft: float
    residential_units: int
    residential_rent_per_unit: float
    commercial_sqft: float
    commercial_rent_per_sqft: float
    retail_sqft: float = 0.0
    retail_rent_per_sqft: float = 0.0
    residential_vacancy: float = 0.05
    commercial_vacancy: float = 0.10
    retail_vacancy: float = 0.08
    opex_ratio: float = 0.30
    cap_rate: float = 0.065


def analyze_mixed_use(inputs: MixedUseInputs) -> ComplianceResult:
    """Mixed-use valuation: residential + commercial + retail components."""
    res_income = inputs.residential_units * inputs.residential_rent_per_unit * 12 * (1 - inputs.residential_vacancy)
    com_income = inputs.commercial_sqft * inputs.commercial_rent_per_sqft * (1 - inputs.commercial_vacancy)
    ret_income = inputs.retail_sqft * inputs.retail_rent_per_sqft * (1 - inputs.retail_vacancy)
    total_income = res_income + com_income + ret_income
    noi = total_income * (1 - inputs.opex_ratio)
    total_value = noi / inputs.cap_rate if inputs.cap_rate > 0 else 0
    total_sqft = inputs.residential_sqft + inputs.commercial_sqft + inputs.retail_sqft
    return ComplianceResult(
        passed=True,
        criteria_checked=["residential_income", "commercial_income", "retail_income", "total_noi", "mixed_use_value"],
        evidence={
            "components": {
                "residential": {"sqft": inputs.residential_sqft, "units": inputs.residential_units, "annual_income": round(res_income, 2), "pct_of_total": round(res_income / total_income * 100, 1) if total_income > 0 else 0},
                "commercial": {"sqft": inputs.commercial_sqft, "annual_income": round(com_income, 2), "pct_of_total": round(com_income / total_income * 100, 1) if total_income > 0 else 0},
                "retail": {"sqft": inputs.retail_sqft, "annual_income": round(ret_income, 2), "pct_of_total": round(ret_income / total_income * 100, 1) if total_income > 0 else 0},
            },
            "totals": {
                "gross_annual_income": round(total_income, 2),
                "net_operating_income": round(noi, 2),
                "property_value": round(total_value, 2),
                "value_per_sqft": round(total_value / total_sqft, 2) if total_sqft > 0 else 0,
                "cap_rate": inputs.cap_rate,
            },
        },
    )


# ==========================================================================
# Register commercial skills in the interpreter registry
# ==========================================================================

COMMERCIAL_INTERPRETER_SKILLS: dict[str, Any] = {
    "commercial-noi": calculate_noi,
    "commercial-dcf": calculate_dcf,
    "industrial-analysis": analyze_industrial,
    "mixed-use-analysis": analyze_mixed_use,
}


def route_valuation(unit_count: int, property_type: str, **kwargs: Any) -> str:
    """Route to correct valuation method based on unit count and property type.

    Residential: 1-4 units → pro forma (interpreter_skills.calculate_pro_forma)
    Commercial: 5+ units → NOI + cap rate (commercial_skills.calculate_noi)
    Industrial: always → industrial analysis
    Mixed-use: always → mixed-use analysis
    """
    if property_type in ("industrial", "warehouse"):
        return "industrial-analysis"
    if property_type == "mixed_use":
        return "mixed-use-analysis"
    if unit_count >= 5:
        return "commercial-noi"
    return "residential-pro-forma"
