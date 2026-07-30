from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field

from plotlot.harness.contracts.base import HarnessContract, JsonObject

EvaluationReadinessStatus = Literal["ready", "blocked"]
DIMENSIONAL_STANDARD_FIELDS = (
    "far",
    "max_far",
    "max_density_units_per_acre",
    "min_lot_area_sqft",
    "min_lot_width_ft",
    "front_setback_ft",
    "side_setback_ft",
    "rear_setback_ft",
    "max_height_ft",
    "max_stories",
    "max_lot_coverage_pct",
)


class EvaluationReadiness(HarnessContract):
    model_config = ConfigDict(frozen=True)

    status: EvaluationReadinessStatus
    can_recommend: bool
    reason: str = Field(min_length=1)
    missing_requirements: list[str] = Field(default_factory=list)
    completed_requirements: list[str] = Field(default_factory=list)
    allowed_outputs: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


def assess_live_evaluation_readiness(
    *,
    analysis_type: str,
    artifacts: JsonObject,
) -> EvaluationReadiness:
    """Decide whether collected live evidence can support a property evaluation."""
    property_record = _artifact(artifacts, "property_record")
    ordinance_rules = _artifact(artifacts, "ordinance_rules")
    feasibility = _artifact(artifacts, "feasibility")
    comping_workflow = _artifact(artifacts, "comping_workflow")
    trust_gates = _artifact(comping_workflow, "trust_gates")
    underwriting_mode = _artifact(artifacts, "underwriting_mode")
    cost_assumptions = _artifact(artifacts, "cost_assumptions")

    requirements = {
        "authoritative_parcel_identity": bool(
            property_record.get("folio") or property_record.get("parcel_id")
        )
        and _positive_number(property_record.get("lot_size_sqft")),
        "verified_zoning_district": bool(
            property_record.get("zoning_code") or property_record.get("ordinance_district_code")
        ),
        "official_dimensional_standards": _has_official_dimensional_standards(ordinance_rules),
        "deterministic_feasibility": bool(feasibility),
        "verified_market_comps": (
            trust_gates.get("underwriting_status") == "available_to_underwriting"
        ),
        "verified_underwriting_inputs": _has_verified_underwriting_inputs(
            underwriting_mode=underwriting_mode,
            cost_assumptions=cost_assumptions,
        ),
    }
    required_names = _required_names(analysis_type)
    missing = [name for name in required_names if not requirements[name]]
    completed = [name for name in required_names if requirements[name]]
    if missing:
        return EvaluationReadiness(
            status="blocked",
            can_recommend=False,
            reason=(
                "The harness collected partial property evidence, but the requested "
                "evaluation lacks required zoning-capacity or underwriting support."
            ),
            missing_requirements=missing,
            completed_requirements=completed,
            allowed_outputs=[
                "parcel_identity",
                "preliminary_zoning_context",
                "collected_evidence",
                "evidence_gap_plan",
            ],
            next_steps=_next_steps(missing),
        )
    return EvaluationReadiness(
        status="ready",
        can_recommend=analysis_type
        in {"acquisition_memo", "development_underwriting", "lender_package"},
        reason="The required evidence and deterministic outputs are available.",
        completed_requirements=completed,
        allowed_outputs=[
            "parcel_identity",
            "zoning_capacity",
            "deterministic_feasibility",
            "valuation",
            "recommendation",
        ],
    )


def _required_names(analysis_type: str) -> list[str]:
    if analysis_type in {
        "acquisition_memo",
        "development_underwriting",
        "lender_package",
    }:
        return [
            "authoritative_parcel_identity",
            "verified_zoning_district",
            "official_dimensional_standards",
            "deterministic_feasibility",
            "verified_market_comps",
            "verified_underwriting_inputs",
        ]
    if analysis_type == "zoning_research":
        return [
            "authoritative_parcel_identity",
            "verified_zoning_district",
            "official_dimensional_standards",
        ]
    return ["authoritative_parcel_identity"]


def _next_steps(missing: list[str]) -> list[str]:
    steps_by_requirement = {
        "authoritative_parcel_identity": (
            "Resolve the parcel against the official county assessor or GIS."
        ),
        "verified_zoning_district": (
            "Resolve the controlling zoning district from the official zoning map."
        ),
        "official_dimensional_standards": (
            "Retrieve and cite the controlling municipal ordinance sections for uses "
            "and dimensional standards."
        ),
        "deterministic_feasibility": (
            "Run the deterministic capacity calculator after parcel geometry and "
            "zoning standards are verified."
        ),
        "verified_market_comps": (
            "Collect and verify qualifying land and exit comps for the subject market."
        ),
        "verified_underwriting_inputs": (
            "Provide dated market, cost, financing, and strategy inputs, then rerun "
            "deterministic underwriting."
        ),
    }
    return [steps_by_requirement[name] for name in missing]


def _artifact(artifacts: JsonObject, key: str) -> JsonObject:
    value = artifacts.get(key)
    return value if isinstance(value, dict) else {}


def _positive_number(value: str | int | float | bool | None) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and float(value) > 0


def _has_official_dimensional_standards(rules: JsonObject) -> bool:
    return (
        bool(rules.get("authority_is_live"))
        and bool(rules.get("authority_is_official"))
        and not bool(rules.get("requires_official_verification"))
        and bool(str(rules.get("source_url") or "").strip())
        and bool(str(rules.get("source_section_id") or "").strip())
        and any(_positive_number(rules.get(field)) for field in DIMENSIONAL_STANDARD_FIELDS)
    )


def _has_verified_underwriting_inputs(
    *,
    underwriting_mode: JsonObject,
    cost_assumptions: JsonObject,
) -> bool:
    if underwriting_mode.get("status") != "completed" or not cost_assumptions:
        return False
    if bool(cost_assumptions.get("requires_official_verification")) or bool(
        cost_assumptions.get("requires_income_assumption_verification")
    ):
        return False
    mode = str(underwriting_mode.get("mode") or "")
    positive_fields, nonnegative_fields = {
        "income_cap_rate": (
            (
                "construction_cost_psf",
                "monthly_rent_per_unit",
                "operating_expense_pct",
                "cap_rate",
            ),
            ("vacancy_pct",),
        ),
        "sold_unit_exit": (
            (
                "construction_cost_psf",
                "avg_unit_size_sqft",
                "builder_margin_pct",
            ),
            ("soft_cost_pct", "impact_fees_per_unit"),
        ),
    }.get(mode, ((), ()))
    return (
        bool(positive_fields)
        and all(_positive_number(cost_assumptions.get(field)) for field in positive_fields)
        and all(_nonnegative_number(cost_assumptions.get(field)) for field in nonnegative_fields)
    )


def _nonnegative_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and float(value) >= 0
