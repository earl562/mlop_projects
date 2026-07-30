from __future__ import annotations

import re
from typing import Final

import httpx
from bs4 import BeautifulSoup

from plotlot.ingestion.discovery import get_municode_configs, resolve_municode_config
from plotlot.ingestion.scraper import MunicodeScraper
from plotlot.observability.tracing import start_otel_span
from plotlot.core.types import MunicodeConfig

_MIAMI_GARDENS_R1_TABLE_NODE_ID: Final[str] = "SPBLADECO_CH34ZOLADE_ARTXIDESTGETADEST_S34-342TADEST"
_MIAMI_GARDENS_R1_SECTION_URL: Final[str] = (
    "https://api.municode.com/codescontent"
    "?nodeId=SPBLADECO_CH34ZOLADE_ARTXIDESTGETADEST_S34-342TADEST"
)
_NUMBER_RE: Final[re.Pattern[str]] = re.compile(r"(\d+(?:,\d{3})*(?:\.\d+)?)")


def _normalize_text(value: str) -> str:
    return " ".join(value.split()).strip()


def _parse_number(value: str) -> float | None:
    match = _NUMBER_RE.search(value)
    if match is None:
        return None
    return float(match.group(1).replace(",", ""))


def _parse_density(value: str) -> float | None:
    return _parse_number(value)


def _parse_height_and_stories(value: str) -> tuple[float | None, float | None]:
    numbers = [float(match.replace(",", "")) for match in _NUMBER_RE.findall(value)]
    if not numbers:
        return None, None
    if len(numbers) == 1:
        return numbers[0], None
    return numbers[0], numbers[1]


def _parse_miami_gardens_r1_table(html: str) -> dict[str, float | str | bool] | None:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table is None:
        return None

    general_rows: dict[str, str] = {}
    principal_rows: dict[str, str] = {}
    accessory_rows: dict[str, str] = {}
    current_section = ""
    for tr in table.find_all("tr"):
        cells = [_normalize_text(td.get_text(" ", strip=True)) for td in tr.find_all(["td", "th"])]
        if not cells:
            continue
        if len(cells) == 1:
            current_section = cells[0]
            continue
        if len(cells) < 2:
            continue
        row_label = cells[0]
        r1_value = cells[1]
        if row_label and r1_value:
            if current_section == "Principal Building Size, Setbacks and Spacing":
                principal_rows[row_label] = r1_value
            elif current_section == "Accessory Building Setbacks and Spacing":
                accessory_rows[row_label] = r1_value
            else:
                general_rows[row_label] = r1_value

    height_value = general_rows.get("Principal building(s)", "")
    max_height_ft, max_stories = _parse_height_and_stories(height_value)

    rules: dict[str, float | str | bool] = {
        "zoning_district": "R-1",
        "source": "municode_live_table",
        "requires_official_verification": True,
        "source_section_id": "Sec. 34-342. - Tables for development standards.",
        "source_url": _MIAMI_GARDENS_R1_SECTION_URL,
        "authority_source_type": "municode_live_table",
        "authority_resolution": "section_table_extract",
        "authority_confidence": "official_live_preliminary_extract",
        "authority_is_live": True,
        "authority_is_official": True,
    }
    numeric_fields = {
        "min_lot_width_ft": _parse_number(general_rows.get("Lot frontage, minimum", "")),
        "min_lot_area_sqft": _parse_number(general_rows.get("Lot area (net), minimum", "")),
        "max_density_units_per_acre": _parse_density(
            general_rows.get("Density, maximum (net)", "")
        ),
        "max_lot_coverage_pct": _parse_number(
            general_rows.get("Lot coverage principal building", "")
        ),
        "max_height_ft": max_height_ft,
        "max_stories": max_stories,
        "setback_front_ft": _parse_number(principal_rows.get("Front setback (minimum)", "")),
        "setback_rear_ft": _parse_number(principal_rows.get("Rear setback (minimum)", "")),
        "setback_side_ft": _parse_number(principal_rows.get("Interior side setback (minimum)", "")),
        "side_street_setback_ft": _parse_number(
            principal_rows.get("Side street setback (minimum)", "")
        ),
        "accessory_building_separation_ft": _parse_number(
            accessory_rows.get("Between accessory building and any other Building (minimum)", "")
        ),
    }
    for key, value in numeric_fields.items():
        if value is not None:
            rules[key] = value

    required_keys = {
        "min_lot_width_ft",
        "min_lot_area_sqft",
        "max_density_units_per_acre",
        "max_lot_coverage_pct",
        "max_height_ft",
        "setback_front_ft",
        "setback_rear_ft",
        "setback_side_ft",
    }
    if not required_keys.issubset(rules):
        return None
    return rules


async def extract_live_municode_rules(
    *,
    municipality: str,
    state: str,
    zoning_code: str,
    config: MunicodeConfig | None = None,
) -> dict[str, float | str | bool] | None:
    municipality_text = municipality.strip().casefold()
    state_text = state.strip().upper()
    zoning_text = zoning_code.strip().upper()
    if municipality_text != "miami gardens" or state_text != "FL" or zoning_text != "R-1":
        return None

    if config is None:
        configs = await get_municode_configs()
        config = resolve_municode_config(configs, municipality, state=state)
    if config is None:
        return None

    scraper = MunicodeScraper()
    with start_otel_span(
        "ordinance.extract_live_municode_rules",
        {
            "plotlot.municipality": municipality,
            "plotlot.state": state_text,
            "plotlot.zoning_code": zoning_text,
        },
    ):
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                html = await scraper.get_section_content(
                    client,
                    config,
                    _MIAMI_GARDENS_R1_TABLE_NODE_ID,
                )
            except httpx.HTTPError:
                return None
    return _parse_miami_gardens_r1_table(html)
