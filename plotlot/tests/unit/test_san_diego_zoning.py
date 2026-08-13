"""San Diego per-city zoning registry.

The safety tests matter more than the happy path here. A wrong zone code selects
another district's dimensional standard and produces a confidently wrong unit
count, which is worse than returning nothing — the pipeline already handles an
undetermined district honestly.
"""

from unittest.mock import AsyncMock, patch

import pytest

from plotlot.property.san_diego_zoning import (
    _SD_CITY_ZONING,
    _is_usable_district,
    resolve_san_diego_zone,
)


def _features(code: str) -> list[dict]:
    return [{"attributes": {"ZONING": code, "APN": "2255935000"}}]


class TestUsableDistrict:
    @pytest.mark.parametrize("code", ["R-1-6", "R-1-7", "R-1-10", "RE-20", "S-P", "PD-R-3.3"])
    def test_plain_codes_are_usable(self, code):
        """A code with no stored standard (S-P, PD-R) is still 'usable' — it just
        misses the join downstream. Only ambiguous/out-of-jurisdiction shapes are
        refused here."""
        assert _is_usable_district(code) is True

    @pytest.mark.parametrize(
        "code",
        [
            "PZ-R-1-10",  # contains R-1-10 but is county authority until annexed
            "PZ-RE-20",
            "R-1-10/RE-20",  # split-zoned; contains R-1-10
            "RE-20/R-1-10",
            "R-1-7/FCC",
            "COUNTY",
            "county",
            "",
            "   ",
        ],
    )
    def test_ambiguous_and_foreign_codes_are_refused(self, code):
        assert _is_usable_district(code) is False


class TestResolveSanDiegoZone:
    @pytest.mark.asyncio
    async def test_returns_exact_code_for_registered_city(self):
        with patch(
            "plotlot.property.arcgis_utils.spatial_query",
            new=AsyncMock(return_value=_features("R-1-6")),
        ):
            code, desc = await resolve_san_diego_zone("Escondido", 33.145686, -117.049988)
        assert code == "R-1-6"
        assert desc is None

    @pytest.mark.asyncio
    async def test_municipality_match_is_case_insensitive(self):
        with patch(
            "plotlot.property.arcgis_utils.spatial_query",
            new=AsyncMock(return_value=_features("R-1-7")),
        ):
            code, _ = await resolve_san_diego_zone("  ESCONDIDO ", 33.149, -117.059284)
        assert code == "R-1-7"

    @pytest.mark.asyncio
    async def test_blank_municipality_still_resolves_by_geometry(self):
        """SD parcels come from the statewide layer with a blank SITE_CITY, so the
        name is usually absent. Geometry must carry the lookup on its own."""
        with patch(
            "plotlot.property.arcgis_utils.spatial_query",
            new=AsyncMock(return_value=_features("R-1-6")),
        ):
            code, _ = await resolve_san_diego_zone("", 33.145686, -117.049988)
        assert code == "R-1-6"

    @pytest.mark.asyncio
    async def test_unregistered_city_falls_back_to_geometry(self):
        """An unrecognised name is a hint that missed, not a reason to give up —
        the fan-out still asks every registered layer."""
        spy = AsyncMock(return_value=_features("R-1-6"))
        with patch("plotlot.property.arcgis_utils.spatial_query", new=spy):
            code, _ = await resolve_san_diego_zone("Carlsbad", 33.145686, -117.049988)
        assert code == "R-1-6"
        spy.assert_awaited()

    @pytest.mark.asyncio
    async def test_parcel_outside_every_registered_city_returns_none(self):
        with patch(
            "plotlot.property.arcgis_utils.spatial_query",
            new=AsyncMock(return_value=[]),
        ):
            code, _ = await resolve_san_diego_zone("", 32.7, -117.16)
        assert code is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("code", ["PZ-R-1-10", "R-1-10/RE-20", "COUNTY"])
    async def test_refused_codes_resolve_to_no_district(self, code):
        """The substring trap: each of these contains or resembles a valid stored
        district, and each must still yield None."""
        with patch(
            "plotlot.property.arcgis_utils.spatial_query",
            new=AsyncMock(return_value=_features(code)),
        ):
            resolved, _ = await resolve_san_diego_zone("Escondido", 33.1, -117.0)
        assert resolved is None

    @pytest.mark.asyncio
    async def test_no_polygon_at_point_returns_none(self):
        with patch(
            "plotlot.property.arcgis_utils.spatial_query",
            new=AsyncMock(return_value=[]),
        ):
            code, _ = await resolve_san_diego_zone("Escondido", 33.1, -117.0)
        assert code is None

    @pytest.mark.asyncio
    async def test_layer_outage_is_swallowed(self):
        """Zoning enrichment is best-effort; an outage must not fail the lookup."""
        with patch(
            "plotlot.property.arcgis_utils.spatial_query",
            new=AsyncMock(side_effect=RuntimeError("503")),
        ):
            code, _ = await resolve_san_diego_zone("Escondido", 33.1, -117.0)
        assert code is None


class TestRegistryIntegrity:
    def test_every_entry_records_its_verification(self):
        """An entry that cannot say what it was proven against must not ship."""
        for city, entry in _SD_CITY_ZONING.items():
            assert entry.url.startswith("https://"), city
            assert entry.zone_field, city
            assert entry.verified_at, city
            assert entry.verified_code, city

    def test_verified_codes_are_themselves_usable(self):
        for city, entry in _SD_CITY_ZONING.items():
            assert _is_usable_district(entry.verified_code), city

    def test_keys_are_lowercase(self):
        for city in _SD_CITY_ZONING:
            assert city == city.lower()
