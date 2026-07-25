from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from plotlot.land_use.ordinances.live_rules import (
    _parse_miami_gardens_r1_table,
    extract_live_municode_rules,
)

_MIAMI_GARDENS_R1_HTML = (
    '<div class="chunk-title">Sec. 34-342. - Tables for development standards.</div>'
    "<table>"
    "<tr><td>Table 1. Development Standards</td></tr>"
    "<tr><td>Zoning Districts</td></tr>"
    "<tr><td></td><td>R-1, Single-Family; R-2, Two-family</td><td>Townhouse</td><td>Multiple-family</td></tr>"
    "<tr><td></td><td>Single-family Detached Two-Family, Duplex</td><td>Townhouse</td><td>Multiple-family</td></tr>"
    "<tr><td>Lot frontage, minimum</td><td>75 ft.</td><td>96 ft.</td><td>100 ft.</td></tr>"
    "<tr><td>Lot area (net), minimum</td><td>7,500 s.f.</td><td>2,200 s.f.</td><td>10,000 s.f.</td></tr>"
    "<tr><td>Density, maximum (net)</td><td>Up to 6 du/ac</td><td>Up to 15 du/ac</td><td>Up to 50 du/ac</td></tr>"
    "<tr><td>Lot coverage principal building</td><td>40% max.</td><td>70 max. per lot</td><td>60 max.</td></tr>"
    "<tr><td>Maximum Height</td></tr>"
    "<tr><td>Principal building(s)</td><td>35 ft./2 stories</td><td>40 ft./3 stories</td><td>120 ft./10 stories</td></tr>"
    "<tr><td>Principal Building Size, Setbacks and Spacing</td></tr>"
    "<tr><td>Front setback (minimum)</td><td>25 ft.</td><td>20 ft.</td><td>25 ft.</td></tr>"
    "<tr><td>Rear setback (minimum)</td><td>25 ft.</td><td>15 ft.</td><td>25 ft.</td></tr>"
    "<tr><td>Interior side setback (minimum)</td><td>7.5 ft. min. or 10% of lot width but not less than 5 ft.</td><td>15 ft.</td><td>15 ft.</td></tr>"
    "<tr><td>Side street setback (minimum)</td><td>15 ft.</td><td>15 ft.</td><td>20 ft.</td></tr>"
    "<tr><td>Accessory Building Setbacks and Spacing</td></tr>"
    "<tr><td>Between accessory building and any other Building (minimum)</td><td>10 ft.</td><td>10 ft.</td><td>20 ft.</td></tr>"
    "</table>"
)


def test_parse_miami_gardens_r1_table_extracts_dimensional_rules() -> None:
    rules = _parse_miami_gardens_r1_table(_MIAMI_GARDENS_R1_HTML)

    assert rules is not None
    assert rules["zoning_district"] == "R-1"
    assert rules["source"] == "municode_live_table"
    assert rules["authority_source_type"] == "municode_live_table"
    assert rules["authority_confidence"] == "official_live_preliminary_extract"
    assert rules["authority_is_live"] is True
    assert rules["authority_is_official"] is True
    assert rules["min_lot_width_ft"] == 75.0
    assert rules["min_lot_area_sqft"] == 7500.0
    assert rules["max_density_units_per_acre"] == 6.0
    assert rules["max_lot_coverage_pct"] == 40.0
    assert rules["max_height_ft"] == 35.0
    assert rules["max_stories"] == 2.0
    assert rules["setback_front_ft"] == 25.0
    assert rules["setback_rear_ft"] == 25.0
    assert rules["setback_side_ft"] == 7.5
    assert rules["accessory_building_separation_ft"] == 10.0


@pytest.mark.asyncio
async def test_extract_live_municode_rules_returns_none_for_unsupported_jurisdiction() -> None:
    rules = await extract_live_municode_rules(
        municipality="Fort Lauderdale",
        state="FL",
        zoning_code="R-1",
    )

    assert rules is None


@pytest.mark.asyncio
async def test_extract_live_municode_rules_fetches_and_parses_miami_gardens_table() -> None:
    fake_config = object()

    with (
        patch(
            "plotlot.land_use.ordinances.live_rules.get_municode_configs",
            new=AsyncMock(return_value={"miami_gardens": fake_config}),
        ),
        patch(
            "plotlot.land_use.ordinances.live_rules.resolve_municode_config",
            return_value=fake_config,
        ),
        patch(
            "plotlot.land_use.ordinances.live_rules.MunicodeScraper.get_section_content",
            new=AsyncMock(return_value=_MIAMI_GARDENS_R1_HTML),
        ) as content_mock,
    ):
        rules = await extract_live_municode_rules(
            municipality="Miami Gardens",
            state="FL",
            zoning_code="R-1",
        )

    assert rules is not None
    assert rules["min_lot_area_sqft"] == 7500.0
    assert rules["setback_front_ft"] == 25.0
    content_mock.assert_awaited_once()
