"""Interpreter skills — deterministic compliance procedures as Python modules.

Per Interpreter Skills (LangChain blog, May 2026):
Skills externalize deterministic routines into code — reviewable, testable, versioned.
The model decides WHEN to call; the code IS the procedure.

Per AutoHarness (DeepMind, arXiv 2603.03329):
Code-as-policy can achieve zero LLM calls at inference for well-defined procedures.

These are Python reference implementations. TypeScript versions would run
in the interpreter runtime (SKILL.md + module).

Architecture: every function is pure-ish — takes structured inputs, returns
structured outputs with pass/fail + evidence. No external calls. No LLM dependence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ComplianceResult:
    passed: bool
    criteria_checked: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    requires_human_review: bool = False
    human_review_reason: str = ""


# ==========================================================================
# 1. zoning-compliance — checkZoning(parcel, proposedUse)
# ==========================================================================

@dataclass
class ParcelZoning:
    parcel_id: str
    zone_district: str
    permitted_uses: list[str]
    max_height_ft: float | None = None
    max_lot_coverage_pct: float | None = None
    min_setback_front_ft: float | None = None
    min_setback_side_ft: float | None = None
    min_setback_rear_ft: float | None = None
    max_density_units_per_acre: float | None = None
    min_lot_size_sqft: float | None = None
    parking_per_unit: float | None = None
    overlay_districts: list[str] = field(default_factory=list)
    special_conditions: list[str] = field(default_factory=list)


@dataclass
class ProposedUse:
    use_type: str  # single_family, multi_family, commercial, industrial, mixed_use
    building_height_ft: float | None = None
    lot_coverage_pct: float | None = None
    front_setback_ft: float | None = None
    side_setback_ft: float | None = None
    rear_setback_ft: float | None = None
    unit_count: int | None = None
    lot_size_sqft: float | None = None
    parking_spaces: int | None = None


def check_zoning(zoning: ParcelZoning, proposed: ProposedUse) -> ComplianceResult:
    failures: list[str] = []
    checked: list[str] = []
    evidence: dict[str, Any] = {}

    # Use check
    checked.append("permitted_use")
    if proposed.use_type not in zoning.permitted_uses:
        failures.append(f"Use '{proposed.use_type}' not permitted in {zoning.zone_district}. Permitted: {zoning.permitted_uses}")

    # Height
    if zoning.max_height_ft is not None and proposed.building_height_ft is not None:
        checked.append("height")
        evidence["height"] = {"max": zoning.max_height_ft, "proposed": proposed.building_height_ft}
        if proposed.building_height_ft > zoning.max_height_ft:
            failures.append(f"Height {proposed.building_height_ft}ft exceeds max {zoning.max_height_ft}ft")

    # Lot coverage
    if zoning.max_lot_coverage_pct is not None and proposed.lot_coverage_pct is not None:
        checked.append("lot_coverage")
        evidence["lot_coverage"] = {"max_pct": zoning.max_lot_coverage_pct, "proposed_pct": proposed.lot_coverage_pct}
        if proposed.lot_coverage_pct > zoning.max_lot_coverage_pct:
            failures.append(f"Lot coverage {proposed.lot_coverage_pct}% exceeds max {zoning.max_lot_coverage_pct}%")

    # Setbacks
    for name, max_val, prop_val in [
        ("front_setback", zoning.min_setback_front_ft, proposed.front_setback_ft),
        ("side_setback", zoning.min_setback_side_ft, proposed.side_setback_ft),
        ("rear_setback", zoning.min_setback_rear_ft, proposed.rear_setback_ft),
    ]:
        if max_val is not None and prop_val is not None:
            checked.append(name)
            evidence[name] = {"required_min_ft": max_val, "proposed_ft": prop_val}
            if prop_val < max_val:
                failures.append(f"{name.replace('_',' ')} {prop_val}ft below required {max_val}ft")

    # Density
    if zoning.max_density_units_per_acre is not None and proposed.unit_count is not None and proposed.lot_size_sqft is not None:
        checked.append("density")
        acres = proposed.lot_size_sqft / 43560.0
        density = proposed.unit_count / acres
        evidence["density"] = {"max_per_acre": zoning.max_density_units_per_acre, "proposed_per_acre": round(density, 2)}
        if density > zoning.max_density_units_per_acre:
            failures.append(f"Density {density:.1f} units/acre exceeds max {zoning.max_density_units_per_acre}")

    # Parking
    if zoning.parking_per_unit is not None and proposed.parking_spaces is not None and proposed.unit_count is not None:
        checked.append("parking")
        required = zoning.parking_per_unit * proposed.unit_count
        evidence["parking"] = {"required": required, "proposed": proposed.parking_spaces}
        if proposed.parking_spaces < required:
            failures.append(f"Parking {proposed.parking_spaces} spaces below required {required:.0f}")

    # Overlay triggers
    if zoning.overlay_districts:
        checked.append("overlay_districts")
        evidence["overlay_districts"] = zoning.overlay_districts
        evidence["overlay_note"] = "Overlay districts may impose additional restrictions not checked in this automated review."

    passed = len(failures) == 0
    human_review = bool(zoning.overlay_districts or zoning.special_conditions)

    return ComplianceResult(
        passed=passed,
        criteria_checked=checked,
        failures=failures,
        evidence=evidence,
        requires_human_review=human_review,
        human_review_reason="Overlay districts or special conditions present" if human_review else "",
    )


# ==========================================================================
# 2. permit-requirements — identifyPermits(projectType, jurisdiction)
# ==========================================================================

PERMIT_REGISTRY: dict[str, list[dict[str, Any]]] = {
    "residential_new_construction": [
        {"permit": "Building Permit", "agency": "Building Department", "required": True, "timeline_weeks": 2},
        {"permit": "Zoning Permit", "agency": "Planning Department", "required": True, "timeline_weeks": 1},
        {"permit": "Site Development Permit", "agency": "Planning Department", "required": True, "timeline_weeks": 4},
        {"permit": "Grading Permit", "agency": "Public Works", "required": True, "timeline_weeks": 2},
        {"permit": "Utility Connection", "agency": "Utility Company", "required": True, "timeline_weeks": 3},
        {"permit": "Environmental Review", "agency": "Environmental Department", "required": False, "condition": "If in sensitive area", "timeline_weeks": 8},
    ],
    "multi_family": [
        {"permit": "Building Permit", "agency": "Building Department", "required": True, "timeline_weeks": 3},
        {"permit": "Zoning Permit", "agency": "Planning Department", "required": True, "timeline_weeks": 2},
        {"permit": "Site Development Permit", "agency": "Planning Department", "required": True, "timeline_weeks": 6},
        {"permit": "Conditional Use Permit", "agency": "Planning Commission", "required": True, "timeline_weeks": 12},
        {"permit": "Traffic Impact Study", "agency": "Transportation Department", "required": True, "timeline_weeks": 8},
        {"permit": "Density Bonus Application", "agency": "Housing Department", "required": False, "condition": "If seeking density bonus", "timeline_weeks": 4},
        {"permit": "Affordable Housing Agreement", "agency": "Housing Department", "required": False, "condition": "If inclusionary zoning applies", "timeline_weeks": 6},
    ],
    "commercial": [
        {"permit": "Building Permit", "agency": "Building Department", "required": True, "timeline_weeks": 3},
        {"permit": "Zoning Permit", "agency": "Planning Department", "required": True, "timeline_weeks": 2},
        {"permit": "Site Development Permit", "agency": "Planning Department", "required": True, "timeline_weeks": 6},
        {"permit": "Conditional Use Permit", "agency": "Planning Commission", "required": True, "timeline_weeks": 12},
        {"permit": "Traffic Impact Study", "agency": "Transportation Department", "required": True, "timeline_weeks": 8},
        {"permit": "Sign Permit", "agency": "Planning Department", "required": True, "timeline_weeks": 2},
    ],
    "industrial": [
        {"permit": "Building Permit", "agency": "Building Department", "required": True, "timeline_weeks": 3},
        {"permit": "Zoning Permit", "agency": "Planning Department", "required": True, "timeline_weeks": 2},
        {"permit": "Site Development Permit", "agency": "Planning Department", "required": True, "timeline_weeks": 6},
        {"permit": "Industrial Waste Permit", "agency": "Environmental Department", "required": True, "timeline_weeks": 8},
        {"permit": "Fire Safety Permit", "agency": "Fire Department", "required": True, "timeline_weeks": 3},
        {"permit": "Stormwater Permit", "agency": "Public Works", "required": True, "timeline_weeks": 6},
    ],
}


def identify_permits(project_type: str, jurisdiction: str | None = None) -> ComplianceResult:
    registry = PERMIT_REGISTRY.get(project_type, [])
    if not registry:
        return ComplianceResult(
            passed=False,
            failures=[f"Unknown project type: {project_type}. Known: {list(PERMIT_REGISTRY.keys())}"],
            criteria_checked=["project_type"],
        )
    required = [p for p in registry if p.get("required")]
    conditional = [p for p in registry if not p.get("required")]
    checked = ["project_type", "required_permits", "conditional_permits"]
    return ComplianceResult(
        passed=True,
        criteria_checked=checked,
        evidence={
            "project_type": project_type,
            "jurisdiction": jurisdiction or "default",
            "required_permits": required,
            "conditional_permits": conditional,
            "total_permits": len(registry),
            "estimated_timeline_weeks": sum(p.get("timeline_weeks", 0) for p in required),
        },
    )


# ==========================================================================
# 3. financial-pro-forma — calculateProForma(params)
# ==========================================================================

@dataclass
class ProFormaInputs:
    land_cost: float
    construction_cost_per_sqft: float
    total_sqft: float
    unit_count: int
    avg_rent_per_unit: float
    vacancy_rate: float = 0.05
    operating_expense_ratio: float = 0.35
    cap_rate: float = 0.06
    soft_cost_ratio: float = 0.15
    financing_cost_ratio: float = 0.03


def calculate_pro_forma(inputs: ProFormaInputs) -> ComplianceResult:
    hard_costs = inputs.construction_cost_per_sqft * inputs.total_sqft
    soft_costs = hard_costs * inputs.soft_cost_ratio
    financing = (inputs.land_cost + hard_costs + soft_costs) * inputs.financing_cost_ratio
    total_project_cost = inputs.land_cost + hard_costs + soft_costs + financing
    gross_income = inputs.unit_count * inputs.avg_rent_per_unit * 12
    vacancy_loss = gross_income * inputs.vacancy_rate
    effective_income = gross_income - vacancy_loss
    operating_expenses = effective_income * inputs.operating_expense_ratio
    net_operating_income = effective_income - operating_expenses
    property_value = net_operating_income / inputs.cap_rate if inputs.cap_rate > 0 else 0
    max_offer = total_project_cost  # breakeven — profit is value above cost

    return ComplianceResult(
        passed=True,
        criteria_checked=["hard_costs", "soft_costs", "financing", "income", "noi", "cap_valuation"],
        evidence={
            "inputs": {
                "land_cost": inputs.land_cost,
                "construction_cost_per_sqft": inputs.construction_cost_per_sqft,
                "total_sqft": inputs.total_sqft,
                "unit_count": inputs.unit_count,
                "avg_rent_per_unit": inputs.avg_rent_per_unit,
                "vacancy_rate": inputs.vacancy_rate,
                "cap_rate": inputs.cap_rate,
            },
            "outputs": {
                "hard_costs": round(hard_costs, 2),
                "soft_costs": round(soft_costs, 2),
                "financing": round(financing, 2),
                "total_project_cost": round(total_project_cost, 2),
                "gross_annual_income": round(gross_income, 2),
                "effective_income": round(effective_income, 2),
                "operating_expenses": round(operating_expenses, 2),
                "net_operating_income": round(net_operating_income, 2),
                "property_value_cap_rate": round(property_value, 2),
                "max_offer_breakeven": round(max_offer, 2),
                "roi_pct": round(((property_value - total_project_cost) / total_project_cost) * 100, 2) if total_project_cost > 0 else 0,
            },
        },
    )


# ==========================================================================
# 4. setback-validator — validateSetbacks(sitePlan, zoningCode)
# ==========================================================================

@dataclass
class SitePlan:
    front_setback_ft: float
    side_setback_left_ft: float
    side_setback_right_ft: float
    rear_setback_ft: float
    building_height_ft: float
    lot_width_ft: float
    lot_depth_ft: float


@dataclass
class ZoningCode:
    min_front_setback_ft: float
    min_side_setback_ft: float
    min_rear_setback_ft: float
    max_height_ft: float
    max_lot_coverage_pct: float | None = None
    min_lot_width_ft: float | None = None
    min_lot_depth_ft: float | None = None


def validate_setbacks(plan: SitePlan, code: ZoningCode) -> ComplianceResult:
    failures: list[str] = []
    checked: list[str] = []
    evidence: dict[str, Any] = {"code": {}, "plan": {}, "status": {}}

    checks = [
        ("front_setback", plan.front_setback_ft, code.min_front_setback_ft),
        ("side_setback_left", plan.side_setback_left_ft, code.min_side_setback_ft),
        ("side_setback_right", plan.side_setback_right_ft, code.min_side_setback_ft),
        ("rear_setback", plan.rear_setback_ft, code.min_rear_setback_ft),
        ("building_height", plan.building_height_ft, code.max_height_ft),
    ]
    for name, actual, required in checks:
        checked.append(name)
        evidence["code"][name] = required
        evidence["plan"][name] = actual
        is_height = "height" in name
        if is_height:
            if actual > required:
                failures.append(f"{name}: {actual}ft exceeds max {required}ft")
                evidence["status"][name] = "FAIL"
            else:
                evidence["status"][name] = "PASS"
        else:
            if actual < required:
                failures.append(f"{name}: {actual}ft below required {required}ft")
                evidence["status"][name] = "FAIL"
            else:
                evidence["status"][name] = "PASS"

    if code.max_lot_coverage_pct is not None:
        checked.append("lot_coverage")
        coverage = ((plan.building_height_ft > 0) * 1.0)  # simplified — would use actual footprint
        evidence["status"]["lot_coverage"] = "CHECK_MANUALLY"

    if code.min_lot_width_ft is not None:
        checked.append("lot_width")
        if plan.lot_width_ft < code.min_lot_width_ft:
            failures.append(f"Lot width {plan.lot_width_ft}ft below minimum {code.min_lot_width_ft}ft")

    if code.min_lot_depth_ft is not None:
        checked.append("lot_depth")
        if plan.lot_depth_ft < code.min_lot_depth_ft:
            failures.append(f"Lot depth {plan.lot_depth_ft}ft below minimum {code.min_lot_depth_ft}ft")

    return ComplianceResult(
        passed=len(failures) == 0,
        criteria_checked=checked,
        failures=failures,
        evidence=evidence,
    )


# ==========================================================================
# 5. fee-calculator — calculateFees(projectType, sqft, jurisdiction)
# ==========================================================================

FEE_SCHEDULE: dict[str, dict[str, float]] = {
    "residential_new_construction": {
        "building_permit_base": 500.00,
        "building_permit_per_sqft": 0.50,
        "plan_check_fee": 0.65,  # 65% of building permit fee
        "school_impact_fee_per_unit": 3500.00,
        "park_impact_fee_per_unit": 1500.00,
        "traffic_impact_fee_per_unit": 2000.00,
        "water_connection": 3500.00,
        "sewer_connection": 4000.00,
    },
    "multi_family": {
        "building_permit_base": 1000.00,
        "building_permit_per_sqft": 0.65,
        "plan_check_fee": 0.65,
        "school_impact_fee_per_unit": 2500.00,
        "park_impact_fee_per_unit": 1200.00,
        "traffic_impact_fee_per_unit": 1800.00,
        "water_connection": 2500.00,
        "sewer_connection": 3000.00,
        "affordable_housing_in_lieu_per_unit": 15000.00,
    },
    "commercial": {
        "building_permit_base": 2000.00,
        "building_permit_per_sqft": 0.75,
        "plan_check_fee": 0.65,
        "traffic_impact_fee_per_sqft": 2.00,
        "water_connection": 5000.00,
        "sewer_connection": 6000.00,
    },
}


def calculate_fees(project_type: str, total_sqft: float, unit_count: int = 0, jurisdiction: str | None = None) -> ComplianceResult:
    schedule = FEE_SCHEDULE.get(project_type, {})
    if not schedule:
        return ComplianceResult(
            passed=False,
            failures=[f"Unknown project type: {project_type}"],
            criteria_checked=["project_type"],
        )
    building_permit = schedule.get("building_permit_base", 0) + schedule.get("building_permit_per_sqft", 0) * total_sqft
    plan_check = building_permit * schedule.get("plan_check_fee", 0)
    fees: dict[str, float] = {"building_permit": round(building_permit, 2), "plan_check": round(plan_check, 2)}
    if unit_count > 0:
        for key in ["school_impact_fee_per_unit", "park_impact_fee_per_unit", "traffic_impact_fee_per_unit", "affordable_housing_in_lieu_per_unit"]:
            rate = schedule.get(key, 0)
            if rate:
                fees[key.replace("_per_unit", "")] = round(rate * unit_count, 2)
    for key in ["water_connection", "sewer_connection", "traffic_impact_fee_per_sqft"]:
        rate = schedule.get(key, 0)
        if rate:
            multiplier = total_sqft if "sqft" in key else 1
            fees[key.replace("_per_sqft", "")] = round(rate * multiplier, 2)
    total = sum(fees.values())
    return ComplianceResult(
        passed=True,
        criteria_checked=["building_permit", "plan_check", "impact_fees", "utility_connections"],
        evidence={
            "project_type": project_type,
            "total_sqft": total_sqft,
            "unit_count": unit_count,
            "jurisdiction": jurisdiction or "default",
            "fees": fees,
            "total_estimated": round(total, 2),
        },
    )


# ==========================================================================
# Interpreter skill registry
# ==========================================================================

INTERPRETER_SKILLS: dict[str, Any] = {
    "zoning-compliance": check_zoning,
    "permit-requirements": identify_permits,
    "financial-pro-forma": calculate_pro_forma,
    "setback-validator": validate_setbacks,
    "fee-calculator": calculate_fees,
}
