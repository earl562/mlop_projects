from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from plotlot.domain.types import PolicyDecision
from plotlot.harness.contracts import JsonObject, RunId, SourceMode, ToolCallId
from plotlot.harness.tool_router import HarnessToolCallResult, ToolRouteStatus


@dataclass(frozen=True, slots=True)
class FiveAddressCase:
    address: str
    short_address: str
    municipality: str
    county: str
    zoning_code: str
    lot_size_sqft: float
    lot_dimensions: str
    last_sale_price: float
    expected_offer: float
    expected_guidance_offer: float
    expected_land_value: float
    expected_guidance_land_value: float
    adv_per_unit: float
    frontage_ft: float
    depth_ft: float
    expected_action: str
    expected_basis: str
    expected_land_signal_strength: str
    expected_land_comp_signal_available: bool
    expected_land_signal_tier: str
    expected_verification_status: str
    expected_comp_support_status: str
    expected_comp_support_tier: str
    expected_land_support_source: str


FIVE_ADDRESS_CASES: Final[tuple[FiveAddressCase, ...]] = (
    FiveAddressCase(
        "45 NW 209 ST, Miami Gardens, FL 33169",
        "45 NW 209 ST",
        "Miami Gardens",
        "Miami-Dade",
        "R-1",
        10105.0,
        "75 x 134.73",
        80000.0,
        120000.0,
        0.0,
        149048.75,
        250401.9,
        500000.0,
        75.0,
        134.73,
        "insufficient_support",
        "supported_relaxed_land_signal_requires_validation",
        "supported_relaxed",
        False,
        "supported_relaxed_land_comps",
        "passed_with_warnings",
        "warning",
        "exit_only",
        "none",
    ),
    FiveAddressCase(
        "171 NE 209th Ter, Miami Gardens, FL 33179",
        "171 NE 209th Ter",
        "Miami Gardens",
        "Miami-Dade",
        "R-1",
        9000.0,
        "75 x 120",
        95000.0,
        105000.0,
        105000.0,
        132000.0,
        132000.0,
        510000.0,
        75.0,
        120.0,
        "offer_range",
        "residual_and_market_signal",
        "direct",
        True,
        "direct_land_comps",
        "passed_with_warnings",
        "passed",
        "balanced",
        "direct_land_comps",
    ),
    FiveAddressCase(
        "310 NW 205th Ter, Miami Gardens, FL 33169",
        "310 NW 205th Ter",
        "Miami Gardens",
        "Miami-Dade",
        "R-1",
        9600.0,
        "70 x 137.14",
        90000.0,
        115000.0,
        115000.0,
        141500.0,
        141500.0,
        525000.0,
        75.0,
        137.14,
        "offer_range",
        "residual_and_market_signal",
        "direct",
        True,
        "direct_land_comps",
        "passed_with_warnings",
        "passed",
        "balanced",
        "direct_land_comps",
    ),
    FiveAddressCase(
        "1234 NW 15th St, Fort Lauderdale, FL 33311",
        "1234 NW 15th St",
        "Fort Lauderdale",
        "Broward",
        "RS-8",
        6000.0,
        "50 x 120",
        150000.0,
        180000.0,
        180000.0,
        240000.0,
        240000.0,
        650000.0,
        50.0,
        120.0,
        "offer_range",
        "residual_and_market_signal",
        "direct",
        True,
        "direct_land_comps",
        "passed_with_warnings",
        "passed",
        "balanced",
        "direct_land_comps",
    ),
    FiveAddressCase(
        "1325 NW 15th Way, Fort Lauderdale, FL 33311",
        "1325 NW 15th Way",
        "Fort Lauderdale",
        "Broward",
        "RS-8",
        5500.0,
        "50 x 110",
        142000.0,
        165000.0,
        165000.0,
        228000.0,
        228000.0,
        625000.0,
        50.0,
        110.0,
        "offer_range",
        "residual_and_market_signal",
        "direct",
        True,
        "direct_land_comps",
        "passed_with_warnings",
        "passed",
        "balanced",
        "direct_land_comps",
    ),
)


def build_assumptions(case: FiveAddressCase) -> JsonObject:
    is_broward = case.county == "Broward"
    return {
        "maxUnits": 1,
        "maxDensityUnitsPerAcre": 8 if is_broward else 6,
        "minLotAreaSf": 5000 if is_broward else 7500,
        "minLotFrontageFt": case.frontage_ft,
        "lotFrontageFt": case.frontage_ft,
        "frontSetbackFt": 25,
        "sideSetbackFt": 5 if is_broward else 7.5,
        "rearSetbackFt": 15 if is_broward else 25,
        "maxLotCoveragePct": 50 if is_broward else 40,
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


def build_result(
    case: FiveAddressCase, tool_name: str, run_id: RunId, args: JsonObject
) -> HarnessToolCallResult:
    return HarnessToolCallResult(
        ok=True,
        tool_call_id=ToolCallId(f"tool_call_{tool_name}"),
        tool_name=tool_name,
        run_id=run_id,
        args=args,
        status=ToolRouteStatus.COMPLETED,
        policy_decision=PolicyDecision(allowed=True, reason="test"),
        payload=_build_tool_payload(case, tool_name),
        events=[],
        source_mode=SourceMode.LIVE,
    )


def _build_tool_payload(case: FiveAddressCase, tool_name: str) -> JsonObject:
    match tool_name:
        case "geocode_address":
            return {
                "status": "success",
                "result": {
                    "address": case.address,
                    "municipality": case.municipality,
                    "county": case.county,
                    "state": "FL",
                    "lat": 26.14 if case.county == "Broward" else 25.96,
                    "lng": -80.16 if case.county == "Broward" else -80.20,
                },
            }
        case "lookup_property_info":
            return {
                "status": "success",
                "result": {
                    "folio": f"fixture-{case.short_address}",
                    "address": case.short_address,
                    "municipality": case.municipality,
                    "county": case.county,
                    "zoning_code": case.zoning_code,
                    "ordinance_district_code": case.zoning_code,
                    "zoning_description": "Residential district",
                    "land_use_code": "0066",
                    "land_use_description": "VACANT RESIDENTIAL",
                    "lot_size_sqft": case.lot_size_sqft,
                    "lot_dimensions": case.lot_dimensions,
                    "living_units": 0,
                    "last_sale_price": case.last_sale_price,
                    "zoning_layer_url": "https://example.test/zoning",
                },
            }
        case "find_comparables":
            return _build_comps_payload(case)
        case "compute_feasibility":
            return {
                "result": {
                    "calculation_type": "feasibility",
                    "formula_version": "feasibility.v2",
                    "max_gross_buildable_sf": round(case.lot_size_sqft * 0.4, 2),
                    "net_rentable_sf": round(case.lot_size_sqft * 0.34, 2),
                    "estimated_units": 1,
                    "parking_required": 2,
                    "major_constraints": ["max_units"],
                    "area_limiters": ["lot_coverage", "setback_envelope"],
                    "lot_depth_ft": case.depth_ft,
                    "buildable_envelope_sf": round(case.lot_size_sqft * 0.44, 2),
                    "lot_coverage_limited_sf": round(case.lot_size_sqft * 0.4, 2),
                    "feasibility_warnings": [],
                }
            }
        case "run_pro_forma":
            return {
                "result": {
                    "calculation_type": "pro_forma",
                    "formula_version": "pro_forma.v1",
                    "gross_development_value": case.adv_per_unit,
                    "hard_costs": 285000.0,
                    "soft_costs": 57000.0,
                    "builder_margin": 30000.0,
                    "impact_fees": 0.0,
                    "impact_fees_per_unit": 0.0,
                    "max_supportable_land_price": case.expected_offer,
                    "cost_per_door": 372000.0,
                    "construction_cost_psf": 167.65,
                    "avg_unit_size_sqft": 1700.0,
                    "adv_per_unit": case.adv_per_unit,
                    "max_units": 1,
                    "soft_cost_pct": 0.2,
                    "builder_margin_pct": 0.05,
                    "adv_source": "curated_arcgis",
                    "market": case.county,
                    "notes": [],
                }
            }
        case "run_residual_land_value":
            return {
                "calculation_type": "residual_land_value",
                "formula_version": "residual_land_value.v1",
                "total_project_costs_excluding_land": 270000.0,
                "max_supportable_land_price": case.expected_offer,
                "spread_to_asking_price": case.expected_offer,
                "go_no_go_signal": "go",
                "warnings": [],
            }
        case "load_underwriting_market_profile":
            return {
                "profile": {
                    "market": case.county,
                    "state": "FL",
                    "county": case.county,
                    "municipality": case.municipality,
                    "construction_cost_psf": 225.0,
                    "avg_unit_size_sqft": 1700.0,
                    "soft_cost_pct": 20.0,
                    "builder_margin_pct": 5.0,
                    "impact_fees_per_unit": 0.0,
                    "adv_per_unit": case.adv_per_unit,
                    "monthly_rent_per_unit": 3200.0,
                    "vacancy_pct": 0.05,
                    "operating_expense_pct": 0.35,
                    "cap_rate": 0.06,
                    "requires_official_verification": False,
                    "requires_income_assumption_verification": False,
                    "income_inferred_fields": [],
                    "income_assumption_source": "test_fixture",
                    "overridden_fields": [],
                    "assumptions_snapshot": {},
                },
                "rental_market_evidence": {},
            }
        case "run_noi_valuation":
            return {
                "calculation_type": "noi_valuation",
                "formula_version": "noi_valuation.v1",
                "gross_scheduled_income": 38400.0,
                "effective_gross_income": 36480.0,
                "operating_expenses": 12768.0,
                "annual_noi": 23712.0,
                "as_built_value": case.adv_per_unit,
                "warnings": [],
            }
        case _:
            return {"status": "success", "results": []}


def _build_comps_payload(case: FiveAddressCase) -> JsonObject:
    land_value = case.expected_land_value
    lot_size_sqft = case.lot_size_sqft
    price_per_acre = round(land_value / (lot_size_sqft / 43560.0), 2)
    if case.expected_land_signal_tier == "supported_relaxed_land_comps":
        comparables = [
            {
                "address": "3421100011870",
                "sale_price": round(land_value * 1.68, 2),
                "sale_date": "2026-03-24",
                "lot_size_sqft": 7664.0,
                "zoning_code": "",
                "distance_miles": 2.87,
                "price_per_acre": round(price_per_acre * 1.68, 2),
                "source_url": "https://example.test/arcgis-land-folio-a",
                "provider": "county_recorded_sales",
                "adjustments": {"qualification_score": 0.62, "identifier_only_address": 1.0},
            },
            {
                "address": "3421100011880",
                "sale_price": round(land_value * 1.68, 2),
                "sale_date": "2026-03-24",
                "lot_size_sqft": 7664.0,
                "zoning_code": "",
                "distance_miles": 2.88,
                "price_per_acre": round(price_per_acre * 1.68, 2),
                "source_url": "https://example.test/arcgis-land-folio-b",
                "provider": "county_recorded_sales",
                "adjustments": {"qualification_score": 0.62, "identifier_only_address": 1.0},
            },
            {
                "address": "2205 NW 177 TER",
                "sale_price": round(land_value, 2),
                "sale_date": "2025-08-04",
                "lot_size_sqft": 8646.0,
                "zoning_code": "",
                "distance_miles": 3.04,
                "price_per_acre": price_per_acre,
                "source_url": "https://example.test/arcgis-land-street",
                "provider": "county_recorded_sales",
                "adjustments": {"qualification_score": 0.647},
            },
        ]
        confidence = 0.45
        used_relaxed = True
        notes: list[str] = [
            "Using lower-confidence fallback land comps outside the exact zoning or lot-size filters."
        ]
    else:
        comparables = [
            {
                "address": f"{case.short_address} Land Comp A",
                "sale_price": round(land_value * 0.93, 2),
                "sale_date": "2026-02-15",
                "lot_size_sqft": lot_size_sqft * 0.96,
                "zoning_code": case.zoning_code,
                "distance_miles": 0.42,
                "price_per_acre": price_per_acre * 0.96,
                "source_url": "https://example.test/arcgis-land-a",
                "provider": "county_recorded_sales",
                "adjustments": {"qualification_score": 0.91},
            },
            {
                "address": f"{case.short_address} Land Comp B",
                "sale_price": round(land_value * 1.04, 2),
                "sale_date": "2026-01-10",
                "lot_size_sqft": lot_size_sqft * 1.03,
                "zoning_code": case.zoning_code,
                "distance_miles": 0.68,
                "price_per_acre": price_per_acre * 1.02,
                "source_url": "https://example.test/arcgis-land-b",
                "provider": "county_recorded_sales",
                "adjustments": {"qualification_score": 0.88},
            },
        ]
        confidence = 0.78
        used_relaxed = False
        notes = []
    unit_comparables = [
        {
            "address": f"{case.short_address} Exit Comp A",
            "sale_price": case.adv_per_unit,
            "sale_date": "2026-03-18",
            "lot_size_sqft": lot_size_sqft,
            "zoning_code": case.zoning_code,
            "distance_miles": 0.71,
            "price_per_acre": 0.0,
            "price_per_unit": case.adv_per_unit,
            "source_url": "https://example.test/arcgis-exit-a",
            "provider": "county_recorded_sales",
            "adjustments": {"qualification_score": 0.9},
        },
        {
            "address": f"{case.short_address} Exit Comp B",
            "sale_price": round(case.adv_per_unit * 0.97, 2),
            "sale_date": "2026-02-06",
            "lot_size_sqft": lot_size_sqft * 1.02,
            "zoning_code": case.zoning_code,
            "distance_miles": 0.95,
            "price_per_acre": 0.0,
            "price_per_unit": round(case.adv_per_unit * 0.97, 2),
            "source_url": "https://example.test/arcgis-exit-b",
            "provider": "county_recorded_sales",
            "adjustments": {"qualification_score": 0.86},
        },
    ]
    return {
        "analysis": {
            "comparables": comparables,
            "unit_comparables": unit_comparables,
            "estimated_land_value": land_value,
            "estimated_land_value_low": round(land_value * 0.96, 2),
            "estimated_land_value_high": round(land_value * 1.02, 2),
            "adv_per_unit": case.adv_per_unit,
            "adv_per_unit_low": round(case.adv_per_unit * 0.97, 2),
            "adv_per_unit_high": case.adv_per_unit,
            "confidence": confidence,
            "sales_source_type": "curated_arcgis",
            "exit_comp_source_type": "curated_arcgis",
            "used_relaxed_land_comps": used_relaxed,
            "used_relaxed_unit_comps": False,
            "notes": notes,
        }
    }
