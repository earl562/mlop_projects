from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch

from plotlot.api.main import app
from plotlot.harness.contracts import RunId, ToolCallId
from plotlot.harness.fixture_runs import (
    CountyReconciliationCandidate,
    _listing_candidate_matches_county_record,
)
from plotlot.harness.tool_router import HarnessToolCallResult, ToolRouteStatus
from plotlot.harness.policy import PolicyDecision


@pytest.fixture
def transport() -> ASGITransport:
    return ASGITransport(app=app)


@pytest.fixture
async def client(transport: ASGITransport):
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def test_county_reconciliation_requires_sale_date_alignment() -> None:
    assert _listing_candidate_matches_county_record(
        CountyReconciliationCandidate(
            listed_address="17605 NW 19th Avenue, Miami Gardens, FL 33056",
            listed_sale_price=135000.0,
            listed_sale_date="2026-04-21",
            listed_lot_size_sqft=9000.0,
            county_address="17605 NW 19th Avenue",
            county_sale_price=135000.0,
            county_sale_date="2026-04-30",
            county_lot_size_sqft=9000.0,
        )
    )


def test_county_reconciliation_accepts_county_slash_date_format() -> None:
    assert _listing_candidate_matches_county_record(
        CountyReconciliationCandidate(
            listed_address="17605 NW 19th Avenue, Miami Gardens, FL 33056",
            listed_sale_price=135000.0,
            listed_sale_date="2026-04-21",
            listed_lot_size_sqft=9000.0,
            county_address="17605 NW 19th Avenue",
            county_sale_price=135000.0,
            county_sale_date="04/30/2026",
            county_lot_size_sqft=9000.0,
        )
    )


def test_county_reconciliation_accepts_numeric_street_without_ordinal_suffix() -> None:
    assert _listing_candidate_matches_county_record(
        CountyReconciliationCandidate(
            listed_address="17605 NW 19th Avenue, Miami Gardens, FL 33056",
            listed_sale_price=135000.0,
            listed_sale_date="2026-04-21",
            listed_lot_size_sqft=9000.0,
            county_address="17605 NW 19 Ave",
            county_sale_price=135000.0,
            county_sale_date="2026-04-30",
            county_lot_size_sqft=9000.0,
        )
    )


def test_county_reconciliation_accepts_missing_direction_when_street_number_and_type_align() -> None:
    assert _listing_candidate_matches_county_record(
        CountyReconciliationCandidate(
            listed_address="17605 NW 19th Avenue, Miami Gardens, FL 33056",
            listed_sale_price=135000.0,
            listed_sale_date="2026-04-21",
            listed_lot_size_sqft=9000.0,
            county_address="17605 19 Ave",
            county_sale_price=135000.0,
            county_sale_date="2026-04-30",
            county_lot_size_sqft=9000.0,
        )
    )


def test_county_reconciliation_rejects_stale_sale_date_match() -> None:
    assert not _listing_candidate_matches_county_record(
        CountyReconciliationCandidate(
            listed_address="17605 NW 19th Avenue, Miami Gardens, FL 33056",
            listed_sale_price=135000.0,
            listed_sale_date="2026-04-21",
            listed_lot_size_sqft=9000.0,
            county_address="17605 NW 19th Avenue",
            county_sale_price=135000.0,
            county_sale_date="2025-01-15",
            county_lot_size_sqft=9000.0,
        )
    )


@pytest.mark.asyncio
async def test_live_run_rejects_county_reconciliation_when_sale_dates_do_not_align(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    async def _fake_tool_result(request) -> HarnessToolCallResult:
        if request.tool_name == "geocode_address":
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
        elif request.tool_name == "lookup_property_info":
            requested_address = str(request.args["address"])
            if "17605 NW 19th" in requested_address:
                payload = {
                    "status": "success",
                    "result": {
                        "folio": "3412110001000",
                        "address": "17605 NW 19th Avenue",
                        "municipality": "Miami Gardens",
                        "county": "Miami-Dade",
                        "zoning_code": "R-1",
                        "ordinance_district_code": "R-1",
                        "zoning_description": "Single-family dwelling residential district",
                        "land_use_code": "0066",
                        "land_use_description": "VACANT RESIDENTIAL",
                        "lot_size_sqft": 9000.0,
                        "living_units": 0,
                        "last_sale_price": 135000.0,
                        "last_sale_date": "2025-01-15",
                        "lat": 25.936991,
                        "lng": -80.235842,
                        "zoning_layer_url": "https://example.test/miami-gardens-zoning",
                    },
                }
            else:
                payload = {
                    "status": "success",
                    "result": {
                        "folio": "3411360031910",
                        "address": "45 NW 209 ST",
                        "municipality": "Miami Gardens",
                        "county": "Miami-Dade",
                        "zoning_code": "R-1",
                        "ordinance_district_code": "R-1",
                        "zoning_description": "Single-family dwelling residential district",
                        "land_use_code": "0066",
                        "land_use_description": "VACANT RESIDENTIAL",
                        "lot_size_sqft": 10105.0,
                        "living_units": 0,
                        "lat": 25.967404,
                        "lng": -80.202576,
                        "zoning_layer_url": "https://example.test/miami-gardens-zoning",
                    },
                }
        elif request.tool_name == "find_comparables":
            payload = {
                "analysis": {
                    "comparables": [],
                    "unit_comparables": [
                        {
                            "address": "105 NE 213 ST",
                            "sale_price": 699000.0,
                            "sale_date": "2026-04-21",
                            "lot_size_sqft": 7500.0,
                            "zoning_code": "",
                            "distance_miles": 0.34,
                            "price_per_acre": 0.0,
                            "price_per_unit": 699000.0,
                            "adjustments": {"qualification_score": 0.92},
                        }
                    ],
                    "estimated_land_value": 0.0,
                    "adv_per_unit": 699000.0,
                    "confidence": 0.55,
                    "web_listing_search": {
                        "query": "miami gardens sold vacant land comps",
                        "provider": "exa",
                        "status": "success",
                        "result_count": 1,
                        "selected_search_window_months": 12,
                    },
                    "web_listing_candidates": [
                        {
                            "title": "17605 NW 19th Avenue, Miami Gardens, FL 33056 | Zillow",
                            "url": "https://www.zillow.com/homedetails/example",
                            "address_hint": "17605 NW 19th Avenue, Miami Gardens, FL 33056",
                            "source_domain": "www.zillow.com",
                            "query": "miami gardens sold vacant land comps",
                            "description": "Public sold listing candidate.",
                            "candidate_kind": "listing_candidate",
                            "classification": "likely_vacant_land",
                            "confidence": 0.85,
                            "search_window_months": 12,
                            "fit_score": 0.92,
                            "lot_size_variance_ratio": 0.08,
                        }
                    ],
                }
            }
        elif request.tool_name == "fetch_web_contents":
            payload = {
                "status": "success",
                "provider": "exa",
                "results": [
                    {
                        "title": "17605 NW 19th Avenue, Miami Gardens, FL 33056 | Zillow",
                        "url": "https://www.zillow.com/homedetails/example",
                        "description": "Sold for $135,000 on 2026-04-21. Lot size: 9,000 sqft.",
                        "content": "Public sold listing. Sold for $135,000 on 2026-04-21. Lot size 9,000 sqft.",
                    }
                ],
            }
        elif request.tool_name == "capture_public_listing_comps":
            payload = {
                "status": "success",
                "provider": "browser_use",
                "strategy": "public_sold_listing_capture",
                "candidates": [],
                "warnings": [],
            }
        else:
            from tests.unit.test_harness_api import _live_tool_payload

            payload = _live_tool_payload(request.tool_name, dict(request.args))

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
            source_mode=request.source_mode,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "45 NW 209 ST, Miami Gardens, FL 33169",
            "analysis_type": "acquisition_memo",
            "source_mode": "live",
            "assumptions": {
                "maxUnits": 1,
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
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    reconciliation = data["artifacts"]["contextual_land_listing_reconciliation"]
    assert reconciliation["status"] == "no_county_record_match"
    assert reconciliation["reconciled_candidate_count"] == 0
    assert reconciliation["rejected_candidate_count"] == 1
    assert reconciliation["rejected_candidates"][0]["reason"] == "candidate_listing_facts_do_not_match_county_record"
    assert data["artifacts"]["comp_search_strategy"]["county_reconciled_candidate_count"] == 0
    assert data["artifacts"]["comp_search_strategy"]["land_signal_tier"] != "county_reconciled_public_listing"
    public_listing_comps = data["artifacts"]["comps"].get("public_listing_land_comparables", [])
    assert not any(comp.get("verification_status") == "county_reconciled" for comp in public_listing_comps)


@pytest.mark.asyncio
async def test_live_run_accepts_county_reconciliation_with_slash_date_format(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    async def _fake_tool_result(request) -> HarnessToolCallResult:
        if request.tool_name == "geocode_address":
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
        elif request.tool_name == "lookup_property_info":
            requested_address = str(request.args["address"])
            if "17605 NW 19th" in requested_address:
                payload = {
                    "status": "success",
                    "result": {
                        "folio": "3412110001000",
                        "address": "17605 NW 19th Avenue",
                        "municipality": "Miami Gardens",
                        "county": "Miami-Dade",
                        "zoning_code": "R-1",
                        "ordinance_district_code": "R-1",
                        "zoning_description": "Single-family dwelling residential district",
                        "land_use_code": "0066",
                        "land_use_description": "VACANT RESIDENTIAL",
                        "lot_size_sqft": 9000.0,
                        "living_units": 0,
                        "last_sale_price": 135000.0,
                        "last_sale_date": "04/30/2026",
                        "lat": 25.936991,
                        "lng": -80.235842,
                        "zoning_layer_url": "https://example.test/miami-gardens-zoning",
                    },
                }
            else:
                payload = {
                    "status": "success",
                    "result": {
                        "folio": "3411360031910",
                        "address": "45 NW 209 ST",
                        "municipality": "Miami Gardens",
                        "county": "Miami-Dade",
                        "zoning_code": "R-1",
                        "ordinance_district_code": "R-1",
                        "zoning_description": "Single-family dwelling residential district",
                        "land_use_code": "0066",
                        "land_use_description": "VACANT RESIDENTIAL",
                        "lot_size_sqft": 10105.0,
                        "living_units": 0,
                        "lat": 25.967404,
                        "lng": -80.202576,
                        "zoning_layer_url": "https://example.test/miami-gardens-zoning",
                    },
                }
        elif request.tool_name == "find_comparables":
            payload = {
                "analysis": {
                    "comparables": [],
                    "unit_comparables": [
                        {
                            "address": "105 NE 213 ST",
                            "sale_price": 699000.0,
                            "sale_date": "2026-04-21",
                            "lot_size_sqft": 7500.0,
                            "zoning_code": "",
                            "distance_miles": 0.34,
                            "price_per_acre": 0.0,
                            "price_per_unit": 699000.0,
                            "adjustments": {"qualification_score": 0.92},
                        }
                    ],
                    "estimated_land_value": 0.0,
                    "adv_per_unit": 699000.0,
                    "confidence": 0.55,
                    "web_listing_search": {
                        "query": "miami gardens sold vacant land comps",
                        "provider": "exa",
                        "status": "success",
                        "result_count": 1,
                        "selected_search_window_months": 12,
                    },
                    "web_listing_candidates": [
                        {
                            "title": "17605 NW 19th Avenue, Miami Gardens, FL 33056 | Zillow",
                            "url": "https://www.zillow.com/homedetails/example",
                            "address_hint": "17605 NW 19th Avenue, Miami Gardens, FL 33056",
                            "source_domain": "www.zillow.com",
                            "query": "miami gardens sold vacant land comps",
                            "description": "Public sold listing candidate.",
                            "candidate_kind": "listing_candidate",
                            "classification": "likely_vacant_land",
                            "confidence": 0.85,
                            "search_window_months": 12,
                            "fit_score": 0.92,
                            "lot_size_variance_ratio": 0.08,
                        }
                    ],
                }
            }
        elif request.tool_name == "fetch_web_contents":
            payload = {
                "status": "success",
                "provider": "exa",
                "results": [
                    {
                        "title": "17605 NW 19th Avenue, Miami Gardens, FL 33056 | Zillow",
                        "url": "https://www.zillow.com/homedetails/example",
                        "description": "Sold for $135,000 on 2026-04-21. Lot size: 9,000 sqft.",
                        "content": "Public sold listing. Sold for $135,000 on 2026-04-21. Lot size 9,000 sqft.",
                    }
                ],
            }
        elif request.tool_name == "capture_public_listing_comps":
            payload = {
                "status": "success",
                "provider": "browser_use",
                "strategy": "public_sold_listing_capture",
                "candidates": [],
                "warnings": [],
            }
        else:
            from tests.unit.test_harness_api import _live_tool_payload

            payload = _live_tool_payload(request.tool_name, dict(request.args))

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
            source_mode=request.source_mode,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "45 NW 209 ST, Miami Gardens, FL 33169",
            "analysis_type": "acquisition_memo",
            "source_mode": "live",
            "assumptions": {
                "maxUnits": 1,
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
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["artifacts"]["comp_search_strategy"]["county_reconciled_candidate_count"] == 1
    assert data["artifacts"]["comp_search_strategy"]["public_listing_signal_tier"] == "county_reconciled"
    assert "contextual_land_listing_reconciliation" in data["artifacts"]
    assert data["artifacts"]["acquisition_guidance"]["county_reconciled_land_candidate_count"] == 1
    assert data["artifacts"]["acquisition_guidance"]["land_signal_source"] == "county_reconciled_public_listing"
    assert data["artifacts"]["acquisition_guidance"]["requires_market_signal_validation"] is False
    assert data["artifacts"]["comp_search_strategy"]["land_signal_tier"] == "county_reconciled_public_listing"
    assert data["artifacts"]["comps"]["public_listing_land_comparables"][0]["verification_status"] == "county_reconciled"


@pytest.mark.asyncio
async def test_live_run_enriches_address_only_public_listing_with_county_sale_facts(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    async def _fake_tool_result(request) -> HarnessToolCallResult:
        if request.tool_name == "geocode_address":
            requested_address = str(request.args["address"])
            payload = {
                "status": "success",
                "result": {
                    "address": requested_address,
                    "municipality": "Miami Gardens",
                    "county": "Miami-Dade",
                    "state": "FL",
                    "lat": 25.936991 if "17605 NW 19th" in requested_address else 25.967404,
                    "lng": -80.235842 if "17605 NW 19th" in requested_address else -80.202576,
                },
            }
        elif request.tool_name == "lookup_property_info":
            requested_address = str(request.args["address"])
            if "17605 NW 19th" in requested_address:
                payload = {
                    "status": "success",
                    "result": {
                        "folio": "3412110001000",
                        "address": "17605 NW 19th Avenue",
                        "municipality": "Miami Gardens",
                        "county": "Miami-Dade",
                        "zoning_code": "R-1",
                        "land_use_description": "VACANT RESIDENTIAL",
                        "lot_size_sqft": 9000.0,
                        "living_units": 0,
                        "last_sale_price": 135000.0,
                        "last_sale_date": "2026-04-30",
                        "lat": 25.936991,
                        "lng": -80.235842,
                    },
                }
            else:
                payload = {
                    "status": "success",
                    "result": {
                        "folio": "3411360031910",
                        "address": "45 NW 209 ST",
                        "municipality": "Miami Gardens",
                        "county": "Miami-Dade",
                        "zoning_code": "R-1",
                        "land_use_description": "VACANT RESIDENTIAL",
                        "lot_size_sqft": 10105.0,
                        "living_units": 0,
                        "lat": 25.967404,
                        "lng": -80.202576,
                    },
                }
        elif request.tool_name == "find_comparables":
            payload = {
                "analysis": {
                    "comparables": [],
                    "unit_comparables": [],
                    "estimated_land_value": 0.0,
                    "adv_per_unit": 0.0,
                    "confidence": 0.55,
                    "web_listing_search": {
                        "query": "miami gardens sold vacant land comps",
                        "provider": "exa",
                        "status": "success",
                        "result_count": 1,
                        "selected_search_window_months": 12,
                    },
                    "web_listing_candidates": [
                        {
                            "title": "17605 NW 19th Avenue, Miami Gardens, FL 33056 | Zillow",
                            "url": "https://www.zillow.com/homedetails/example",
                            "address_hint": "17605 NW 19th Avenue, Miami Gardens, FL 33056",
                            "source_domain": "www.zillow.com",
                            "query": "miami gardens sold vacant land comps",
                            "description": "Public sold listing candidate with limited snippet.",
                            "candidate_kind": "listing_candidate",
                            "classification": "likely_vacant_land",
                            "confidence": 0.85,
                            "search_window_months": 12,
                            "fit_score": 0.92,
                            "lot_size_variance_ratio": 0.08,
                        }
                    ],
                }
            }
        elif request.tool_name == "fetch_web_contents":
            payload = {
                "status": "success",
                "provider": "exa",
                "results": [
                    {
                        "title": "17605 NW 19th Avenue, Miami Gardens, FL 33056 | Zillow",
                        "url": "https://www.zillow.com/homedetails/example",
                        "description": "Zillow home details for the public property page.",
                        "content": "Public property page with address only.",
                    }
                ],
            }
        elif request.tool_name == "capture_public_listing_comps":
            payload = {
                "status": "success",
                "provider": "browser_capture_fixture",
                "captured_count": 0,
                "candidates": [],
                "warnings": [],
            }
        else:
            from tests.unit.test_harness_api import _live_tool_payload

            payload = _live_tool_payload(request.tool_name, dict(request.args))

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
            source_mode=request.source_mode,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "45 NW 209 ST, Miami Gardens, FL 33169",
            "analysis_type": "acquisition_memo",
            "source_mode": "live",
            "assumptions": {
                "maxUnits": 1,
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
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    reconciliation = data["artifacts"]["contextual_land_listing_reconciliation"]
    assert reconciliation["status"] == "county_reconciled"
    assert reconciliation["reconciled_candidate_count"] == 1
    assert reconciliation["reconciled_candidates"][0]["county_sale_price"] == 135000.0
    assert reconciliation["reconciled_candidates"][0]["reconciliation_basis"] == "county_record_enriched"
    assert data["artifacts"]["comp_search_strategy"]["land_signal_tier"] == "county_reconciled_public_listing"
    assert data["artifacts"]["acquisition_guidance"]["land_signal_source"] == "county_reconciled_public_listing"
