from __future__ import annotations

import json

import pytest
from pytest import MonkeyPatch

from plotlot.cli_harness import main
from plotlot.domain.types import PolicyDecision
from plotlot.harness.contracts import RunId, SourceMode, ToolCallId
from plotlot.harness.tool_router import HarnessToolCallResult, ToolRouteStatus


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


def _result(tool_name: str, run_id: str, args: dict[str, object], payload: dict[str, object]) -> HarnessToolCallResult:
    return HarnessToolCallResult(
        ok=True,
        tool_call_id=ToolCallId(f"tool_call_{tool_name}"),
        tool_name=tool_name,
        run_id=RunId(run_id),
        args=args,
        status=ToolRouteStatus.COMPLETED,
        policy_decision=PolicyDecision(allowed=True, reason="test"),
        payload=payload,
        events=[],
        source_mode=SourceMode.LIVE,
    )


@pytest.mark.parametrize(
    ("address", "municipality", "county", "zoning_code", "lot_size_sqft", "lot_dimensions", "use_parcel_geometry", "last_sale_price", "frontage_ft", "expected_offer", "expected_land_value", "include_frontage"),
    [
        (
            "45 NW 209 ST, Miami Gardens, FL 33169",
            "Miami Gardens",
            "Miami-Dade",
            "R-1",
            10105.0,
            "75 x 134.73",
            False,
            80000.0,
            75.0,
            120000.0,
            149048.75,
            False,
        ),
        (
            "1234 NW 15th St, Fort Lauderdale, FL 33311",
            "Fort Lauderdale",
            "Broward",
            "RS-8",
            6000.0,
            "",
            True,
            150000.0,
            50.0,
            180000.0,
            240000.0,
            False,
        ),
    ],
)
def test_cli_run_acquisition_memo_accepts_json_assumptions_for_manual_comp_gold_paths(
    capsys,
    monkeypatch: MonkeyPatch,
    address: str,
    municipality: str,
    county: str,
    zoning_code: str,
    lot_size_sqft: float,
    lot_dimensions: str,
    use_parcel_geometry: bool,
    last_sale_price: float,
    frontage_ft: float,
    expected_offer: float,
    expected_land_value: float,
    include_frontage: bool,
) -> None:
    async def _fake_tool_result(request) -> HarnessToolCallResult:  # noqa: ANN001
        match request.tool_name:
            case "geocode_address":
                payload = {
                    "status": "success",
                    "result": {
                        "address": str(request.args["address"]),
                        "municipality": municipality,
                        "county": county,
                        "state": "FL",
                        "lat": 25.0,
                        "lng": -80.0,
                    },
                }
            case "lookup_property_info":
                parcel_geometry = (
                    [
                        [-80.1592, 26.1404],
                        [-80.159051, 26.1404],
                        [-80.159051, 26.1407297],
                        [-80.1592, 26.1407297],
                        [-80.1592, 26.1404],
                    ]
                    if use_parcel_geometry
                    else None
                )
                payload = {
                    "status": "success",
                    "result": {
                        "folio": "fixture-folio",
                        "address": address,
                        "municipality": municipality,
                        "county": county,
                        "zoning_code": zoning_code,
                        "ordinance_district_code": zoning_code,
                        "zoning_description": "Residential district",
                        "land_use_code": "0066",
                        "land_use_description": "VACANT RESIDENTIAL",
                        "lot_size_sqft": lot_size_sqft,
                        "lot_dimensions": lot_dimensions,
                        "living_units": 0,
                        "last_sale_price": last_sale_price,
                        "parcel_geometry": parcel_geometry,
                        "zoning_layer_url": "https://example.test/zoning",
                    },
                }
            case "compute_feasibility":
                payload = {
                    "result": {
                        "calculation_type": "feasibility",
                        "formula_version": "feasibility.v2",
                        "max_gross_buildable_sf": 3000.0,
                        "net_rentable_sf": 2550.0,
                        "estimated_units": 1,
                        "parking_required": 2,
                        "major_constraints": ["lot_coverage"],
                        "area_limiters": ["lot_coverage"],
                        "lot_depth_ft": lot_size_sqft / frontage_ft,
                        "buildable_envelope_sf": None,
                        "lot_coverage_limited_sf": 3000.0,
                        "feasibility_warnings": [],
                    }
                }
            case "run_pro_forma":
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
                        "max_supportable_land_price": expected_offer,
                        "cost_per_door": 372000.0,
                        "construction_cost_psf": 167.65,
                        "avg_unit_size_sqft": 1700.0,
                        "adv_per_unit": 650000.0 if county == "Broward" else 500000.0,
                        "max_units": 1,
                        "soft_cost_pct": 0.2,
                        "builder_margin_pct": 0.05,
                        "adv_source": "manual_comps",
                        "market": county,
                        "notes": [],
                    }
                }
            case "run_residual_land_value":
                payload = {
                    "calculation_type": "residual_land_value",
                    "formula_version": "residual_land_value.v1",
                    "total_project_costs_excluding_land": 270000.0,
                    "max_supportable_land_price": expected_offer,
                    "spread_to_asking_price": expected_offer,
                    "go_no_go_signal": "go",
                    "warnings": [],
                }
            case _:
                payload = {"status": "success", "results": []}
        return _result(request.tool_name, str(request.run_id), dict(request.args), payload)

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    assumptions = {
        "avgUnitSizeSf": 1700,
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
                "address": "land comp 1",
                "salePrice": expected_land_value,
                "saleDate": "2026-02-01",
                "lotSizeSqft": lot_size_sqft,
                "sourceUrl": "https://example.test/land-1",
            },
            {
                "address": "land comp 2",
                "salePrice": expected_land_value,
                "saleDate": "2026-01-15",
                "lotSizeSqft": lot_size_sqft,
                "sourceUrl": "https://example.test/land-2",
            },
        ],
        "manualExitComps": [
            {
                "address": "exit comp 1",
                "salePrice": 650000 if county == "Broward" else 500000,
                "saleDate": "2026-03-01",
                "units": 1,
                "sourceUrl": "https://example.test/exit-1",
            },
            {
                "address": "exit comp 2",
                "salePrice": 650000 if county == "Broward" else 500000,
                "saleDate": "2026-02-14",
                "units": 1,
                "sourceUrl": "https://example.test/exit-2",
            },
        ],
    }
    if include_frontage:
        assumptions["lotFrontageFt"] = frontage_ft

    exit_code = main(
        [
            "run",
            "acquisition-memo",
            "--address",
            address,
            "--source-mode",
            "live",
            "--assumptions-json",
            json.dumps(assumptions),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "completed"
    assert payload["source_mode"] == "live"
    assert payload["artifacts"]["acquisition_guidance"]["pricing_source"] == "manual_comps"
    assert payload["artifacts"]["acquisition_guidance"]["recommended_offer"] == pytest.approx(expected_offer)
    assert payload["artifacts"]["acquisition_guidance"]["land_value_signal"] == pytest.approx(expected_land_value)
    assert payload["artifacts"]["manual_comparables"]["land_comp_count"] == 2
    assert payload["artifacts"]["manual_comparables"]["unit_comp_quality"] == {
        "unit_comp_count": 2,
        "scored_unit_comp_count": 0,
        "strong_unit_comp_count": 0,
        "very_strong_unit_comp_count": 0,
        "unit_comp_scores": [],
        "best_exit_fit_score": 1.0,
        "best_exit_price_variance_ratio": 0.0,
        "best_exit_qualification_score": 0.0,
        "qualified_exit_comp_signal": True,
        "manual_override_used": True,
    }
    if not include_frontage:
        if use_parcel_geometry:
            assert any(
                "estimated lot frontage from parcel geometry" in warning
                for warning in payload["artifacts"].get("warnings", [])
            )
        else:
            assert not any(
                "minimum lot width as a conservative frontage proxy" in warning
                for warning in payload["artifacts"].get("warnings", [])
            )


def test_cli_run_live_auto_comp_path_surfaces_exit_comp_supportability(capsys, monkeypatch: MonkeyPatch) -> None:
    observed_searches: list[tuple[int, float]] = []

    async def _fake_tool_result(request) -> HarnessToolCallResult:  # noqa: ANN001
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
                        "zoning_description": "Single-family dwelling residential district",
                        "land_use_code": "0066",
                        "land_use_description": "VACANT RESIDENTIAL",
                        "lot_size_sqft": 10105.0,
                        "living_units": 0,
                        "zoning_layer_url": "https://example.test/miami-gardens-zoning",
                    },
                }
            case "find_comparables":
                months = int(request.args["months"])
                radius_miles = float(request.args["radius_miles"])
                observed_searches.append((months, radius_miles))
                if months in {6, 12} or (months == 24 and radius_miles == 3.0):
                    payload = {
                        "analysis": {
                            "comparables": [],
                            "unit_comparables": [],
                            "estimated_land_value": 0.0,
                            "adv_per_unit": 0.0,
                            "confidence": 0.0,
                            "notes": [],
                        }
                    }
                else:
                    payload = {
                        "analysis": {
                            "comparables": [
                                {
                                    "address": "17605 NW 19th Avenue",
                                    "sale_price": 145000.0,
                                    "sale_date": "2026-02-01",
                                    "lot_size_sqft": 9500.0,
                                    "zoning_code": "R-1",
                                    "distance_miles": 4.12,
                                    "price_per_acre": 665789.47,
                                    "adjustments": {},
                                }
                            ],
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
                                },
                                {
                                    "address": "220 NE 211 ST",
                                    "sale_price": 505000.0,
                                    "sale_date": "2026-05-05",
                                    "lot_size_sqft": 3007.0,
                                    "zoning_code": "",
                                    "distance_miles": 0.38,
                                    "price_per_acre": 0.0,
                                    "price_per_unit": 505000.0,
                                    "adjustments": {"qualification_score": 0.88},
                                },
                            ],
                            "estimated_land_value": 154391.78,
                            "price_per_acre_low": 665789.47,
                            "price_per_acre_high": 665789.47,
                            "estimated_land_value_low": 154391.78,
                            "estimated_land_value_high": 154391.78,
                            "adv_per_unit": 505000.0,
                            "adv_per_unit_low": 485000.0,
                            "adv_per_unit_high": 602000.0,
                            "adv_source": "comps",
                            "confidence": 0.55,
                            "notes": [
                                "No reliable vacant-land comps within 24 months; using nearby improved single-family sales for exit pricing only."
                            ],
                        }
                    }
            case "run_residual_land_value":
                payload = {
                    "calculation_type": "residual_land_value",
                    "formula_version": "residual_land_value.v1",
                    "total_project_costs_excluding_land": 425000.0,
                    "max_supportable_land_price": -95000.0,
                    "spread_to_asking_price": -95000.0,
                    "go_no_go_signal": "no_go",
                    "warnings": ["Negative residual land value: costs and profit exceed as-built value."],
                }
            case _:
                payload = {"status": "success", "result": dict(request.args), "results": []}
        return _result(request.tool_name, str(request.run_id), dict(request.args), payload)

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    exit_code = main(
        [
            "run",
            "acquisition-memo",
            "--address",
            "45 NW 209 ST, Miami Gardens, FL 33169",
            "--source-mode",
            "live",
            "--assumptions-json",
            json.dumps(
                {
                    "maxUnits": 1,
                    "maxFar": 0.8,
                    "avgUnitSizeSf": 1800,
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
                }
            ),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert observed_searches == [(6, 3.0), (12, 3.0), (24, 3.0), (24, 6.0)]
    assert payload["artifacts"]["comp_search_strategy"]["selected_reason"] == "qualified_exit_comp_fallback"
    assert payload["artifacts"]["comp_search_strategy"]["attempts"][-1]["qualified_exit_comp_signal"] is True
    assert payload["artifacts"]["comp_search_strategy"]["attempts"][-1]["strong_unit_comp_count"] == 2
    assert payload["artifacts"]["acquisition_guidance"]["recommended_action"] == "insufficient_support"
    assert payload["artifacts"]["acquisition_guidance"]["exit_comp_signal_available"] is True


def test_cli_run_rejects_non_object_assumptions_json(capsys) -> None:
    exit_code = main(
        [
            "run",
            "acquisition-memo",
            "--address",
            "45 NW 209 ST, Miami Gardens, FL 33169",
            "--assumptions-json",
            "[]",
        ]
    )

    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "invalid_input"
