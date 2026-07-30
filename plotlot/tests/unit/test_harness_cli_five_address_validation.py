from __future__ import annotations

import json

import pytest
from pytest import MonkeyPatch

from plotlot.cli_harness import main
from plotlot.harness.five_address_support import (
    FIVE_ADDRESS_CASES,
    FiveAddressCase,
    build_assumptions,
    build_result,
)


@pytest.fixture(autouse=True)
def harness_store_path(tmp_path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("PLOTLOT_HARNESS_STORE_PATH", str(tmp_path / "harness-runs.json"))
    monkeypatch.setenv("PLOTLOT_HARNESS_JOB_STORE_PATH", str(tmp_path / "harness-jobs.json"))
    monkeypatch.setenv(
        "PLOTLOT_HARNESS_CALCULATION_STORE_PATH",
        str(tmp_path / "harness-calculations.json"),
    )
    monkeypatch.setenv(
        "PLOTLOT_HARNESS_EVIDENCE_STORE_PATH", str(tmp_path / "harness-evidence.json")
    )
    monkeypatch.setenv("PLOTLOT_HARNESS_REPORT_STORE_PATH", str(tmp_path / "harness-reports.json"))
    monkeypatch.setenv(
        "PLOTLOT_HARNESS_VERIFICATION_STORE_PATH",
        str(tmp_path / "harness-verifications.json"),
    )
    monkeypatch.setenv("PLOTLOT_HARNESS_TOOL_CALL_STORE_PATH", str(tmp_path / "tool-calls.json"))


@pytest.mark.parametrize(
    "case", FIVE_ADDRESS_CASES, ids=[case.address for case in FIVE_ADDRESS_CASES]
)
def test_cli_validates_five_miami_dade_and_broward_addresses(
    capsys,
    monkeypatch: MonkeyPatch,
    case: FiveAddressCase,
) -> None:
    async def _fake_tool_result(request):  # noqa: ANN001
        return build_result(case, request.tool_name, request.run_id, request.args)

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    exit_code = main(
        [
            "run",
            "acquisition-memo",
            "--address",
            case.address,
            "--source-mode",
            "live",
            "--assumptions-json",
            json.dumps(build_assumptions(case)),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "completed"
    assert payload["source_mode"] == "live"
    assert payload["verification_status"] == case.expected_verification_status
    assert payload["artifacts"]["site"]["municipality"] == case.municipality
    assert payload["artifacts"]["site"]["county"] == case.county
    assert (
        payload["artifacts"]["comp_search_strategy"]["land_signal_tier"]
        == case.expected_land_signal_tier
    )
    assert payload["artifacts"]["comp_search_strategy"]["sales_source_type"] == "curated_arcgis"
    assert payload["artifacts"]["comp_search_strategy"]["exit_comp_source_type"] == "curated_arcgis"
    assert (
        payload["artifacts"]["acquisition_guidance"]["recommended_action"] == case.expected_action
    )
    assert payload["artifacts"]["acquisition_guidance"]["basis"] == case.expected_basis
    assert payload["artifacts"]["acquisition_guidance"]["recommended_offer"] == pytest.approx(
        case.expected_guidance_offer
    )
    assert payload["artifacts"]["acquisition_guidance"]["land_value_signal"] == pytest.approx(
        case.expected_guidance_land_value
    )
    assert (
        payload["artifacts"]["acquisition_guidance"]["land_signal_strength"]
        == case.expected_land_signal_strength
    )
    assert (
        payload["artifacts"]["acquisition_guidance"]["land_comp_signal_available"]
        == case.expected_land_comp_signal_available
    )
    underwriting_section = next(
        section
        for section in payload["report"]["sections"]
        if section["section_id"] == "underwriting_summary"
    )
    support_summary = underwriting_section["comp_support_summary"]
    assert support_summary["status"] == case.expected_comp_support_status
    assert support_summary["combined_support_tier"] == case.expected_comp_support_tier
    assert support_summary["land_support_source"] == case.expected_land_support_source
    assert "public_listing_comps" not in {
        section["section_id"] for section in payload["report"]["sections"]
    }
    exit_comp_evidence = next(
        item
        for item in payload["evidence_items"]
        if item["structured_payload"].get("comp_type") == "unit_comparables"
    )
    assert exit_comp_evidence["metadata"]["comp_quality_status"] == "strong"
    assert exit_comp_evidence["metadata"]["qualification_score"] >= 0.86
