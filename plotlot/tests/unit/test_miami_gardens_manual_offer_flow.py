from __future__ import annotations

import pytest
from httpx import AsyncClient
from pytest import MonkeyPatch

from plotlot.domain.types import PolicyDecision
from plotlot.harness.contracts import RunId, SourceMode, ToolCallId
from plotlot.harness.tool_router import HarnessToolCallResult, ToolRouteStatus


def _default_payload(tool_name: str, args: dict[str, object]) -> dict[str, object]:
    match tool_name:
        case "run_noi_valuation":
            return {
                "calculation_type": "noi_valuation",
                "formula_version": "noi_valuation.v1",
                "gross_scheduled_income": 38400.0,
                "effective_gross_income": 36480.0,
                "operating_expenses": 12768.0,
                "annual_noi": 23712.0,
                "as_built_value": 395200.0,
                "warnings": [],
            }
        case "run_residual_land_value":
            return {
                "calculation_type": "residual_land_value",
                "formula_version": "residual_land_value.v1",
                "total_project_costs_excluding_land": 270000.0,
                "max_supportable_land_price": 120000.0,
                "spread_to_asking_price": 120000.0,
                "go_no_go_signal": "go",
                "warnings": [],
            }
        case "load_underwriting_market_profile":
            assumptions = args.get("assumptions")
            if not isinstance(assumptions, dict):
                assumptions = {}
            return {
                "profile": {
                    "market": args.get("county"),
                    "state": args.get("state", "FL"),
                    "monthly_rent_per_unit": assumptions.get("monthlyRentPerUnit"),
                    "vacancy_pct": 0.05,
                    "operating_expense_pct": assumptions.get("operatingExpensePct"),
                    "cap_rate": assumptions.get("capRate"),
                    "income_assumption_source": "user_input",
                    "overridden_fields": [],
                    "income_inferred_fields": [],
                    "requires_official_verification": False,
                    "assumptions_snapshot": dict(assumptions),
                },
                "rental_market_evidence": {},
            }
        case "search_municode_live" | "search_zoning_ordinance" | "web_search":
            return {"status": "success", "results": []}
        case _:
            return {"status": "success", "result": dict(args)}


@pytest.mark.asyncio
async def test_miami_gardens_manual_land_offer_flow_stays_conservative_with_partial_setbacks(
    client: AsyncClient,
    harness_store_path: None,
    monkeypatch: MonkeyPatch,
) -> None:
    observed_pro_forma_args: dict[str, object] = {}

    async def _fake_tool_result(request) -> HarnessToolCallResult:  # noqa: ANN001
        payload: dict[str, object]
        match request.tool_name:
            case "geocode_address":
                payload = {
                    "status": "success",
                    "result": {
                        "address": str(request.args["address"]),
                        "municipality": "Miami Gardens",
                        "county": "Miami-Dade",
                        "state": "FL",
                        "lat": 25.967404,
                        "lng": -80.202576,
                    },
                }
            case "lookup_property_info":
                payload = {
                    "status": "success",
                    "result": {
                        "folio": "3411360031910",
                        "address": "45 NW 209 ST",
                        "municipality": "Miami Gardens",
                        "county": "Miami-Dade",
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
                }
            case "compute_feasibility":
                assert request.args["max_units"] == 1
                assert request.args["lot_frontage_ft"] == pytest.approx(75.0)
                assert request.args["setback_front_ft"] == pytest.approx(25.0)
                assert request.args["setback_side_ft"] == pytest.approx(7.5)
                assert request.args["setback_rear_ft"] == pytest.approx(25.0)
                assert request.args["max_lot_coverage_pct"] == pytest.approx(40.0)
                payload = {
                    "result": {
                        "calculation_type": "feasibility",
                        "formula_version": "feasibility.v2",
                        "max_gross_buildable_sf": 4042.0,
                        "net_rentable_sf": 3435.7,
                        "estimated_units": 1,
                        "parking_required": 2,
                        "major_constraints": ["max_units"],
                        "area_limiters": ["lot_coverage", "setback_envelope"],
                        "lot_depth_ft": 134.73,
                        "buildable_envelope_sf": 4468.2,
                        "lot_coverage_limited_sf": 4042.0,
                        "feasibility_warnings": [],
                    }
                }
            case "run_pro_forma":
                observed_pro_forma_args.update(dict(request.args))
                payload = {
                    "result": {
                        "calculation_type": "pro_forma",
                        "formula_version": "pro_forma.v1",
                        "gross_development_value": 500000.0,
                        "hard_costs": 265000.0,
                        "soft_costs": 53000.0,
                        "builder_margin": 25000.0,
                        "impact_fees": 0.0,
                        "impact_fees_per_unit": 0.0,
                        "max_supportable_land_price": 120000.0,
                        "cost_per_door": 343000.0,
                        "construction_cost_psf": 155.88,
                        "avg_unit_size_sqft": 1700.0,
                        "adv_per_unit": 500000.0,
                        "max_units": 1,
                        "soft_cost_pct": 0.2,
                        "builder_margin_pct": 0.05,
                        "adv_source": "manual_comps",
                        "market": "Miami-Dade",
                        "notes": [],
                    }
                }
            case _:
                payload = _default_payload(request.tool_name, dict(request.args))

        return HarnessToolCallResult(
            ok=True,
            tool_call_id=ToolCallId(f"tool_call_{request.tool_name}"),
            tool_name=request.tool_name,
            run_id=RunId(str(request.run_id)),
            args=dict(request.args),
            status=ToolRouteStatus.COMPLETED,
            policy_decision=PolicyDecision(allowed=True, reason="test"),
            payload=payload,
            events=[],
            source_mode=SourceMode.LIVE,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "45 NW 209 ST, Miami Gardens, FL 33169",
            "analysis_type": "acquisition_memo",
            "source_mode": "live",
            "assumptions": {
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
                    {
                        "address": "17605 NW 19th Avenue, Miami Gardens, FL 33056",
                        "salePrice": 135000,
                        "saleDate": "2025-12-01",
                        "lotSizeSqft": 9000,
                        "sourceUrl": "https://example.test/land-1",
                    },
                    {
                        "address": "2940 NW 169th Ter, Miami Gardens, FL 33056",
                        "salePrice": 145000,
                        "saleDate": "2025-10-10",
                        "lotSizeSqft": 10000,
                        "sourceUrl": "https://example.test/land-2",
                    },
                ],
                "manualExitComps": [
                    {
                        "address": "105 NE 213th St, Miami Gardens, FL 33179",
                        "salePrice": 699000,
                        "saleDate": "2026-01-20",
                        "units": 1,
                        "sourceUrl": "https://example.test/exit-1",
                    },
                    {
                        "address": "115 NE 213th St, Miami Gardens, FL 33179",
                        "salePrice": 500000,
                        "saleDate": "2025-11-05",
                        "units": 1,
                        "sourceUrl": "https://example.test/exit-2",
                    },
                    {
                        "address": "100 NW 208th St, Miami Gardens, FL 33169",
                        "salePrice": 500000,
                        "saleDate": "2025-09-12",
                        "units": 1,
                        "sourceUrl": "https://example.test/exit-3",
                    },
                ],
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert observed_pro_forma_args["estimated_land_value"] == pytest.approx(149048.75)
    assert observed_pro_forma_args["adv_per_unit"] == pytest.approx(500000.0)
    assert data["artifacts"]["manual_comparables"]["land_comp_count"] == 2
    assert data["artifacts"]["manual_comparables"]["exit_comp_count"] == 3
    land_comp_quality = data["artifacts"]["manual_comparables"]["land_comp_quality"]
    assert land_comp_quality["land_comp_count"] == 2
    assert land_comp_quality["scored_land_comp_count"] == 0
    assert land_comp_quality["strong_land_comp_count"] == 0
    assert land_comp_quality["independent_land_comp_count"] == 2
    assert land_comp_quality["strong_independent_land_comp_count"] == 0
    assert land_comp_quality["land_comp_scores"] == []
    assert land_comp_quality["direct_land_comp_signal"] is False
    assert land_comp_quality["manual_override_used"] is True
    assert land_comp_quality["best_fit_score"] == pytest.approx(0.99)
    assert land_comp_quality["best_fit_lot_size_variance_ratio"] == pytest.approx(0.01)
    assert land_comp_quality["best_fit_qualification_score"] == pytest.approx(0.0)
    assert data["artifacts"]["manual_dimensional_standards"]["max_height_ft"] == pytest.approx(35.0)
    assert data["artifacts"]["manual_dimensional_standards"]["max_stories"] == pytest.approx(2.0)
    assert data["artifacts"]["manual_dimensional_standards"]["min_lot_frontage_ft"] == pytest.approx(75.0)
    assert data["artifacts"]["manual_dimensional_standards"]["water_setback_ft"] == pytest.approx(0.0)
    assert data["artifacts"]["manual_dimensional_standards"]["accessory_separation_ft"] == pytest.approx(10.0)
    assert "rear_setback_ft" not in data["artifacts"]["manual_dimensional_standards"]
    assert any(
        "preliminary staged zoning standards for miami gardens r-1" in warning.lower()
        for warning in data["artifacts"]["warnings"]
    )
    assert data["artifacts"]["acquisition_guidance"]["recommended_action"] == "offer_range"
    assert data["artifacts"]["acquisition_guidance"]["pricing_source"] == "manual_comps"
    assert data["artifacts"]["acquisition_guidance"]["pricing_basis"] == "user_supplied_comps"
    assert data["artifacts"]["acquisition_guidance"]["recommended_offer"] == pytest.approx(120000.0)
    assert data["artifacts"]["acquisition_guidance"]["recommended_offer_low"] == pytest.approx(120000.0)
    assert data["artifacts"]["acquisition_guidance"]["recommended_offer_high"] == pytest.approx(120000.0)
    assert data["artifacts"]["acquisition_guidance"]["land_value_signal"] == pytest.approx(149048.75)
    assert data["artifacts"]["acquisition_guidance"]["market_to_residual_gap"] == pytest.approx(29048.75)
    assert data["artifacts"]["acquisition_guidance"]["owner_basis_warning"] == (
        "Prior recorded sale price was 80000; seller expectations may exceed supportable pricing."
    )
    assert any(tool_call["tool_name"] == "run_residual_land_value" for tool_call in data["tool_calls"])
    comp_claim = next(claim for claim in data["claims"] if claim["claim_type"] == "comp_value_signal")
    assert comp_claim["metadata"]["pricing_source"] == "manual_comps"
    claim_land_comp_quality = comp_claim["metadata"]["land_comp_quality"]
    assert claim_land_comp_quality["land_comp_count"] == 2
    assert claim_land_comp_quality["scored_land_comp_count"] == 0
    assert claim_land_comp_quality["strong_land_comp_count"] == 0
    assert claim_land_comp_quality["independent_land_comp_count"] == 2
    assert claim_land_comp_quality["strong_independent_land_comp_count"] == 0
    assert claim_land_comp_quality["land_comp_scores"] == []
    assert claim_land_comp_quality["direct_land_comp_signal"] is False
    assert claim_land_comp_quality["manual_override_used"] is True
    assert claim_land_comp_quality["best_fit_score"] == pytest.approx(0.99)
    assert claim_land_comp_quality["best_fit_lot_size_variance_ratio"] == pytest.approx(0.01)
    assert claim_land_comp_quality["best_fit_qualification_score"] == pytest.approx(0.0)
    land_comp_evidence = next(
        item for item in data["evidence_items"] if item["source_url"] == "https://example.test/land-1"
    )
    assert land_comp_evidence["metadata"]["comp_quality_status"] == "user_supplied_unscored"
    assert land_comp_evidence["metadata"]["manual_override_used"] is True
    exit_comp_evidence = next(
        item for item in data["evidence_items"] if item["source_url"] == "https://example.test/exit-1"
    )
    assert exit_comp_evidence["metadata"]["comp_quality_status"] == "user_supplied_unscored"
    assert exit_comp_evidence["metadata"]["manual_override_used"] is True
    assert any(
        item["provider"] == "user_provided_comp"
        and item["source_url"] == "https://example.test/land-1"
        for item in data["evidence_items"]
    )


@pytest.mark.asyncio
async def test_miami_gardens_manual_offer_flow_requires_multiple_manual_land_comps(
    client: AsyncClient,
    harness_store_path: None,
    monkeypatch: MonkeyPatch,
) -> None:
    async def _fake_tool_result(request) -> HarnessToolCallResult:  # noqa: ANN001
        payload: dict[str, object]
        match request.tool_name:
            case "geocode_address":
                payload = {
                    "status": "success",
                    "result": {
                        "address": str(request.args["address"]),
                        "municipality": "Miami Gardens",
                        "county": "Miami-Dade",
                        "state": "FL",
                        "lat": 25.967404,
                        "lng": -80.202576,
                    },
                }
            case "lookup_property_info":
                payload = {
                    "status": "success",
                    "result": {
                        "folio": "3411360031910",
                        "address": "45 NW 209 ST",
                        "municipality": "Miami Gardens",
                        "county": "Miami-Dade",
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
                }
            case "compute_feasibility":
                payload = {
                    "result": {
                        "calculation_type": "feasibility",
                        "formula_version": "feasibility.v2",
                        "max_gross_buildable_sf": 4042.0,
                        "net_rentable_sf": 3435.7,
                        "estimated_units": 1,
                        "parking_required": 2,
                        "major_constraints": ["max_units"],
                        "area_limiters": ["lot_coverage"],
                        "lot_depth_ft": 134.73,
                        "buildable_envelope_sf": None,
                        "lot_coverage_limited_sf": 4042.0,
                        "feasibility_warnings": [
                            "Setback envelope was not calculated because one or more setback dimensions were missing."
                        ],
                    }
                }
            case "run_pro_forma":
                payload = {
                    "result": {
                        "calculation_type": "pro_forma",
                        "formula_version": "pro_forma.v1",
                        "gross_development_value": 500000.0,
                        "hard_costs": 265000.0,
                        "soft_costs": 53000.0,
                        "builder_margin": 25000.0,
                        "impact_fees": 0.0,
                        "impact_fees_per_unit": 0.0,
                        "max_supportable_land_price": 120000.0,
                        "cost_per_door": 343000.0,
                        "construction_cost_psf": 155.88,
                        "avg_unit_size_sqft": 1700.0,
                        "adv_per_unit": 500000.0,
                        "max_units": 1,
                        "soft_cost_pct": 0.2,
                        "builder_margin_pct": 0.05,
                        "adv_source": "manual_comps",
                        "market": "Miami-Dade",
                        "notes": [],
                    }
                }
            case _:
                payload = _default_payload(request.tool_name, dict(request.args))

        return HarnessToolCallResult(
            ok=True,
            tool_call_id=ToolCallId(f"tool_call_{request.tool_name}"),
            tool_name=request.tool_name,
            run_id=RunId(str(request.run_id)),
            args=dict(request.args),
            status=ToolRouteStatus.COMPLETED,
            policy_decision=PolicyDecision(allowed=True, reason="test"),
            payload=payload,
            events=[],
            source_mode=SourceMode.LIVE,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "45 NW 209 ST, Miami Gardens, FL 33169",
            "analysis_type": "acquisition_memo",
            "source_mode": "live",
            "assumptions": {
                "minLotAreaSf": 7500,
                "maxDensityUnitsPerAcre": 6,
                "minLotFrontageFt": 75,
                "frontSetbackFt": 25,
                "sideSetbackFt": 7.5,
                "maxLotCoveragePct": 40,
                "maxHeightFt": 35,
                "maxStories": 2,
                "parkingSpacesPerUnit": 2,
                "avgUnitSizeSf": 1700,
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
                    {
                        "address": "17605 NW 19th Avenue, Miami Gardens, FL 33056",
                        "salePrice": 135000,
                        "saleDate": "2025-12-01",
                        "lotSizeSqft": 9000,
                        "sourceUrl": "https://example.test/land-1",
                    }
                ],
                "manualExitComps": [
                    {
                        "address": "105 NE 213th St, Miami Gardens, FL 33179",
                        "salePrice": 699000,
                        "saleDate": "2026-01-20",
                        "units": 1,
                        "sourceUrl": "https://example.test/exit-1",
                    }
                ],
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["artifacts"]["manual_comparables"]["land_comp_count"] == 1
    assert data["artifacts"]["manual_comparables"]["exit_comp_count"] == 1
    assert data["artifacts"]["acquisition_guidance"]["recommended_action"] == "insufficient_support"
    assert data["artifacts"]["acquisition_guidance"]["land_comp_signal_available"] is False
    assert data["artifacts"]["acquisition_guidance"]["recommended_offer"] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_live_run_provides_risk_budget_to_municode_lookup(
    client: AsyncClient,
    harness_store_path: None,
    monkeypatch: MonkeyPatch,
) -> None:
    seen_municode_budget: int | None = None

    async def _fake_tool_result(request) -> HarnessToolCallResult:  # noqa: ANN001
        nonlocal seen_municode_budget

        match request.tool_name:
            case "geocode_address":
                payload: dict[str, object] = {
                    "status": "success",
                    "result": {
                        "address": str(request.args["address"]),
                        "municipality": "Miami Gardens",
                        "county": "Miami-Dade",
                        "state": "FL",
                        "lat": 25.967404,
                        "lng": -80.202576,
                    },
                }
            case "lookup_property_info":
                payload = {
                    "status": "success",
                    "result": {
                        "folio": "3411360031910",
                        "address": "45 NW 209 ST",
                        "municipality": "Miami Gardens",
                        "county": "Miami-Dade",
                        "state": "FL",
                        "zoning_code": "R-1",
                        "ordinance_district_code": "R-1",
                        "zoning_description": "Single-family detached residential",
                        "land_use_code": "0066",
                        "land_use_description": "VACANT RESIDENTIAL",
                        "lot_size_sqft": 10105.0,
                        "lot_dimensions": "75 x 134.73",
                        "living_units": 0,
                        "last_sale_price": 80000.0,
                    },
                }
            case "search_south_florida_gis":
                payload = {"status": "success", "results": [], "evidence": []}
            case "search_zoning_ordinance":
                payload = {"status": "success", "results": [], "evidence": []}
            case "search_municode_live":
                seen_municode_budget = request.context.risk_budget_cents
                payload = {"status": "success", "results": [], "evidence": []}
            case "find_comparables":
                payload = {
                    "status": "success",
                    "analysis": {
                        "comparables": [],
                        "unit_comparables": [],
                        "estimated_land_value": 0.0,
                        "confidence": 0.0,
                        "notes": [],
                    },
                    "evidence": [],
                }
            case "compute_feasibility":
                payload = {
                    "result": {
                        "calculation_type": "feasibility",
                        "formula_version": "feasibility.v2",
                        "max_gross_buildable_sf": 4042.0,
                        "net_rentable_sf": 3435.7,
                        "estimated_units": 1,
                        "parking_required": 2,
                        "major_constraints": ["max_units"],
                        "feasibility_warnings": [],
                    }
                }
            case "load_underwriting_market_profile":
                payload = {
                    "profile": {
                        "market": "Miami-Dade",
                        "state": "FL",
                        "monthly_rent_per_unit": 3200,
                        "vacancy_pct": 0.05,
                        "operating_expense_pct": 0.35,
                        "cap_rate": 0.06,
                        "income_assumption_source": "fixture",
                        "overridden_fields": [],
                        "income_inferred_fields": [],
                        "requires_official_verification": False,
                        "assumptions_snapshot": {},
                    },
                    "rental_market_evidence": {},
                }
            case "run_noi_valuation":
                payload = _default_payload(request.tool_name, dict(request.args))
            case "run_pro_forma":
                payload = {
                    "result": {
                        "calculation_type": "pro_forma",
                        "formula_version": "pro_forma.v1",
                        "gross_development_value": 500000.0,
                        "hard_costs": 265000.0,
                        "soft_costs": 53000.0,
                        "builder_margin": 25000.0,
                        "impact_fees": 0.0,
                        "impact_fees_per_unit": 0.0,
                        "max_supportable_land_price": 120000.0,
                        "cost_per_door": 343000.0,
                        "construction_cost_psf": 155.88,
                        "avg_unit_size_sqft": 1700.0,
                        "adv_per_unit": 500000.0,
                        "max_units": 1,
                        "soft_cost_pct": 0.2,
                        "builder_margin_pct": 0.05,
                        "adv_source": "manual_comps",
                        "market": "Miami-Dade",
                        "notes": [],
                    }
                }
            case "run_residual_land_value":
                payload = _default_payload(request.tool_name, dict(request.args))
            case "generate_acquisition_memo":
                payload = {
                    "report_id": "report_fixture",
                    "title": "Fixture acquisition memo",
                    "status": "draft",
                    "sections": [],
                    "claims": [],
                    "evidence_ids": [],
                    "calculation_ids": [],
                }
            case "verify_report":
                payload = {
                    "status": "passed_with_warnings",
                    "checks": [],
                    "missing_evidence": [],
                    "stale_evidence": [],
                    "math_errors": [],
                    "unsupported_claims": [],
                    "jurisdiction_mismatches": [],
                    "mock_or_fixture_blockers": [],
                }
            case _:
                payload = _default_payload(request.tool_name, dict(request.args))

        return HarnessToolCallResult(
            ok=True,
            tool_call_id=ToolCallId(f"tool_call_{request.tool_name}"),
            tool_name=request.tool_name,
            run_id=RunId(str(request.run_id)),
            args=dict(request.args),
            status=ToolRouteStatus.COMPLETED,
            policy_decision=PolicyDecision(allowed=True, reason="test"),
            payload=payload,
            events=[],
            source_mode=SourceMode.LIVE,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "45 NW 209 ST, Miami Gardens, FL 33169",
            "analysis_type": "acquisition_memo",
            "source_mode": "live",
            "assumptions": {
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
                "manualExitComps": [
                    {
                        "address": "105 NE 213th St, Miami Gardens, FL 33179",
                        "salePrice": 699000,
                        "saleDate": "2026-01-20",
                        "units": 1,
                        "sourceUrl": "https://example.test/exit-1",
                    }
                ],
            },
        },
    )

    assert response.status_code == 200
    assert seen_municode_budget is not None
    assert seen_municode_budget >= 25
