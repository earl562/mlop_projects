from __future__ import annotations

import pytest
from httpx import AsyncClient
from pytest import MonkeyPatch

from plotlot.harness.five_address_support import (
    FIVE_ADDRESS_CASES,
    FiveAddressCase,
    build_assumptions,
    build_result,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", FIVE_ADDRESS_CASES, ids=[case.address for case in FIVE_ADDRESS_CASES])
async def test_harness_validates_five_miami_dade_and_broward_addresses(
    client: AsyncClient,
    harness_store_path: None,
    monkeypatch: MonkeyPatch,
    case: FiveAddressCase,
) -> None:
    async def _fake_tool_result(request):  # noqa: ANN001
        return build_result(case, request.tool_name, request.run_id, request.args)

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": case.address,
            "analysis_type": "acquisition_memo",
            "source_mode": "live",
            "assumptions": build_assumptions(case),
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["source_mode"] == "live"
    assert data["verification_status"] == case.expected_verification_status
    assert data["artifacts"]["site"]["municipality"] == case.municipality
    assert data["artifacts"]["site"]["county"] == case.county
    assert data["artifacts"]["comp_search_strategy"]["land_signal_tier"] == case.expected_land_signal_tier
    assert data["artifacts"]["comp_search_strategy"]["sales_source_type"] == "curated_arcgis"
    assert data["artifacts"]["comp_search_strategy"]["exit_comp_source_type"] == "curated_arcgis"
    assert data["artifacts"]["acquisition_guidance"]["recommended_action"] == case.expected_action
    assert data["artifacts"]["acquisition_guidance"]["basis"] == case.expected_basis
    assert data["artifacts"]["acquisition_guidance"]["recommended_offer"] == pytest.approx(
        case.expected_guidance_offer
    )
    assert data["artifacts"]["acquisition_guidance"]["land_value_signal"] == pytest.approx(
        case.expected_guidance_land_value
    )
    assert (
        data["artifacts"]["acquisition_guidance"]["land_signal_strength"]
        == case.expected_land_signal_strength
    )
    assert (
        data["artifacts"]["acquisition_guidance"]["land_comp_signal_available"]
        == case.expected_land_comp_signal_available
    )
    underwriting_section = next(
        section
        for section in data["report"]["sections"]
        if section["section_id"] == "underwriting_summary"
    )
    support_summary = underwriting_section["comp_support_summary"]
    assert support_summary["status"] == case.expected_comp_support_status
    assert support_summary["combined_support_tier"] == case.expected_comp_support_tier
    assert support_summary["land_support_source"] == case.expected_land_support_source
    assert "public_listing_comps" not in {section["section_id"] for section in data["report"]["sections"]}
    exit_comp_evidence = next(
        item for item in data["evidence_items"] if item["structured_payload"].get("comp_type") == "unit_comparables"
    )
    assert exit_comp_evidence["metadata"]["comp_quality_status"] == "strong"
    assert exit_comp_evidence["metadata"]["qualification_score"] >= 0.86
