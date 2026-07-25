from __future__ import annotations

from dataclasses import dataclass
from math import isclose
import os
from unittest.mock import patch

from plotlot.domain.types import PolicyDecision
from plotlot.harness.contracts import CountyName, ExecutionMode, SourceMode
from plotlot.harness.eval_models import EvalCaseResult, EvalResult, eval_result
from plotlot.harness.fixture_evidence import fixture_evidence_for_run
from plotlot.harness.fixture_runs import FixtureDealRunRequest, run_deal_analysis, run_fixture_deal_analysis
from plotlot.harness.health import HarnessHealthStatus, collect_harness_health
from plotlot.harness.south_florida_gis import search_south_florida_gis
from plotlot.harness.tool_router import HarnessToolCallResult, ToolRouteStatus
from plotlot.harness.training_ingestion import (
    build_training_knowledge_index,
    discover_training_video_sources,
    extract_training_concepts,
    map_concepts_to_workflow_templates,
    normalize_transcript,
    segment_transcript,
)
from plotlot.harness.underwriting_calculators import run_feasibility, run_residual_land_value
from plotlot.harness.underwriting_models import FeasibilityInput, ResidualLandValueInput
from plotlot.harness.contracts import JsonObject, RunId, ToolCallId


_LIVE_EVAL_ENABLED = os.environ.get("PLOTLOT_LIVE_TESTS") == "1"


def harness_suite() -> EvalResult:
    result = run_fixture_deal_analysis(
        FixtureDealRunRequest(
            address="example Miami-Dade fixture address",
            analysis_type="acquisition_memo",
            execution_mode=ExecutionMode.LOCAL,
        )
    )
    event_types = [event.type.value for event in result.events]
    failures: list[str] = []
    if result.status != "completed":
        failures.append("fixture run did not complete")
    if event_types[:3] != ["run.created", "skill.selected", "run.started"]:
        failures.append("fixture run no longer emits the expected run lifecycle prefix")
    if "tool.completed" not in event_types:
        failures.append("fixture run did not execute shared tool calls")
    if event_types[-1] != "run.completed":
        failures.append("fixture run did not emit run.completed")
    if not result.evidence_ids:
        failures.append("fixture run did not expose evidence ids")
    if not result.preliminary:
        failures.append("fixture run must be preliminary")
    if len(result.tool_calls) < 6:
        failures.append("fixture run did not persist the expected shared tool calls")
    if len(result.calculations) < 2:
        failures.append("fixture run did not produce underwriting calculations")
    return eval_result(
        "harness",
        [
            EvalCaseResult(
                name="fixture_run_trajectory",
                passed=not failures,
                run_id=result.run_id,
                failures=failures,
                metrics={"event_count": len(result.events), "evidence_count": len(result.evidence_ids)},
            )
        ],
    )


def evidence_suite() -> EvalResult:
    run = run_fixture_deal_analysis(
        FixtureDealRunRequest(
            address="example Broward fixture address",
            analysis_type="zoning_research",
        )
    )
    evidence = fixture_evidence_for_run(run)
    failures: list[str] = []
    if len(evidence) != len(run.evidence_ids):
        failures.append("fixture evidence count does not match run evidence ids")
    if any(item.run_id != run.run_id for item in evidence):
        failures.append("fixture evidence run_id mismatch")
    if any(item.source_mode != SourceMode.FIXTURE for item in evidence):
        failures.append("fixture evidence source mode mismatch")
    return eval_result(
        "evidence",
        [
            EvalCaseResult(
                name="fixture_evidence_linkage",
                passed=not failures,
                run_id=run.run_id,
                failures=failures,
                metrics={"evidence_count": len(evidence)},
            )
        ],
    )


def south_florida_gis_suite() -> EvalResult:
    miami = search_south_florida_gis(
        "zoning",
        county=CountyName("Miami-Dade"),
        source_mode=SourceMode.FIXTURE,
    )
    broward = search_south_florida_gis(
        "zoning",
        county=CountyName("Broward"),
        source_mode=SourceMode.FIXTURE,
    )
    failures: list[str] = []
    if not miami:
        failures.append("Miami-Dade zoning fixture missing")
    if not broward:
        failures.append("Broward zoning fixture missing")
    return eval_result(
        "south-florida-gis",
        [
            EvalCaseResult(
                name="provider_selection",
                passed=not failures,
                failures=failures,
                metrics={"miami_dade_sources": len(miami), "broward_sources": len(broward)},
            )
        ],
    )


def south_florida_address_paths_suite() -> EvalResult:
    cases: list[EvalCaseResult] = []
    fixture_addresses = [
        ("miami_dade_acquisition_path", "example Miami-Dade fixture address", "Miami-Dade"),
        ("broward_acquisition_path", "example Broward fixture address", "Broward"),
    ]
    for case_name, address, expected_county in fixture_addresses:
        run = run_fixture_deal_analysis(
            FixtureDealRunRequest(
                address=address,
                analysis_type="acquisition_memo",
                execution_mode=ExecutionMode.LOCAL,
            )
        )
        failures: list[str] = []
        evidence_types = {item.source_type.value for item in run.evidence_items}
        claim_types = {claim.claim_type for claim in run.claims}
        property_record = run.artifacts.get("property_record")
        if run.status != "completed":
            failures.append("run did not complete")
        if run.verification_status != "passed_with_warnings":
            failures.append("fixture acquisition path verification status changed")
        if not run.preliminary:
            failures.append("fixture acquisition path must remain preliminary")
        if not isinstance(property_record, dict) or property_record.get("county") != expected_county:
            failures.append("property record county did not match fixture expectation")
        if "parcel_record" not in evidence_types:
            failures.append("parcel evidence missing")
        if "market_comp" not in evidence_types:
            failures.append("land comparable evidence missing")
        if "rental_comp" not in evidence_types:
            failures.append("exit comparable evidence missing")
        if "zoning_program" not in claim_types:
            failures.append("zoning claim missing")
        if "comp_value_signal" not in claim_types:
            failures.append("comp value claim missing")
        if "max_supportable_land_price" not in claim_types:
            failures.append("residual land value claim missing")
        cases.append(
            EvalCaseResult(
                name=case_name,
                passed=not failures,
                run_id=run.run_id,
                failures=failures,
                metrics={
                    "evidence_count": len(run.evidence_items),
                    "claim_count": len(run.claims),
                    "event_count": len(run.events),
                },
            )
        )
    return eval_result("south-florida-address-paths", cases)


@dataclass(frozen=True)
class _LiveAddressPathCase:
    name: str
    address: str
    county: str
    municipality: str
    zoning_code: str
    lot_frontage_ft: float
    expected_action: str
    assumptions: JsonObject


def south_florida_address_paths_live_suite() -> EvalResult:
    if not _LIVE_EVAL_ENABLED:
        return eval_result(
            "south-florida-address-paths-live",
            [
                EvalCaseResult(
                    name="live_tests_disabled",
                    passed=True,
                    failures=[],
                    metrics={
                        "skipped": 1,
                        "requires_env": "PLOTLOT_LIVE_TESTS=1",
                    },
                )
            ],
        )

    return eval_result(
        "south-florida-address-paths-live",
        [_run_live_address_path_case(case) for case in _live_address_path_cases()],
    )


def _run_live_address_path_case(case: _LiveAddressPathCase) -> EvalCaseResult:
    run = run_deal_analysis(
        FixtureDealRunRequest(
            address=case.address,
            analysis_type="acquisition_memo",
            source_mode=SourceMode.LIVE,
            execution_mode=ExecutionMode.LOCAL,
            assumptions=case.assumptions,
        )
    )
    failures: list[str] = []
    property_record = run.artifacts.get("property_record")
    comps = run.artifacts.get("comps")
    guidance = run.artifacts.get("acquisition_guidance")
    underwriting_mode = run.artifacts.get("underwriting_mode")
    tool_names = {tool_call.tool_name for tool_call in run.tool_calls}

    if run.status != "completed":
        failures.append("run did not complete")
    if run.source_mode is not SourceMode.LIVE:
        failures.append("run did not preserve live source mode")
    if not isinstance(property_record, dict):
        failures.append("property record missing")
    else:
        if str(property_record.get("county") or "").strip() != case.county:
            failures.append("property county mismatch")
        if str(property_record.get("municipality") or "").strip().casefold() != case.municipality.casefold():
            failures.append("property municipality mismatch")
        if str(property_record.get("zoning_code") or "").strip().upper() != case.zoning_code.upper():
            failures.append("property zoning mismatch")
    if not {"geocode_address", "lookup_property_info", "find_comparables"}.issubset(tool_names):
        failures.append("parcel or comps tool coverage regressed")
    if "compute_feasibility" not in tool_names:
        failures.append("feasibility tool did not run")
    if "run_pro_forma" not in tool_names and "run_residual_land_value" not in tool_names:
        failures.append("underwriting tools did not run")
    if not isinstance(comps, dict):
        failures.append("comps artifact missing")
    else:
        land_comps = comps.get("comparables")
        contextual_land = comps.get("public_listing_land_comparables")
        if not (
            isinstance(land_comps, list)
            and len(land_comps) > 0
            or isinstance(contextual_land, list)
            and len(contextual_land) > 0
        ):
            failures.append("no live land comp signal returned")
        adv_per_unit = comps.get("adv_per_unit")
        if not isinstance(adv_per_unit, int | float) or float(adv_per_unit) <= 0:
            failures.append("no positive exit comp pricing signal returned")
    if not isinstance(guidance, dict):
        failures.append("acquisition guidance missing")
    else:
        recommended_action = str(guidance.get("recommended_action") or "").strip()
        if recommended_action != case.expected_action:
            failures.append("acquisition guidance decision changed")
        recommended_offer = guidance.get("recommended_offer")
        if recommended_action == "offer_range":
            if not isinstance(recommended_offer, int | float) or float(recommended_offer) <= 0:
                failures.append("recommended offer missing or non-positive")
        elif recommended_action == "no_offer":
            max_supportable_land_price = guidance.get("max_supportable_land_price")
            if not isinstance(max_supportable_land_price, int | float):
                failures.append("no-offer decision missing supportable land price")
        elif recommended_action == "insufficient_support":
            if not isinstance(recommended_offer, int | float) or float(recommended_offer) != 0.0:
                failures.append("insufficient-support decision should not return an offer")
        else:
            failures.append("acquisition guidance did not produce a supported decision")
    if not isinstance(underwriting_mode, dict):
        failures.append("underwriting mode missing")
    else:
        if str(underwriting_mode.get("status") or "").strip() not in {"completed", "partial"}:
            failures.append("underwriting mode did not reach a usable state")

    evidence_types = {item.source_type.value for item in run.evidence_items}
    if "parcel_record" not in evidence_types:
        failures.append("parcel evidence missing")
    if "market_comp" not in evidence_types:
        failures.append("market comp evidence missing")

    lot_size_sqft = 0.0
    if isinstance(property_record, dict):
        raw_lot_size = property_record.get("lot_size_sqft")
        if isinstance(raw_lot_size, int | float):
            lot_size_sqft = float(raw_lot_size)

    land_comp_count = 0
    public_listing_count = 0
    if isinstance(comps, dict):
        raw_land_comps = comps.get("comparables")
        if isinstance(raw_land_comps, list):
            land_comp_count = len(raw_land_comps)
        raw_public_listing = comps.get("public_listing_land_comparables")
        if isinstance(raw_public_listing, list):
            public_listing_count = len(raw_public_listing)

    metrics: JsonObject = {
        "tool_call_count": len(run.tool_calls),
        "event_count": len(run.events),
        "evidence_count": len(run.evidence_items),
        "claim_count": len(run.claims),
        "lot_size_sqft": lot_size_sqft,
        "lot_frontage_ft": case.lot_frontage_ft,
        "land_comp_count": land_comp_count,
        "public_listing_land_comp_count": public_listing_count,
        "recommended_action": guidance.get("recommended_action") if isinstance(guidance, dict) else "",
        "verification_status": run.verification_status,
        "preliminary": run.preliminary,
    }
    return EvalCaseResult(
        name=case.name,
        passed=not failures,
        run_id=run.run_id,
        failures=failures,
        metrics=metrics,
    )


def _live_address_path_cases() -> tuple[_LiveAddressPathCase, ...]:
    miami_dade_base = {
        "maxUnits": 1,
        "maxDensityUnitsPerAcre": 6,
        "minLotAreaSf": 7500,
        "frontSetbackFt": 25,
        "sideSetbackFt": 7.5,
        "rearSetbackFt": 25,
        "maxLotCoveragePct": 40,
        "parkingSpacesPerUnit": 2,
        "avgUnitSizeSf": 1700,
        "monthlyRentPerUnit": 3200,
        "operatingExpensePct": 0.35,
        "capRate": 0.06,
        "hardCosts": 285000,
        "softCosts": 57000,
        "contingency": 18000,
        "developerFee": 30000,
        "closingCosts": 12000,
        "financingCosts": 18000,
        "holdingCosts": 14000,
        "sellingCosts": 26000,
        "targetProfitPct": 0.18,
    }
    broward_base = {
        "maxUnits": 1,
        "maxDensityUnitsPerAcre": 8,
        "minLotAreaSf": 5000,
        "frontSetbackFt": 25,
        "sideSetbackFt": 5,
        "rearSetbackFt": 15,
        "maxLotCoveragePct": 50,
        "parkingSpacesPerUnit": 2,
        "avgUnitSizeSf": 1700,
        "monthlyRentPerUnit": 3200,
        "operatingExpensePct": 0.35,
        "capRate": 0.06,
        "hardCosts": 285000,
        "softCosts": 57000,
        "contingency": 18000,
        "developerFee": 30000,
        "closingCosts": 12000,
        "financingCosts": 18000,
        "holdingCosts": 14000,
        "sellingCosts": 26000,
        "targetProfitPct": 0.18,
    }
    return (
        _LiveAddressPathCase(
            name="miami_gardens_45_nw_209_st",
            address="45 NW 209 ST, Miami Gardens, FL 33169",
            county="Miami-Dade",
            municipality="Miami Gardens",
            zoning_code="R-1",
            lot_frontage_ft=75.0,
            expected_action="insufficient_support",
            assumptions={**miami_dade_base, "minLotFrontageFt": 75, "lotFrontageFt": 75},
        ),
        _LiveAddressPathCase(
            name="miami_gardens_171_ne_209th_ter",
            address="171 NE 209th Ter, Miami Gardens, FL 33179",
            county="Miami-Dade",
            municipality="Miami Gardens",
            zoning_code="R-1",
            lot_frontage_ft=75.0,
            expected_action="offer_range",
            assumptions={**miami_dade_base, "minLotFrontageFt": 75, "lotFrontageFt": 75},
        ),
        _LiveAddressPathCase(
            name="miami_gardens_310_nw_205th_ter",
            address="310 NW 205th Ter, Miami Gardens, FL 33169",
            county="Miami-Dade",
            municipality="Miami Gardens",
            zoning_code="R-1",
            lot_frontage_ft=75.0,
            expected_action="offer_range",
            assumptions={**miami_dade_base, "minLotFrontageFt": 75, "lotFrontageFt": 75},
        ),
        _LiveAddressPathCase(
            name="fort_lauderdale_1401_nw_14th_st",
            address="1401 NW 14th St, Fort Lauderdale, FL 33311",
            county="Broward",
            municipality="Fort Lauderdale",
            zoning_code="RDS-15",
            lot_frontage_ft=50.0,
            expected_action="offer_range",
            assumptions={**broward_base, "maxDensityUnitsPerAcre": 15, "minLotFrontageFt": 50, "lotFrontageFt": 50, "maxFar": 0.75},
        ),
        _LiveAddressPathCase(
            name="fort_lauderdale_101_se_1st_ave",
            address="101 SE 1st Ave, Fort Lauderdale, FL 33301",
            county="Broward",
            municipality="Fort Lauderdale",
            zoning_code="RAC-CC",
            lot_frontage_ft=50.0,
            expected_action="offer_range",
            assumptions={**broward_base, "maxDensityUnitsPerAcre": 15, "minLotFrontageFt": 50, "lotFrontageFt": 50, "maxFar": 0.75},
        ),
    )


def underwriting_suite() -> EvalResult:
    residual = run_residual_land_value(
        ResidualLandValueInput(
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
    )
    feasibility = run_feasibility(
        FeasibilityInput(
            lot_area_sf=10_000,
            max_far=1.5,
            max_units=12,
            efficiency_factor=0.85,
            avg_unit_size_sf=850,
            parking_spaces_per_unit=1.5,
        )
    )
    failures: list[str] = []
    if residual.max_supportable_land_price != 195_000:
        failures.append("residual land value output changed")
    if residual.go_no_go_signal.value != "go":
        failures.append("residual land value go/no-go changed")
    if feasibility.estimated_units != 12:
        failures.append("feasibility estimated units changed")
    return eval_result(
        "underwriting",
        [
            EvalCaseResult(
                name="deterministic_calculators",
                passed=not failures,
                failures=failures,
                metrics={
                    "max_supportable_land_price": residual.max_supportable_land_price,
                    "estimated_units": feasibility.estimated_units,
                },
            )
        ],
    )


def training_discovery_suite() -> EvalResult:
    videos = discover_training_video_sources(
        source_mode=SourceMode.FIXTURE,
        url="https://www.youtube.com/watch?v=0IS1iFMJ8sQ",
    )
    concepts = []
    mappings = []
    knowledge = []
    if videos:
        transcript = normalize_transcript(videos[0])
        segments = segment_transcript(transcript)
        concepts = extract_training_concepts(transcript, segments)
        mappings = map_concepts_to_workflow_templates(concepts)
        knowledge = build_training_knowledge_index(concepts)
    failures: list[str] = []
    if not videos:
        failures.append("YouTube ARV fixture video missing")
    if not concepts:
        failures.append("training concepts were not extracted")
    if concepts and not concepts[0].segment_ids:
        failures.append("training concept missing transcript segment ids")
    if not mappings:
        failures.append("workflow mappings were not created")
    return eval_result(
        "training-discovery",
        [
            EvalCaseResult(
                name="youtube_arv_workflow_mapping",
                passed=not failures,
                failures=failures,
                metrics={
                    "video_count": len(videos),
                    "concept_count": len(concepts),
                    "mapping_count": len(mappings),
                    "knowledge_count": len(knowledge),
                },
            )
        ],
    )


def health_suite() -> EvalResult:
    health = collect_harness_health()
    failures = [] if health.status == HarnessHealthStatus.OK else ["harness health is not ok"]
    return eval_result(
        "health",
        [
            EvalCaseResult(
                name="harness_health_readiness",
                passed=not failures,
                failures=failures,
                metrics=health.metrics,
            )
        ],
    )


@dataclass(frozen=True)
class _ManualOfferEvalCase:
    name: str
    request: FixtureDealRunRequest
    property_payload: JsonObject
    feasibility_result: JsonObject
    pro_forma_result: JsonObject
    noi_result: JsonObject
    residual_result: JsonObject
    expected_feasibility: JsonObject
    expected_land_value: float
    expected_adv_per_unit: float
    expected_offer: float
    expected_guidance_offer: float
    expected_action: str
    expected_basis: str
    expected_land_signal_available: bool
    expected_market_gap: float
    expected_owner_basis_warning: str
    expected_warning_substring: str
    expected_gis_warning: str | None = None
    expected_frontage_warning_substring: str | None = None
    expected_manual_dimensional: JsonObject | None = None
    expected_missing_manual_dimensional_keys: tuple[str, ...] = ()


_MANUAL_LAND_COMP_QUALITY: dict[str, JsonObject] = {
    "miami_gardens_manual_offer": {
        "land_comp_count": 2,
        "scored_land_comp_count": 0,
        "strong_land_comp_count": 0,
        "independent_land_comp_count": 2,
        "strong_independent_land_comp_count": 0,
        "land_comp_scores": [],
        "best_fit_score": 0.99,
        "best_fit_lot_size_variance_ratio": 0.01,
        "best_fit_qualification_score": 0.0,
        "direct_land_comp_signal": False,
        "manual_override_used": True,
    },
    "broward_manual_offer": {
        "land_comp_count": 2,
        "scored_land_comp_count": 0,
        "strong_land_comp_count": 0,
        "independent_land_comp_count": 2,
        "strong_independent_land_comp_count": 0,
        "land_comp_scores": [],
        "best_fit_score": 0.917,
        "best_fit_lot_size_variance_ratio": 0.083,
        "best_fit_qualification_score": 0.0,
        "direct_land_comp_signal": False,
        "manual_override_used": True,
    },
}


def manual_offer_suite() -> EvalResult:
    cases = [_manual_offer_eval_case(case) for case in _manual_offer_eval_cases()]
    return eval_result("manual-offer-workflows", cases)


def _manual_offer_eval_case(case: _ManualOfferEvalCase) -> EvalCaseResult:
    failures: list[str] = []
    observed_feasibility_args: JsonObject = {}
    observed_pro_forma_args: JsonObject = {}

    async def _fake_tool_result(request) -> HarnessToolCallResult:  # noqa: ANN001
        payload = _manual_offer_tool_payload(
            case=case,
            request=request,
            observed_feasibility_args=observed_feasibility_args,
            observed_pro_forma_args=observed_pro_forma_args,
        )
        return HarnessToolCallResult(
            ok=True,
            tool_call_id=ToolCallId(f"tool_call_{request.tool_name}"),
            tool_name=request.tool_name,
            run_id=RunId(str(request.run_id)),
            args=dict(request.args),
            status=ToolRouteStatus.COMPLETED,
            policy_decision=PolicyDecision(allowed=True, reason="eval"),
            payload=payload,
            events=[],
            source_mode=SourceMode.LIVE,
        )

    with patch("plotlot.harness.fixture_runs._tool_result", _fake_tool_result):
        result = run_deal_analysis(case.request)

    tool_names = {tool_call.tool_name for tool_call in result.tool_calls}
    if result.status != "completed":
        failures.append("live manual-offer run did not complete")
    if result.source_mode is not SourceMode.LIVE:
        failures.append("live manual-offer run did not preserve live source mode")
    if not {
        "geocode_address",
        "lookup_property_info",
        "search_zoning_ordinance",
        "load_underwriting_market_profile",
        "find_comparables",
        "compute_feasibility",
        "run_pro_forma",
        "run_noi_valuation",
        "run_residual_land_value",
    }.issubset(tool_names):
        failures.append("live manual-offer path no longer covers parcel, zoning, comps, and underwriting")
    for key, expected_value in case.expected_feasibility.items():
        actual_value = observed_feasibility_args.get(key)
        if isinstance(expected_value, float):
            if not isinstance(actual_value, int | float) or not isclose(float(actual_value), expected_value, abs_tol=0.1):
                failures.append(f"{case.name} feasibility input {key} changed")
        elif actual_value != expected_value:
            failures.append(f"{case.name} feasibility input {key} changed")
    for key in case.expected_missing_manual_dimensional_keys:
        manual_dimensional = result.artifacts.get("manual_dimensional_standards", {})
        if isinstance(manual_dimensional, dict) and key in manual_dimensional:
            failures.append(f"{case.name} manual dimensional artifact unexpectedly includes {key}")
    if not isclose(float(observed_pro_forma_args.get("estimated_land_value") or 0.0), case.expected_land_value):
        failures.append(f"{case.name} pro forma estimated_land_value changed")
    if not isclose(float(observed_pro_forma_args.get("adv_per_unit") or 0.0), case.expected_adv_per_unit):
        failures.append(f"{case.name} pro forma adv_per_unit changed")
    manual_comparables = result.artifacts.get("manual_comparables", {})
    if not isinstance(manual_comparables, dict) or manual_comparables.get("land_comp_count") != 2:
        failures.append(f"{case.name} manual land comp count changed")
    if not isinstance(manual_comparables, dict) or manual_comparables.get("exit_comp_count") != 3:
        failures.append(f"{case.name} manual exit comp count changed")
    expected_land_comp_quality = _MANUAL_LAND_COMP_QUALITY[case.name]
    if (
        not isinstance(manual_comparables, dict)
        or manual_comparables.get("land_comp_quality") != expected_land_comp_quality
    ):
        failures.append(f"{case.name} manual land comp quality changed")
    guidance = result.artifacts.get("acquisition_guidance", {})
    if not isinstance(guidance, dict) or guidance.get("recommended_action") != case.expected_action:
        failures.append(f"{case.name} acquisition guidance action changed")
    if not isinstance(guidance, dict) or guidance.get("pricing_source") != "manual_comps":
        failures.append(f"{case.name} acquisition guidance pricing source changed")
    if not isinstance(guidance, dict) or guidance.get("pricing_basis") != "user_supplied_comps":
        failures.append(f"{case.name} acquisition guidance pricing basis changed")
    if not isinstance(guidance, dict) or str(guidance.get("basis") or "") != case.expected_basis:
        failures.append(f"{case.name} acquisition guidance basis changed")
    if not isinstance(guidance, dict) or bool(guidance.get("land_comp_signal_available")) is not case.expected_land_signal_available:
        failures.append(f"{case.name} acquisition guidance land_comp_signal_available changed")
    if not isclose(float(guidance.get("recommended_offer") or 0.0), case.expected_guidance_offer):
        failures.append(f"{case.name} acquisition guidance recommended_offer changed")
    if not isclose(float(guidance.get("recommended_offer_low") or 0.0), case.expected_guidance_offer):
        failures.append(f"{case.name} acquisition guidance recommended_offer_low changed")
    if not isclose(float(guidance.get("recommended_offer_high") or 0.0), case.expected_guidance_offer):
        failures.append(f"{case.name} acquisition guidance recommended_offer_high changed")
    if not isclose(float(guidance.get("land_value_signal") or 0.0), case.expected_land_value):
        failures.append(f"{case.name} acquisition guidance land_value_signal changed")
    if not isclose(float(guidance.get("market_to_residual_gap") or 0.0), case.expected_market_gap):
        failures.append(f"{case.name} acquisition guidance market_to_residual_gap changed")
    if not isinstance(guidance, dict) or guidance.get("owner_basis_warning") != case.expected_owner_basis_warning:
        failures.append(f"{case.name} acquisition guidance owner_basis_warning changed")
    warnings = [item for item in result.artifacts.get("warnings", []) if isinstance(item, str)]
    if not any(case.expected_warning_substring in warning.lower() for warning in warnings):
        failures.append(f"{case.name} expected underwriting warning changed")
    if case.expected_frontage_warning_substring is not None and not any(
        case.expected_frontage_warning_substring in warning.lower() for warning in warnings
    ):
        failures.append(f"{case.name} parcel-geometry warning changed")
    if case.expected_manual_dimensional is not None:
        manual_dimensional = result.artifacts.get("manual_dimensional_standards", {})
        for key, expected_value in case.expected_manual_dimensional.items():
            actual_value = manual_dimensional.get(key) if isinstance(manual_dimensional, dict) else None
            if not isinstance(actual_value, int | float) or not isclose(float(actual_value), float(expected_value)):
                failures.append(f"{case.name} manual dimensional standard {key} changed")
    if case.expected_gis_warning is not None:
        gis_site_context = result.artifacts.get("gis_site_context", {})
        if not isinstance(gis_site_context, dict) or gis_site_context.get("warning") != case.expected_gis_warning:
            failures.append(f"{case.name} Broward GIS context warning changed")
    comp_claim = next((claim for claim in result.claims if claim.claim_type == "comp_value_signal"), None)
    if comp_claim is None or comp_claim.metadata.get("pricing_source") != "manual_comps":
        failures.append(f"{case.name} comp value claim pricing source changed")
    elif comp_claim.metadata.get("land_comp_quality") != expected_land_comp_quality:
        failures.append(f"{case.name} comp value claim land comp quality changed")
    land_comp_evidence = next(
        (item for item in result.evidence_items if item.source_url.endswith("-land-1") or item.source_url.endswith("land-1")),
        None,
    )
    if land_comp_evidence is None or land_comp_evidence.metadata.get("comp_quality_status") != "user_supplied_unscored":
        failures.append(f"{case.name} manual land comp evidence quality changed")
    if land_comp_evidence is None or land_comp_evidence.metadata.get("manual_override_used") is not True:
        failures.append(f"{case.name} manual land comp evidence override flag changed")
    return EvalCaseResult(
        name=case.name,
        passed=not failures,
        run_id=result.run_id,
        failures=failures,
        metrics={
            "tool_call_count": len(result.tool_calls),
            "warning_count": len(warnings),
            "evidence_count": len(result.evidence_items),
        },
    )


def _manual_offer_tool_payload(
    *,
    case: _ManualOfferEvalCase,
    request,
    observed_feasibility_args: JsonObject,
    observed_pro_forma_args: JsonObject,
) -> JsonObject:
    match request.tool_name:
        case "geocode_address":
            return {
                "status": "success",
                "result": {
                    "address": str(request.args["address"]),
                    "municipality": case.property_payload["municipality"],
                    "county": case.property_payload["county"],
                    "state": "FL",
                    "lat": case.property_payload["lat"],
                    "lng": case.property_payload["lng"],
                },
            }
        case "lookup_property_info":
            return {"status": "success", "result": case.property_payload}
        case "load_underwriting_market_profile":
            return {
                "profile": {
                    "market": case.property_payload["county"],
                    "source": "manual_eval",
                    "state": "FL",
                    "construction_cost_psf": case.pro_forma_result["construction_cost_psf"],
                    "avg_unit_size_sqft": case.pro_forma_result["avg_unit_size_sqft"],
                    "soft_cost_pct": case.pro_forma_result["soft_cost_pct"],
                    "builder_margin_pct": case.pro_forma_result["builder_margin_pct"],
                    "impact_fees_per_unit": case.pro_forma_result["impact_fees_per_unit"],
                    "monthly_rent_per_unit": case.request.assumptions["monthlyRentPerUnit"],
                    "vacancy_pct": 0.05,
                    "operating_expense_pct": case.request.assumptions["operatingExpensePct"],
                    "cap_rate": case.request.assumptions["capRate"],
                    "income_assumption_source": "user_input",
                    "overridden_fields": [],
                    "income_inferred_fields": [],
                    "requires_official_verification": False,
                    "assumptions_snapshot": dict(case.request.assumptions),
                },
                "rental_market_evidence": {},
            }
        case "find_comparables":
            return {
                "analysis": {
                    "comparables": [],
                    "unit_comparables": [],
                    "estimated_land_value": 0.0,
                    "adv_per_unit": 0.0,
                    "confidence": 0.0,
                    "notes": [],
                }
            }
        case "compute_feasibility":
            observed_feasibility_args.update(dict(request.args))
            return {"result": case.feasibility_result}
        case "run_pro_forma":
            observed_pro_forma_args.update(dict(request.args))
            return {"result": case.pro_forma_result}
        case "run_noi_valuation":
            return {"result": case.noi_result}
        case "run_residual_land_value":
            return {"result": case.residual_result}
        case "search_zoning_ordinance" | "search_municode_live" | "web_search":
            return {"status": "success", "results": []}
        case _:
            return {"status": "success", "result": dict(request.args)}


def _manual_offer_eval_cases() -> tuple[_ManualOfferEvalCase, _ManualOfferEvalCase]:
    return (
        _ManualOfferEvalCase(
            name="miami_gardens_manual_offer",
            request=FixtureDealRunRequest(
                address="45 NW 209 ST, Miami Gardens, FL 33169",
                analysis_type="acquisition_memo",
                source_mode=SourceMode.LIVE,
                assumptions={
                    "minLotAreaSf": 7500,
                    "maxDensityUnitsPerAcre": 6,
                    "minLotFrontageFt": 75,
                    "frontSetbackFt": 25,
                    "sideSetbackFt": 7.5,
                    "maxLotCoveragePct": 40,
                    "maxHeightFt": 35,
                    "maxStories": 2,
                    "waterSetbackFt": 0,
                    "accessorySeparationFt": 10,
                    "parkingSpacesPerUnit": 2,
                    "avgUnitSizeSf": 1700,
                    "monthlyRentPerUnit": 3200,
                    "operatingExpensePct": 0.35,
                    "capRate": 0.06,
                    "hardCosts": 265000,
                    "softCosts": 53000,
                    "contingency": 20000,
                    "developerFee": 25000,
                    "closingCosts": 12000,
                    "financingCosts": 18000,
                    "holdingCosts": 12000,
                    "sellingCosts": 35000,
                    "targetProfitPct": 0.18,
                    "manualLandComps": [
                        {"address": "17605 NW 19th Avenue, Miami Gardens, FL 33056", "salePrice": 135000, "saleDate": "2025-12-01", "lotSizeSqft": 9000, "sourceUrl": "https://example.test/land-1"},
                        {"address": "2940 NW 169th Ter, Miami Gardens, FL 33056", "salePrice": 145000, "saleDate": "2025-10-10", "lotSizeSqft": 10000, "sourceUrl": "https://example.test/land-2"},
                    ],
                    "manualExitComps": [
                        {"address": "105 NE 213th St, Miami Gardens, FL 33179", "salePrice": 699000, "saleDate": "2026-01-20", "units": 1, "sourceUrl": "https://example.test/exit-1"},
                        {"address": "115 NE 213th St, Miami Gardens, FL 33179", "salePrice": 500000, "saleDate": "2025-11-05", "units": 1, "sourceUrl": "https://example.test/exit-2"},
                        {"address": "100 NW 208th St, Miami Gardens, FL 33169", "salePrice": 500000, "saleDate": "2025-09-12", "units": 1, "sourceUrl": "https://example.test/exit-3"},
                    ],
                },
            ),
            property_payload={
                "folio": "3411360031910",
                "address": "45 NW 209 ST",
                "municipality": "Miami Gardens",
                "county": "Miami-Dade",
                "state": "FL",
                "lat": 25.967404,
                "lng": -80.202576,
                "zoning_code": "R-1",
                "ordinance_district_code": "R-1",
                "zoning_description": "Single-family detached residential",
                "land_use_code": "0066",
                "land_use_description": "VACANT RESIDENTIAL",
                "lot_size_sqft": 10105.0,
                "lot_dimensions": "75 x 134.73",
                "living_units": 0,
                "last_sale_price": 80000.0,
                "zoning_layer_url": "https://example.test/miami-gardens-zoning",
            },
            feasibility_result={"calculation_type": "feasibility", "formula_version": "feasibility.v2", "max_gross_buildable_sf": 4042.0, "net_rentable_sf": 3435.7, "estimated_units": 1, "parking_required": 2, "major_constraints": ["max_units"], "area_limiters": ["lot_coverage", "setback_envelope"], "lot_depth_ft": 134.73, "buildable_envelope_sf": 4468.2, "lot_coverage_limited_sf": 4042.0, "feasibility_warnings": []},
            pro_forma_result={"calculation_type": "pro_forma", "formula_version": "pro_forma.v1", "gross_development_value": 500000.0, "hard_costs": 265000.0, "soft_costs": 53000.0, "builder_margin": 25000.0, "impact_fees": 0.0, "impact_fees_per_unit": 0.0, "max_supportable_land_price": 120000.0, "cost_per_door": 343000.0, "construction_cost_psf": 155.88, "avg_unit_size_sqft": 1700.0, "adv_per_unit": 500000.0, "max_units": 1, "soft_cost_pct": 0.2, "builder_margin_pct": 0.05, "adv_source": "manual_comps", "market": "Miami-Dade", "notes": []},
            noi_result={"calculation_type": "noi_valuation", "formula_version": "noi_valuation.v1", "gross_scheduled_income": 38400.0, "effective_gross_income": 36480.0, "operating_expenses": 12768.0, "annual_noi": 23712.0, "as_built_value": 395200.0, "warnings": []},
            residual_result={"calculation_type": "residual_land_value", "formula_version": "residual_land_value.v1", "total_project_costs_excluding_land": 270000.0, "max_supportable_land_price": 120000.0, "spread_to_asking_price": 120000.0, "go_no_go_signal": "go", "warnings": []},
            expected_feasibility={"max_units": 1, "lot_frontage_ft": 75.0, "setback_front_ft": 25.0, "setback_side_ft": 7.5, "setback_rear_ft": 25.0, "max_lot_coverage_pct": 40.0},
            expected_land_value=149048.75,
            expected_adv_per_unit=500000.0,
            expected_offer=120000.0,
            expected_guidance_offer=120000.0,
            expected_action="offer_range",
            expected_basis="residual_and_market_signal",
            expected_land_signal_available=False,
            expected_market_gap=29048.75,
            expected_owner_basis_warning="Prior recorded sale price was 80000; seller expectations may exceed supportable pricing.",
            expected_warning_substring="preliminary staged zoning standards for miami gardens r-1",
            expected_manual_dimensional={"max_height_ft": 35.0, "max_stories": 2.0, "min_lot_frontage_ft": 75.0, "water_setback_ft": 0.0, "accessory_separation_ft": 10.0},
            expected_missing_manual_dimensional_keys=("rear_setback_ft",),
        ),
        _ManualOfferEvalCase(
            name="broward_manual_offer",
            request=FixtureDealRunRequest(
                address="1234 NW 15th St, Fort Lauderdale, FL 33311",
                analysis_type="acquisition_memo",
                source_mode=SourceMode.LIVE,
                assumptions={
                    "avgUnitSizeSf": 1700,
                    "monthlyRentPerUnit": 3200,
                    "operatingExpensePct": 0.35,
                    "capRate": 0.06,
                    "hardCosts": 285000,
                    "softCosts": 57000,
                    "contingency": 18000,
                    "developerFee": 30000,
                    "closingCosts": 12000,
                    "financingCosts": 18000,
                    "holdingCosts": 14000,
                    "sellingCosts": 26000,
                    "targetProfitPct": 0.18,
                    "manualLandComps": [
                        {"address": "1401 NW 14th Ave, Fort Lauderdale, FL 33311", "salePrice": 200000, "saleDate": "2026-02-11", "lotSizeSqft": 5000, "sourceUrl": "https://example.test/ftl-land-1"},
                        {"address": "1325 NW 15th Way, Fort Lauderdale, FL 33311", "salePrice": 220000, "saleDate": "2026-03-22", "lotSizeSqft": 5500, "sourceUrl": "https://example.test/ftl-land-2"},
                    ],
                    "manualExitComps": [
                        {"address": "1517 NE 5th Ct, Fort Lauderdale, FL 33301", "salePrice": 650000, "saleDate": "2026-01-18", "units": 1, "sourceUrl": "https://example.test/ftl-exit-1"},
                        {"address": "1320 NW 11th Pl, Fort Lauderdale, FL 33311", "salePrice": 625000, "saleDate": "2026-02-03", "units": 1, "sourceUrl": "https://example.test/ftl-exit-2"},
                        {"address": "1409 NW 16th Ter, Fort Lauderdale, FL 33311", "salePrice": 680000, "saleDate": "2026-03-01", "units": 1, "sourceUrl": "https://example.test/ftl-exit-3"},
                    ],
                },
            ),
            property_payload={
                "folio": "494233281490",
                "address": "1234 NW 15th St, Fort Lauderdale, FL 33311",
                "municipality": "Fort Lauderdale",
                "county": "Broward",
                "state": "FL",
                "lat": 26.1404,
                "lng": -80.1592,
                "zoning_code": "RS-8",
                "ordinance_district_code": "RS-8",
                "zoning_description": "Residential Single Family/Low Medium Density",
                "lot_size_sqft": 6000.0,
                "parcel_geometry": [[-80.1592, 26.1404], [-80.159051, 26.1404], [-80.159051, 26.1407297], [-80.1592, 26.1407297], [-80.1592, 26.1404]],
                "living_units": 0,
                "last_sale_price": 150000.0,
                "land_use_code": "VAC",
                "land_use_description": "VACANT RESIDENTIAL",
                "zoning_layer_url": "https://example.test/ftl-zoning",
            },
            feasibility_result={"calculation_type": "feasibility", "formula_version": "feasibility.v2", "max_gross_buildable_sf": 3000.0, "net_rentable_sf": 2550.0, "estimated_units": 1, "parking_required": 2, "major_constraints": ["lot_coverage"], "area_limiters": ["floor_area_ratio", "lot_coverage", "setback_envelope"], "lot_depth_ft": 120.0, "buildable_envelope_sf": 3200.0, "lot_coverage_limited_sf": 3000.0, "feasibility_warnings": []},
            pro_forma_result={"calculation_type": "pro_forma", "formula_version": "pro_forma.v1", "gross_development_value": 650000.0, "hard_costs": 285000.0, "soft_costs": 57000.0, "builder_margin": 30000.0, "impact_fees": 0.0, "impact_fees_per_unit": 0.0, "max_supportable_land_price": 180000.0, "cost_per_door": 372000.0, "construction_cost_psf": 167.65, "avg_unit_size_sqft": 1700.0, "adv_per_unit": 650000.0, "max_units": 1, "soft_cost_pct": 0.2, "builder_margin_pct": 0.05, "adv_source": "manual_comps", "market": "Broward", "notes": []},
            noi_result={"calculation_type": "noi_valuation", "formula_version": "noi_valuation.v1", "gross_scheduled_income": 38400.0, "effective_gross_income": 36480.0, "operating_expenses": 12768.0, "annual_noi": 27360.0, "as_built_value": 480000.0, "warnings": []},
            residual_result={"calculation_type": "residual_land_value", "formula_version": "residual_land_value.v1", "total_project_costs_excluding_land": 300000.0, "max_supportable_land_price": 180000.0, "spread_to_asking_price": 180000.0, "go_no_go_signal": "go", "warnings": []},
            expected_feasibility={"max_far": 0.75, "max_units": 1, "lot_frontage_ft": 48.69, "lot_depth_ft": 120.01, "setback_front_ft": 25.0, "setback_side_ft": 5.0, "setback_rear_ft": 15.0, "max_lot_coverage_pct": 50.0},
            expected_land_value=240000.0,
            expected_adv_per_unit=650000.0,
            expected_offer=180000.0,
            expected_guidance_offer=180000.0,
            expected_action="offer_range",
            expected_basis="residual_and_market_signal",
            expected_land_signal_available=False,
            expected_market_gap=60000.0,
            expected_owner_basis_warning="Prior recorded sale price was 150000; seller expectations may exceed supportable pricing.",
            expected_warning_substring="municipal parcels",
            expected_gis_warning="Broward county zoning layers are contextual for municipal parcels; use municipal zoning code or GIS for entitlement standards.",
            expected_frontage_warning_substring="estimated lot frontage from parcel geometry",
        ),
    )
