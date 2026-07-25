from __future__ import annotations

from unittest.mock import patch

from plotlot.harness.contracts import ExecutionMode, JsonObject, RunId, SourceMode
from plotlot.harness.eval_models import EvalCaseResult, EvalResult, eval_result
from plotlot.harness.five_address_support import (
    FIVE_ADDRESS_CASES,
    FiveAddressCase,
    build_assumptions,
    build_result,
)
from plotlot.harness.fixture_runs import FixtureDealRunRequest, run_deal_analysis


def south_florida_five_address_suite() -> EvalResult:
    return eval_result(
        "south-florida-five-addresses",
        [_evaluate_case(case) for case in FIVE_ADDRESS_CASES],
    )


def _evaluate_case(case: FiveAddressCase) -> EvalCaseResult:
    async def _fake_tool_result(request):  # noqa: ANN001
        return build_result(
            case=case,
            tool_name=request.tool_name,
            run_id=RunId(str(request.run_id)),
            args=request.args,
        )

    with patch("plotlot.harness.fixture_runs._tool_result", _fake_tool_result):
        result = run_deal_analysis(
            FixtureDealRunRequest(
                address=case.address,
                analysis_type="acquisition_memo",
                source_mode=SourceMode.LIVE,
                execution_mode=ExecutionMode.LOCAL,
                assumptions=build_assumptions(case),
            )
        )

    failures = _collect_failures(case, result.model_dump(mode="json"))
    return EvalCaseResult(
        name=case.address,
        passed=not failures,
        run_id=result.run_id,
        failures=failures,
        metrics={
            "event_count": len(result.events),
            "evidence_count": len(result.evidence_items),
            "claim_count": len(result.claims),
        },
    )


def _collect_failures(case: FiveAddressCase, payload: JsonObject) -> list[str]:
    failures: list[str] = []
    artifacts = payload.get("artifacts")
    report = payload.get("report")
    evidence_items = payload.get("evidence_items")
    if payload.get("status") != "completed":
        failures.append("run did not complete")
    if payload.get("source_mode") != "live":
        failures.append("run did not preserve live mode")
    if payload.get("verification_status") != case.expected_verification_status:
        failures.append("verification status changed")
    if not isinstance(artifacts, dict):
        return ["artifacts missing"]
    site = artifacts.get("site")
    comp_search_strategy = artifacts.get("comp_search_strategy")
    guidance = artifacts.get("acquisition_guidance")
    if not isinstance(site, dict) or site.get("municipality") != case.municipality or site.get("county") != case.county:
        failures.append("site context changed")
    if not isinstance(comp_search_strategy, dict) or comp_search_strategy.get("land_signal_tier") != case.expected_land_signal_tier:
        failures.append("comp search strategy tier changed")
    if not isinstance(comp_search_strategy, dict) or comp_search_strategy.get("sales_source_type") != "curated_arcgis":
        failures.append("sales source type changed")
    if not isinstance(comp_search_strategy, dict) or comp_search_strategy.get("exit_comp_source_type") != "curated_arcgis":
        failures.append("exit comp source type changed")
    if not isinstance(guidance, dict) or guidance.get("recommended_action") != case.expected_action:
        failures.append("acquisition guidance action changed")
    if not isinstance(guidance, dict) or guidance.get("basis") != case.expected_basis:
        failures.append("acquisition guidance basis changed")
    if not isinstance(guidance, dict) or guidance.get("recommended_offer") != case.expected_guidance_offer:
        failures.append("acquisition guidance offer changed")
    if not isinstance(guidance, dict) or guidance.get("land_value_signal") != case.expected_guidance_land_value:
        failures.append("acquisition guidance land value changed")
    if not isinstance(guidance, dict) or guidance.get("land_signal_strength") != case.expected_land_signal_strength:
        failures.append("land signal strength changed")
    if not isinstance(guidance, dict) or guidance.get("land_comp_signal_available") is not case.expected_land_comp_signal_available:
        failures.append("land comp signal availability changed")
    if isinstance(report, dict):
        sections = [section for section in report.get("sections", []) if isinstance(section, dict)]
        section_ids = {section.get("section_id") for section in sections}
        if "public_listing_comps" in section_ids:
            failures.append("report unexpectedly includes public listing comps")
        underwriting_section = next(
            (section for section in sections if section.get("section_id") == "underwriting_summary"),
            None,
        )
        if not isinstance(underwriting_section, dict):
            failures.append("underwriting section missing")
        else:
            support_summary = underwriting_section.get("comp_support_summary")
            if not isinstance(support_summary, dict):
                failures.append("comp support summary missing")
            else:
                if support_summary.get("status") != case.expected_comp_support_status:
                    failures.append("comp support status changed")
                if support_summary.get("combined_support_tier") != case.expected_comp_support_tier:
                    failures.append("comp support tier changed")
                if support_summary.get("land_support_source") != case.expected_land_support_source:
                    failures.append("land support source changed")
    else:
        failures.append("report missing")
    if isinstance(evidence_items, list):
        exit_comp_evidence = next(
            (
                item
                for item in evidence_items
                if isinstance(item, dict)
                and isinstance(item.get("structured_payload"), dict)
                and item["structured_payload"].get("comp_type") == "unit_comparables"
            ),
            None,
        )
        if not isinstance(exit_comp_evidence, dict):
            failures.append("exit comp evidence missing")
        else:
            metadata = exit_comp_evidence.get("metadata")
            if not isinstance(metadata, dict) or metadata.get("comp_quality_status") != "strong":
                failures.append("exit comp evidence quality changed")
    else:
        failures.append("evidence items missing")
    return failures
