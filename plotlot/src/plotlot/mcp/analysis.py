from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from plotlot.core.types import ZoningReport
from plotlot.mcp.tool_types import JsonObject, JsonValue

type LookupAddress = Callable[[str], Awaitable[ZoningReport | None]]
type ReportAsDict = Callable[[ZoningReport], JsonObject]


@dataclass(frozen=True, slots=True)
class RunFullAnalysisDeps:
    lookup_address: LookupAddress
    asdict_fn: ReportAsDict


def _object_value(value: JsonValue) -> JsonObject:
    return value if isinstance(value, dict) else {}


async def run_full_analysis_tool(address: str, deps: RunFullAnalysisDeps) -> JsonObject:
    try:
        report = await deps.lookup_address(address)
    except RuntimeError as exc:
        return {"error": str(exc), "address": address}

    if report is None:
        return {
            "error": f"Could not geocode or analyse address: {address}",
            "address": address,
        }

    raw = deps.asdict_fn(report)
    numeric_params = _object_value(raw.get("numeric_params"))
    density_analysis = _object_value(raw.get("density_analysis"))
    pro_forma = _object_value(raw.get("pro_forma"))

    numeric_fields = (
        "max_density_units_per_acre",
        "min_lot_area_per_unit_sqft",
        "far",
        "max_lot_coverage_pct",
        "max_height_ft",
        "setback_front_ft",
        "setback_side_ft",
        "setback_rear_ft",
    )
    standards_found = any(numeric_params.get(field) is not None for field in numeric_fields)
    zoning_found = bool(raw.get("zoning_district"))
    ordinance_indexed = bool(raw.get("sources"))
    max_units = density_analysis.get("max_units")

    if standards_found:
        coverage = "full"
    elif zoning_found:
        coverage = "zoning_only"
    else:
        coverage = "none"

    if coverage == "full":
        guidance = (
            "Full data available. Present the zoning district, dimensional standards, "
            "and max-units analysis as computed. Cite the retrieved ordinance sections."
        )
    elif coverage == "zoning_only":
        guidance = (
            f"The zoning district ({raw.get('zoning_district')}) and property data below were "
            "retrieved from the county's official GIS and ARE accurate - state them plainly. "
            "Do NOT say the zoning 'could not be retrieved'. The dimensional standards "
            "(setbacks, density, height, FAR) for this district are NOT yet in the PlotLot "
            "database, so max units cannot be computed. Say so honestly and offer to ingest the "
            "ordinance with the ingest_municipality tool. NEVER fabricate phone numbers, office "
            "names, URLs, or numeric zoning values that are not present in this response."
        )
    else:
        guidance = (
            "No zoning district was resolved for this address. State that the official zoning "
            "lookup returned no record and suggest verifying the address. Do NOT invent a zoning "
            "code, phone number, URL, or any dimensional values."
        )

    return {
        "address": address,
        "municipality": raw.get("municipality"),
        "county": raw.get("county"),
        "zoning_district": raw.get("zoning_district"),
        "zoning_description": raw.get("zoning_description"),
        "confidence": raw.get("confidence"),
        "max_density_units_per_acre": numeric_params.get("max_density_units_per_acre"),
        "max_height_ft": numeric_params.get("max_height_ft"),
        "max_far": numeric_params.get("far"),
        "setback_front_ft": numeric_params.get("setback_front_ft"),
        "setback_side_ft": numeric_params.get("setback_side_ft"),
        "setback_rear_ft": numeric_params.get("setback_rear_ft"),
        "min_lot_area_sqft": numeric_params.get("min_lot_area_per_unit_sqft"),
        "max_units": max_units,
        "governing_constraint": density_analysis.get("governing_constraint"),
        "max_land_price": pro_forma.get("max_land_price"),
        "cost_per_door": pro_forma.get("cost_per_door"),
        "data_status": {
            "coverage": coverage,
            "zoning_district_found": zoning_found,
            "dimensional_standards_found": standards_found,
            "ordinance_text_indexed": ordinance_indexed,
            "max_units_computed": bool(max_units),
        },
        "presentation_guidance": guidance,
        "full_report": raw,
    }
