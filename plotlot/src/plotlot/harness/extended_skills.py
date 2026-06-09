"""Extended interpreter skills — environmental, variance, FAR, sensitivity.

Covers gaps in the land development workflow:
- Environmental checks (flood zone, wetlands, soil, endangered species)
- Zoning variance feasibility analysis
- Floor Area Ratio (FAR) and lot coverage calculations
- Financial sensitivity analysis (what-if scenarios)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from plotlot.harness.interpreter_skills import ComplianceResult


# ==========================================================================
# ENVIRONMENTAL CHECKS
# ==========================================================================

@dataclass
class EnvironmentalInputs:
    parcel_id: str
    flood_zone: str = ""  # X, A, AE, VE, etc.
    wetland_indicator: bool = False
    endangered_species_habitat: bool = False
    soil_type: str = ""  # sandy, clay, fill, organic
    brownfield: bool = False
    coastal_zone: bool = False
    steep_slope_pct: float = 0.0
    critical_area: bool = False


def check_environmental(inputs: EnvironmentalInputs) -> ComplianceResult:
    """Check environmental constraints that could block or complicate development."""
    flags: list[str] = []
    checked: list[str] = []
    evidence: dict[str, Any] = {"findings": {}}

    # Flood zone
    checked.append("flood_zone")
    high_risk = {"A", "AE", "VE", "AH", "AO", "V"}
    if inputs.flood_zone in high_risk:
        flags.append(f"High-risk flood zone {inputs.flood_zone}: requires elevation certificate, flood insurance, possibly LOMR")
        evidence["findings"]["flood_zone"] = {"risk": "HIGH", "zone": inputs.flood_zone, "requires": ["elevation_certificate", "flood_insurance"]}
    elif inputs.flood_zone and inputs.flood_zone != "X":
        evidence["findings"]["flood_zone"] = {"risk": "MODERATE", "zone": inputs.flood_zone}
    else:
        evidence["findings"]["flood_zone"] = {"risk": "LOW", "zone": inputs.flood_zone or "X"}

    # Wetlands
    checked.append("wetlands")
    if inputs.wetland_indicator:
        flags.append("Wetland indicator present: requires Army Corps jurisdictional determination, possible Section 404 permit")
        evidence["findings"]["wetlands"] = {"present": True, "requires": ["jurisdictional_determination", "section_404_permit"]}

    # Endangered species
    checked.append("endangered_species")
    if inputs.endangered_species_habitat:
        flags.append("Endangered species habitat: requires USFWS consultation, biological assessment, possible HCP")
        evidence["findings"]["endangered_species"] = {"present": True, "requires": ["usfws_consultation", "habitat_conservation_plan"]}

    # Soil
    checked.append("soil")
    if inputs.soil_type == "organic":
        flags.append("Organic soils: poor bearing capacity, requires geotechnical investigation and possible over-excavation")
        evidence["findings"]["soil"] = {"type": "organic", "risk": "HIGH"}
    elif inputs.soil_type in ("clay", "fill"):
        flags.append(f"{inputs.soil_type.title()} soils: may require soil amendment or deep foundations")
        evidence["findings"]["soil"] = {"type": inputs.soil_type, "risk": "MODERATE"}

    # Brownfield
    checked.append("brownfield")
    if inputs.brownfield:
        flags.append("Brownfield site: requires Phase I/II ESA, possible remediation plan")
        evidence["findings"]["brownfield"] = {"present": True, "requires": ["phase_one_esa", "phase_two_esa", "remediation_plan"]}

    # Steep slopes
    checked.append("steep_slopes")
    if inputs.steep_slope_pct > 25:
        flags.append(f"Steep slopes ({inputs.steep_slope_pct}%): requires geotechnical study, grading plan, possible retaining walls")
        evidence["findings"]["steep_slopes"] = {"slope_pct": inputs.steep_slope_pct, "risk": "HIGH"}
    elif inputs.steep_slope_pct > 15:
        evidence["findings"]["steep_slopes"] = {"slope_pct": inputs.steep_slope_pct, "risk": "MODERATE"}

    passed = len(flags) == 0
    return ComplianceResult(
        passed=passed,
        criteria_checked=checked,
        failures=flags if not passed else [],
        evidence=evidence,
        requires_human_review=not passed or inputs.brownfield or inputs.endangered_species_habitat,
        human_review_reason="Environmental constraints require expert review" if not passed else "",
    )


# ==========================================================================
# ZONING VARIANCE FEASIBILITY
# ==========================================================================

@dataclass
class VarianceInputs:
    parcel_id: str
    variance_type: str  # use, area, height, setback, density, parking
    current_requirement: float
    proposed_value: float
    hardship_argument: str = ""
    neighbor_impact: str = "unknown"  # low, medium, high
    precedent_exists: bool = False


def assess_variance(inputs: VarianceInputs) -> ComplianceResult:
    """Assess likelihood of zoning variance approval."""
    score = 0
    checked = ["variance_type", "hardship", "neighbor_impact", "precedent"]
    evidence: dict[str, Any] = {}

    # Hardship
    if inputs.hardship_argument:
        score += 2
        evidence["hardship"] = "argued"

    # Deviation magnitude
    deviation_pct = abs(inputs.proposed_value - inputs.current_requirement) / max(inputs.current_requirement, 1) * 100
    evidence["deviation_pct"] = round(deviation_pct, 1)
    if deviation_pct <= 10:
        score += 3
    elif deviation_pct <= 25:
        score += 1
    else:
        score -= 1

    # Neighbor impact
    if inputs.neighbor_impact == "low":
        score += 2
    elif inputs.neighbor_impact == "high":
        score -= 2

    # Precedent
    if inputs.precedent_exists:
        score += 2

    if score >= 5:
        likelihood = "LIKELY"
    elif score >= 3:
        likelihood = "POSSIBLE"
    else:
        likelihood = "UNLIKELY"

    return ComplianceResult(
        passed=likelihood != "UNLIKELY",
        criteria_checked=checked,
        evidence={
            "variance_type": inputs.variance_type,
            "current": inputs.current_requirement,
            "proposed": inputs.proposed_value,
            "deviation_pct": round(deviation_pct, 1),
            "score": f"{score}/7",
            "likelihood": likelihood,
            "factors": {"hardship": bool(inputs.hardship_argument), "neighbor_impact": inputs.neighbor_impact, "precedent": inputs.precedent_exists},
        },
        requires_human_review=True,
        human_review_reason="Variance decisions are discretionary; expert review required",
    )


# ==========================================================================
# FAR + LOT COVERAGE
# ==========================================================================

@dataclass
class FARInputs:
    building_sqft: float
    lot_sqft: float
    max_far: float  # max allowed Floor Area Ratio
    max_lot_coverage_pct: float  # max allowed building coverage %
    building_footprint_sqft: float  # ground floor area


def check_far(inputs: FARInputs) -> ComplianceResult:
    """Check Floor Area Ratio and lot coverage compliance."""
    failures: list[str] = []
    evidence: dict[str, Any] = {}

    actual_far = inputs.building_sqft / inputs.lot_sqft if inputs.lot_sqft > 0 else 0
    evidence["far"] = {"max": inputs.max_far, "actual": round(actual_far, 3), "compliant": actual_far <= inputs.max_far}
    if actual_far > inputs.max_far:
        failures.append(f"FAR {actual_far:.2f} exceeds maximum {inputs.max_far}")

    actual_coverage = (inputs.building_footprint_sqft / inputs.lot_sqft * 100) if inputs.lot_sqft > 0 else 0
    evidence["lot_coverage"] = {"max_pct": inputs.max_lot_coverage_pct, "actual_pct": round(actual_coverage, 1), "compliant": actual_coverage <= inputs.max_lot_coverage_pct}
    if actual_coverage > inputs.max_lot_coverage_pct:
        failures.append(f"Lot coverage {actual_coverage:.1f}% exceeds maximum {inputs.max_lot_coverage_pct}%")

    buildable_sqft = inputs.max_far * inputs.lot_sqft
    remaining_sqft = max(0, buildable_sqft - inputs.building_sqft)
    evidence["buildable"] = {"max_sqft": round(buildable_sqft, 0), "remaining_sqft": round(remaining_sqft, 0), "remaining_units": f"~{int(remaining_sqft/800)} units (residential estimate)"}

    return ComplianceResult(
        passed=len(failures) == 0,
        criteria_checked=["far", "lot_coverage"],
        failures=failures,
        evidence=evidence,
    )


# ==========================================================================
# SENSITIVITY ANALYSIS
# ==========================================================================

@dataclass
class SensitivityInputs:
    base_noi: float
    base_cap_rate: float
    scenarios: int = 5  # number of cap rate scenarios
    cap_rate_range: float = 0.01  # ± range


def run_sensitivity(inputs: SensitivityInputs) -> ComplianceResult:
    """Run cap rate sensitivity analysis for a property valuation."""
    base_value = inputs.base_noi / inputs.base_cap_rate if inputs.base_cap_rate > 0 else 0
    scenarios: list[dict[str, Any]] = []
    spread = inputs.cap_rate_range * 2
    step = spread / (inputs.scenarios - 1) if inputs.scenarios > 1 else 0
    for i in range(inputs.scenarios):
        cap = inputs.base_cap_rate - inputs.cap_rate_range + (step * i)
        value = inputs.base_noi / cap if cap > 0 else 0
        scenarios.append({"cap_rate": round(cap, 4), "value": round(value, 2), "delta_from_base_pct": round((value - base_value) / base_value * 100, 1)})
    values = [s["value"] for s in scenarios]
    low_val, high_val = min(values), max(values)
    return ComplianceResult(
        passed=True,
        criteria_checked=["cap_rate_sensitivity"],
        evidence={
            "base": {"noi": inputs.base_noi, "cap_rate": inputs.base_cap_rate, "value": round(base_value, 2)},
            "range": {"low_cap": round(inputs.base_cap_rate - inputs.cap_rate_range, 4), "high_cap": round(inputs.base_cap_rate + inputs.cap_rate_range, 4), "low_value": round(low_val, 2), "high_value": round(high_val, 2), "spread_pct": round((high_val - low_val) / base_value * 100, 1) if base_value > 0 else 0},
            "scenarios": scenarios,
        },
    )


EXTENDED_INTERPRETER_SKILLS: dict[str, Any] = {
    "environmental-check": check_environmental,
    "variance-assessment": assess_variance,
    "far-check": check_far,
    "sensitivity-analysis": run_sensitivity,
}
