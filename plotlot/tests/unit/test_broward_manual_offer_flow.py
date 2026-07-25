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
                "max_supportable_land_price": 180000.0,
                "spread_to_asking_price": 180000.0,
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
async def test_fort_lauderdale_manual_land_offer_flow_uses_verified_standard_and_contextual_broward_gis(
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
                        "municipality": "Fort Lauderdale",
                        "county": "Broward",
                        "state": "FL",
                        "lat": 26.1404,
                        "lng": -80.1592,
                    },
                }
            case "lookup_property_info":
                parcel_geometry = [
                    [-80.1592, 26.1404],
                    [-80.159051, 26.1404],
                    [-80.159051, 26.1407297],
                    [-80.1592, 26.1407297],
                    [-80.1592, 26.1404],
                ]
                payload = {
                    "status": "success",
                    "result": {
                        "folio": "494233281490",
                        "address": "1234 NW 15th St, Fort Lauderdale, FL 33311",
                        "municipality": "Fort Lauderdale",
                        "county": "Broward",
                        "zoning_code": "RS-8",
                        "ordinance_district_code": "RS-8",
                        "zoning_description": "Residential Single Family/Low Medium Density",
                        "lot_size_sqft": 6000.0,
                        "parcel_geometry": parcel_geometry,
                        "living_units": 0,
                        "last_sale_price": 150000.0,
                        "lat": 26.1404,
                        "lng": -80.1592,
                        "zoning_layer_url": "https://example.test/ftl-zoning",
                    },
                }
            case "compute_feasibility":
                assert request.args["max_far"] == pytest.approx(0.75)
                assert request.args["max_units"] == 1
                assert request.args["lot_frontage_ft"] == pytest.approx(48.69, abs=0.1)
                assert request.args["lot_depth_ft"] == pytest.approx(120.01, abs=0.1)
                assert request.args["setback_front_ft"] == pytest.approx(25.0)
                assert request.args["setback_side_ft"] == pytest.approx(5.0)
                assert request.args["setback_rear_ft"] == pytest.approx(15.0)
                assert request.args["max_lot_coverage_pct"] == pytest.approx(50.0)
                payload = {
                    "result": {
                        "calculation_type": "feasibility",
                        "formula_version": "feasibility.v2",
                        "max_gross_buildable_sf": 3000.0,
                        "net_rentable_sf": 2550.0,
                        "estimated_units": 1,
                        "parking_required": 2,
                        "major_constraints": ["lot_coverage"],
                        "area_limiters": ["floor_area_ratio", "lot_coverage", "setback_envelope"],
                        "lot_depth_ft": 120.0,
                        "buildable_envelope_sf": 3200.0,
                        "lot_coverage_limited_sf": 3000.0,
                        "feasibility_warnings": [],
                    }
                }
            case "run_pro_forma":
                observed_pro_forma_args.update(dict(request.args))
                payload = {
                    "result": {
                        "calculation_type": "pro_forma",
                        "formula_version": "pro_forma.v1",
                        "gross_development_value": 650000.0,
                        "hard_costs": 285000.0,
                        "soft_costs": 57000.0,
                        "builder_margin": 30000.0,
                        "impact_fees": 0.0,
                        "impact_fees_per_unit": 0.0,
                        "max_supportable_land_price": 180000.0,
                        "cost_per_door": 372000.0,
                        "construction_cost_psf": 167.65,
                        "avg_unit_size_sqft": 1700.0,
                        "adv_per_unit": 650000.0,
                        "max_units": 1,
                        "soft_cost_pct": 0.2,
                        "builder_margin_pct": 0.05,
                        "adv_source": "manual_comps",
                        "market": "Broward",
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
            "address": "1234 NW 15th St, Fort Lauderdale, FL 33311",
            "analysis_type": "acquisition_memo",
            "source_mode": "live",
            "assumptions": {
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
                    {
                        "address": "1401 NW 14th Ave, Fort Lauderdale, FL 33311",
                        "salePrice": 200000,
                        "saleDate": "2026-02-11",
                        "lotSizeSqft": 5000,
                        "sourceUrl": "https://example.test/ftl-land-1",
                    },
                    {
                        "address": "1325 NW 15th Way, Fort Lauderdale, FL 33311",
                        "salePrice": 220000,
                        "saleDate": "2026-03-22",
                        "lotSizeSqft": 5500,
                        "sourceUrl": "https://example.test/ftl-land-2",
                    },
                ],
                "manualExitComps": [
                    {
                        "address": "1517 NE 5th Ct, Fort Lauderdale, FL 33301",
                        "salePrice": 650000,
                        "saleDate": "2026-01-18",
                        "units": 1,
                        "sourceUrl": "https://example.test/ftl-exit-1",
                    },
                    {
                        "address": "1320 NW 11th Pl, Fort Lauderdale, FL 33311",
                        "salePrice": 625000,
                        "saleDate": "2026-02-03",
                        "units": 1,
                        "sourceUrl": "https://example.test/ftl-exit-2",
                    },
                    {
                        "address": "1409 NW 16th Ter, Fort Lauderdale, FL 33311",
                        "salePrice": 680000,
                        "saleDate": "2026-03-01",
                        "units": 1,
                        "sourceUrl": "https://example.test/ftl-exit-3",
                    },
                ],
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["verification_status"] == "passed_with_warnings"
    assert observed_pro_forma_args["estimated_land_value"] == pytest.approx(240000.0)
    assert observed_pro_forma_args["adv_per_unit"] == pytest.approx(650000.0)
    assert data["artifacts"]["gis_site_context"]["county"] == "Broward"
    assert data["artifacts"]["gis_site_context"]["municipality"] == "Fort Lauderdale"
    assert (
        data["artifacts"]["gis_site_context"]["warning"]
        == "Broward county zoning layers are contextual for municipal parcels; use municipal zoning code or GIS for entitlement standards."
    )
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
    assert land_comp_quality["best_fit_score"] == pytest.approx(0.917, abs=0.001)
    assert land_comp_quality["best_fit_lot_size_variance_ratio"] == pytest.approx(0.083, abs=0.001)
    assert land_comp_quality["best_fit_qualification_score"] == pytest.approx(0.0)
    assert any(
        "estimated lot frontage from parcel geometry" in warning
        for warning in data["artifacts"].get("warnings", [])
    )
    assert data["artifacts"]["acquisition_guidance"]["recommended_action"] == "offer_range"
    assert data["artifacts"]["acquisition_guidance"]["pricing_source"] == "manual_comps"
    assert data["artifacts"]["acquisition_guidance"]["pricing_basis"] == "user_supplied_comps"
    assert data["artifacts"]["acquisition_guidance"]["recommended_offer"] == pytest.approx(180000.0)
    assert data["artifacts"]["acquisition_guidance"]["recommended_offer_low"] == pytest.approx(180000.0)
    assert data["artifacts"]["acquisition_guidance"]["recommended_offer_high"] == pytest.approx(180000.0)
    assert data["artifacts"]["acquisition_guidance"]["land_value_signal"] == pytest.approx(240000.0)
    assert data["artifacts"]["acquisition_guidance"]["market_to_residual_gap"] == pytest.approx(60000.0)
    assert data["artifacts"]["acquisition_guidance"]["owner_basis_warning"] == (
        "Prior recorded sale price was 150000; seller expectations may exceed supportable pricing."
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
    assert claim_land_comp_quality["best_fit_score"] == pytest.approx(0.917, abs=0.001)
    assert claim_land_comp_quality["best_fit_lot_size_variance_ratio"] == pytest.approx(0.083, abs=0.001)
    assert claim_land_comp_quality["best_fit_qualification_score"] == pytest.approx(0.0)
    land_comp_evidence = next(
        item for item in data["evidence_items"] if item["source_url"] == "https://example.test/ftl-land-1"
    )
    assert land_comp_evidence["metadata"]["comp_quality_status"] == "user_supplied_unscored"
    assert land_comp_evidence["metadata"]["manual_override_used"] is True
    exit_comp_evidence = next(
        item for item in data["evidence_items"] if item["source_url"] == "https://example.test/ftl-exit-1"
    )
    assert exit_comp_evidence["metadata"]["comp_quality_status"] == "user_supplied_unscored"
    assert exit_comp_evidence["metadata"]["manual_override_used"] is True
    assert any(
        item["source_type"] == "gis_layer"
        and item["applicability"] == "requires_municipal_verification"
        for item in data["evidence_items"]
    )
    assert any(
        item["provider"] == "user_provided_comp"
        and item["source_url"] == "https://example.test/ftl-land-1"
        for item in data["evidence_items"]
    )
