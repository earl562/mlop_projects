from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol

from plotlot.core.types import CompAnalysis, PropertyRecord
from plotlot.mcp.tool_types import JsonObject


class FindComparables(Protocol):
    async def __call__(self, subject: PropertyRecord, *, state: str) -> CompAnalysis: ...


@dataclass(frozen=True, slots=True)
class ComparableSalesInput:
    lat: float
    lng: float
    state: str = "FL"
    radius_miles: float = 3.0


@dataclass(frozen=True, slots=True)
class ComparableSalesDeps:
    find_comparables: FindComparables


async def run_get_comparable_sales(
    input_data: ComparableSalesInput,
    deps: ComparableSalesDeps,
) -> JsonObject:
    prop = PropertyRecord(county="")
    prop.lat = input_data.lat
    prop.lng = input_data.lng

    try:
        result = await deps.find_comparables(prop, state=input_data.state)
    except RuntimeError as exc:
        return {
            "lat": input_data.lat,
            "lng": input_data.lng,
            "state": input_data.state,
            "error": str(exc),
            "comparables": [],
        }

    comp_data = asdict(result)
    return {
        "lat": input_data.lat,
        "lng": input_data.lng,
        "state": input_data.state,
        "comparable_count": len(result.comparables),
        "median_price_per_acre": comp_data.get("median_price_per_acre"),
        "price_per_acre_low": comp_data.get("price_per_acre_low"),
        "price_per_acre_high": comp_data.get("price_per_acre_high"),
        "estimated_land_value": comp_data.get("estimated_land_value"),
        "estimated_land_value_low": comp_data.get("estimated_land_value_low"),
        "estimated_land_value_high": comp_data.get("estimated_land_value_high"),
        "adv_per_unit": comp_data.get("adv_per_unit"),
        "adv_per_unit_low": comp_data.get("adv_per_unit_low"),
        "adv_per_unit_high": comp_data.get("adv_per_unit_high"),
        "adv_source": comp_data.get("adv_source"),
        "confidence": comp_data.get("confidence"),
        "comparables": comp_data.get("comparables", []),
        "unit_comparables": comp_data.get("unit_comparables", []),
    }
