from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from plotlot.harness.contracts import JsonObject

logger = logging.getLogger(__name__)

WEST_PALM_NWD_STANDARDS_URL = (
    "https://online.encodeplus.com/regs/westpalmbeach-fl/doc-view.aspx?ajax=0&pn=0&secid=269"
)
WEST_PALM_NWD_REQUIREMENTS_URL = (
    "https://online.encodeplus.com/regs/westpalmbeach-fl/doc-view.aspx?ajax=0&pn=0&secid=434"
)
_PARSER_VERSION = "west_palm_encodeplus_nwd_r_c1_v1"
_SCHEMA_VERSION = "official_dimensional_rules_v1"


async def resolve_official_dimensional_rules(
    *,
    municipality: str,
    zoning_code: str,
    lot_area_sqft: float,
    lot_depth_ft: float | None,
    client: httpx.AsyncClient | None = None,
) -> JsonObject | None:
    if not _supports_west_palm_nwd_r(municipality, zoning_code) or lot_area_sqft <= 0:
        return None
    if client is not None:
        return await _fetch_west_palm_nwd_r_rules(
            client=client,
            lot_area_sqft=lot_area_sqft,
            lot_depth_ft=lot_depth_ft,
        )
    timeout = httpx.Timeout(10.0, connect=4.0)
    headers = {"User-Agent": "PlotLot/1.0 official-zoning-retrieval"}
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers=headers,
    ) as owned_client:
        return await _fetch_west_palm_nwd_r_rules(
            client=owned_client,
            lot_area_sqft=lot_area_sqft,
            lot_depth_ft=lot_depth_ft,
        )


async def _fetch_west_palm_nwd_r_rules(
    *,
    client: httpx.AsyncClient,
    lot_area_sqft: float,
    lot_depth_ft: float | None,
) -> JsonObject | None:
    try:
        standards_response, requirements_response = await asyncio.gather(
            client.get(WEST_PALM_NWD_STANDARDS_URL),
            client.get(WEST_PALM_NWD_REQUIREMENTS_URL),
        )
        standards_response.raise_for_status()
        requirements_response.raise_for_status()
        return _parse_west_palm_nwd_r_rules(
            standards_html=standards_response.text,
            requirements_html=requirements_response.text,
            lot_area_sqft=lot_area_sqft,
            lot_depth_ft=lot_depth_ft,
        )
    except (httpx.HTTPError, ValueError):
        logger.warning(
            "West Palm Beach official NWD-R-C1 dimensional retrieval failed",
            exc_info=True,
        )
        return None


def _parse_west_palm_nwd_r_rules(
    *,
    standards_html: str,
    requirements_html: str,
    lot_area_sqft: float,
    lot_depth_ft: float | None,
) -> JsonObject:
    standards_text = _page_text(standards_html)
    requirements_text = _page_text(requirements_html)
    if "sec. 94-84" not in standards_text.casefold() or "nwd-r-c1" not in standards_text.casefold():
        raise ValueError("Section 94-84 NWD-R-C1 marker missing")
    requirements_folded = requirements_text.casefold()
    if "sec. 94-128" not in requirements_folded or "table iv-39" not in requirements_folded:
        raise ValueError("Section 94-128 Table IV-39 marker missing")

    corner_segment = _segment(standards_text, "Corner:", "Rear:")
    height_segment = _segment(
        standards_text,
        "Maximum height of principal structure",
        "Maximum lot coverage",
    )
    coverage_segment = _segment(
        standards_text,
        "Maximum lot coverage",
        "Maximum floor area ratio",
    )
    far_segment = _segment(standards_text, "Maximum floor area ratio", None)
    cumulative_side_segment = _segment(
        standards_text,
        "Side minimum cumulative",
        "Garage location",
    )
    nwd_r_density_segment = _segment(
        requirements_text,
        "Table IV-39: Building Requirements",
        None,
    )

    min_lot_area_sqft = _number(
        standards_text,
        r"Lot area\s*:\s*([\d,]+(?:\.\d+)?)\s+square feet",
    )
    min_lot_width_ft = _number(
        standards_text,
        r"Lot width\s*:\s*([\d,]+(?:\.\d+)?)\s+feet",
    )
    setback_front_ft = _number(
        standards_text,
        r"minimum front setback shall be\s+([\d.]+)\s+feet",
    )
    setback_side_ft = _number(
        standards_text,
        r"Side minimum\s*\(one side only\)\s*:\s*([\d.]+)\s+feet",
    )
    rear_cap_ft = _number(
        standards_text,
        r"Rear\s*:\s*([\d.]+)\s+feet\s*,?\s*or",
    )
    rear_depth_pct = _number(
        standards_text,
        r"or\s+([\d.]+)\s+percent of the lot depth",
    )
    max_density_units_per_acre = _number(
        nwd_r_density_segment,
        r"Density\s+Maximum\s+([\d.]+)\s+DU\s*/?\s*Acre",
    )

    tier_index = 0 if lot_area_sqft <= 4_999 else (1 if lot_area_sqft < 7_500 else 2)
    corner_values = _three_tier_values(corner_segment)
    height_values = _three_tier_values(height_segment)
    coverage_values = _three_tier_values(coverage_segment)
    far_values = _three_tier_values(far_segment)
    cumulative_side_values = _two_tier_values(cumulative_side_segment)

    retrieved_at = datetime.now(timezone.utc).isoformat()
    rules: JsonObject = {
        "zoning_district": "NWD-R-C1",
        "min_lot_area_sqft": min_lot_area_sqft,
        "min_lot_width_ft": min_lot_width_ft,
        "setback_front_ft": setback_front_ft,
        "setback_corner_ft": corner_values[tier_index],
        "setback_side_ft": setback_side_ft,
        "setback_side_cumulative_ft": (
            cumulative_side_values[0] if lot_area_sqft < 7_500 else cumulative_side_values[1]
        ),
        "max_height_ft": height_values[tier_index],
        "max_lot_coverage_pct": coverage_values[tier_index],
        "far": far_values[tier_index],
        "max_density_units_per_acre": max_density_units_per_acre,
        "front_setback_condition": (
            "Contextual front setback under Sec. 94-79(b); 15 feet only when "
            "a contextual front setback has not been established."
        ),
        "rear_setback_formula": (
            f"Lesser of {rear_cap_ft:g} feet or {rear_depth_pct:g}% of lot depth."
        ),
        "source": "west_palm_beach_encodeplus_live",
        "source_section_id": "Sec. 94-84; Sec. 94-128 Table IV-39",
        "source_url": WEST_PALM_NWD_STANDARDS_URL,
        "secondary_source_url": WEST_PALM_NWD_REQUIREMENTS_URL,
        "retrieved_at": retrieved_at,
        "parser_version": _PARSER_VERSION,
        "schema_version": _SCHEMA_VERSION,
        "requires_official_verification": False,
        "authority_source_type": "official_encodeplus_live",
        "authority_resolution": "official_live_section_extract",
        "authority_confidence": "official_live_exact_district",
        "authority_is_live": True,
        "authority_is_official": True,
        "authority_jurisdiction": "West Palm Beach",
    }
    if lot_depth_ft is not None and lot_depth_ft > 0:
        rules["setback_rear_ft"] = min(rear_cap_ft, lot_depth_ft * rear_depth_pct / 100.0)

    warning = (
        "The front setback remains contextual under Sec. 94-79(b); verify the established "
        "block-face setback before final site planning."
    )
    return {
        "status": "success",
        "fallback_source": "west_palm_beach_encodeplus_live",
        "requires_official_verification": False,
        "authority_source_type": "official_encodeplus_live",
        "authority_resolution": "official_live_section_extract",
        "authority_confidence": "official_live_exact_district",
        "authority_is_live": True,
        "authority_is_official": True,
        "authority_jurisdiction": "West Palm Beach",
        "retrieved_at": retrieved_at,
        "parser_version": _PARSER_VERSION,
        "schema_version": _SCHEMA_VERSION,
        "warnings": [warning],
        "rules": rules,
        "results": [
            {
                "section": "Sec. 94-84",
                "section_id": "Sec. 94-84",
                "title": "NWD-R-C1 property development regulations",
                "text": standards_text[:2_000],
                "zone_codes": ["NWD-R-C1", "NWD-R", "NWD-R (city)"],
                "citation": {
                    "url": WEST_PALM_NWD_STANDARDS_URL,
                    "jurisdiction": "West Palm Beach",
                },
            },
            {
                "section": "Sec. 94-128 Table IV-39",
                "section_id": "Sec. 94-128 Table IV-39",
                "title": "NWD-R-C1 density",
                "text": requirements_text[:2_000],
                "zone_codes": ["NWD-R-C1", "NWD-R", "NWD-R (city)"],
                "citation": {
                    "url": WEST_PALM_NWD_REQUIREMENTS_URL,
                    "jurisdiction": "West Palm Beach",
                },
            },
        ],
    }


def _supports_west_palm_nwd_r(municipality: str, zoning_code: str) -> bool:
    normalized_municipality = re.sub(r"[^a-z0-9]", "", municipality.casefold())
    normalized_zoning = re.sub(r"[^a-z0-9]", "", zoning_code.casefold())
    return normalized_municipality == "westpalmbeach" and normalized_zoning.startswith("nwdr")


def _page_text(html: str) -> str:
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    normalized = " ".join(text.split())
    if not normalized:
        raise ValueError("Official ordinance page was empty")
    return normalized


def _segment(text: str, start: str, end: str | None) -> str:
    folded = text.casefold()
    start_index = folded.find(start.casefold())
    if start_index < 0:
        raise ValueError(f"Required ordinance heading missing: {start}")
    if end is None:
        return text[start_index:]
    end_index = folded.find(end.casefold(), start_index + len(start))
    if end_index < 0:
        raise ValueError(f"Required ordinance heading missing: {end}")
    return text[start_index:end_index]


def _number(text: str, pattern: str) -> float:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
    if match is None:
        raise ValueError(f"Required ordinance value missing: {pattern}")
    return float(match.group(1).replace(",", ""))


def _three_tier_values(segment: str) -> tuple[float, float, float]:
    return (
        _number(segment, r"up to 4,999 square feet\s*:\s*(\d+(?:\.\d+)?)"),
        _number(segment, r"5,000 to 7,499 square feet\s*:\s*(\d+(?:\.\d+)?)"),
        _number(segment, r"7,500 square feet and over\s*:\s*(\d+(?:\.\d+)?)"),
    )


def _two_tier_values(segment: str) -> tuple[float, float]:
    return (
        _number(segment, r"up to 7,499 square feet\s*:\s*(\d+(?:\.\d+)?)"),
        _number(segment, r"7,500 square feet and over\s*:\s*(\d+(?:\.\d+)?)"),
    )
