from __future__ import annotations

import httpx
import pytest

from plotlot.harness.official_dimensional_sources import (
    WEST_PALM_NWD_REQUIREMENTS_URL,
    WEST_PALM_NWD_STANDARDS_URL,
    resolve_official_dimensional_rules,
)


SECTION_94_84_HTML = """
<html><body>
<h1>Sec. 94-84. Historic multifamily context 1 (NWD-R-C1).</h1>
<p>Lot area: 4,500 square feet; Lot width: 45 feet.</p>
<p>Where a contextual front setback has not been established, the minimum
front setback shall be 15 feet.</p>
<p>Corner: For lots up to 4,999 square feet: 10 feet; For lots 5,000 to
7,499 square feet: 12.5 feet; For lots 7,500 square feet and over: 15 feet.</p>
<p>Rear: 15 feet, or 10 percent of the lot depth, whichever is less.</p>
<p>Side minimum (one side only): 5 feet.</p>
<p>Side minimum cumulative (both sides): For lots up to 7,499 square feet:
15 feet; For lots 7,500 square feet and over: 20 feet.</p>
<p>Garage location: side or rear loaded garages meet applicable setbacks.</p>
<p>Maximum height of principal structure. For lots up to 4,999 square feet:
24 feet; For lots 5,000 to 7,499 square feet: 27 feet; For lots 7,500 square
feet and over: 32 feet.</p>
<p>Maximum lot coverage for all structures: For lots up to 4,999 square feet:
35 percent; For lots 5,000 to 7,499 square feet: 30 percent; For lots 7,500
square feet and over: 25 percent.</p>
<p>Maximum floor area ratio for all structures: For lots up to 4,999 square
feet: 0.55; For lots 5,000 to 7,499 square feet: 0.50; For lots 7,500 square
feet and over: 0.45.</p>
</body></html>
"""

SECTION_94_128_HTML = """
<html><body>
<h1>Sec. 94-128. Northwest neighborhood district (NWD).</h1>
<p>6. Table IV-39: NWD-R-C1.</p>
<p>Building requirements for NWD-R-C1 are included in section 94-84.</p>
<p>Table IV-38: Building Requirements - NWD-2. Density Maximum 20 DU/Acre.</p>
<p>Table IV-38a: Building Requirements - NWD-2C. Density Maximum 20 DU/Acre.</p>
<p>Table IV-39: Building Requirements - NWD-R-C1. Density Maximum 14 DU/Acre.</p>
</body></html>
"""


@pytest.mark.parametrize(
    ("lot_area_sqft", "height_ft", "coverage_pct", "far"),
    [
        (4_900.0, 24.0, 35.0, 0.55),
        (7_000.0, 27.0, 30.0, 0.50),
        (7_500.0, 32.0, 25.0, 0.45),
    ],
)
async def test_resolves_current_west_palm_nwd_r_tier_from_official_pages(
    lot_area_sqft: float,
    height_ft: float,
    coverage_pct: float,
    far: float,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == WEST_PALM_NWD_STANDARDS_URL:
            return httpx.Response(200, text=SECTION_94_84_HTML)
        if str(request.url) == WEST_PALM_NWD_REQUIREMENTS_URL:
            return httpx.Response(200, text=SECTION_94_128_HTML)
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        payload = await resolve_official_dimensional_rules(
            municipality="WEST PALM BEACH",
            zoning_code="NWD-R (city)",
            lot_area_sqft=lot_area_sqft,
            lot_depth_ft=100.0,
            client=client,
        )

    assert payload is not None
    assert payload["authority_is_live"] is True
    assert payload["authority_is_official"] is True
    assert payload["requires_official_verification"] is False
    rules = payload["rules"]
    assert rules["zoning_district"] == "NWD-R-C1"
    assert rules["max_height_ft"] == height_ft
    assert rules["max_lot_coverage_pct"] == coverage_pct
    assert rules["far"] == far
    assert rules["max_density_units_per_acre"] == 14.0
    assert rules["setback_rear_ft"] == 10.0
    assert rules["source_section_id"] == "Sec. 94-84; Sec. 94-128 Table IV-39"
    assert len(payload["results"]) == 2


async def test_west_palm_resolver_fails_closed_when_density_section_is_incomplete() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == WEST_PALM_NWD_STANDARDS_URL:
            return httpx.Response(200, text=SECTION_94_84_HTML)
        if str(request.url) == WEST_PALM_NWD_REQUIREMENTS_URL:
            return httpx.Response(200, text="<p>Table IV-39 unavailable</p>")
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        payload = await resolve_official_dimensional_rules(
            municipality="West Palm Beach",
            zoning_code="NWD-R",
            lot_area_sqft=7_000.0,
            lot_depth_ft=None,
            client=client,
        )

    assert payload is None


async def test_official_resolver_ignores_unsupported_jurisdictions_without_network() -> None:
    called = False

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        payload = await resolve_official_dimensional_rules(
            municipality="Miami",
            zoning_code="NWD-R",
            lot_area_sqft=7_000.0,
            lot_depth_ft=100.0,
            client=client,
        )

    assert payload is None
    assert called is False
