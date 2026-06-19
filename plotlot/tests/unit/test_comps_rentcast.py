"""Tests for the RentCast comps provider + its find_comparables fallback wiring."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from plotlot.core.types import PropertyRecord


def _mock_http(json_data: dict):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=json_data)
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(return_value=resp)
    return client


_RC_RESPONSE = {
    "price": 820000,
    "comparables": [
        {
            "formattedAddress": "1 A St",
            "price": 800000,
            "distance": 0.2,
            "removedDate": "2025-09-01",
        },
        {
            "formattedAddress": "2 B St",
            "price": 850000,
            "distance": 0.4,
            "removedDate": "2025-08-01",
        },
        {
            "formattedAddress": "3 C St",
            "price": 900000,
            "distance": 0.6,
            "removedDate": "2025-07-01",
        },
        {"formattedAddress": "4 D St", "price": 0, "distance": 0.1},  # skipped (no price)
    ],
}


class TestRentcastProvider:
    async def test_returns_comp_analysis_with_adv_from_comps(self):
        from plotlot.pipeline import comps_rentcast

        subject = PropertyRecord(county="San Diego", lat=32.76, lng=-117.19)
        with (
            patch.object(comps_rentcast.settings, "rentcast_api_key", "k"),
            patch("httpx.AsyncClient", return_value=_mock_http(_RC_RESPONSE)),
        ):
            ca = await comps_rentcast.fetch_rentcast_comps(subject)

        assert ca is not None
        assert ca.adv_source == "comps"
        assert ca.adv_per_unit == 850000  # median of 800k/850k/900k
        assert len(ca.unit_comparables) == 3  # zero-price comp dropped
        assert ca.notes and "RentCast" in ca.notes[0]

    async def test_no_key_returns_none(self):
        from plotlot.pipeline import comps_rentcast

        subject = PropertyRecord(county="San Diego", lat=32.76, lng=-117.19)
        with patch.object(comps_rentcast.settings, "rentcast_api_key", ""):
            assert await comps_rentcast.fetch_rentcast_comps(subject) is None

    async def test_no_comps_returns_none(self):
        from plotlot.pipeline import comps_rentcast

        subject = PropertyRecord(county="San Diego", lat=32.76, lng=-117.19)
        with (
            patch.object(comps_rentcast.settings, "rentcast_api_key", "k"),
            patch("httpx.AsyncClient", return_value=_mock_http({"comparables": []})),
        ):
            assert await comps_rentcast.fetch_rentcast_comps(subject) is None

    async def test_api_error_returns_none(self):
        from plotlot.pipeline import comps_rentcast

        subject = PropertyRecord(county="San Diego", lat=32.76, lng=-117.19)
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.get = AsyncMock(side_effect=Exception("boom"))
        with (
            patch.object(comps_rentcast.settings, "rentcast_api_key", "k"),
            patch("httpx.AsyncClient", return_value=client),
        ):
            assert await comps_rentcast.fetch_rentcast_comps(subject) is None


class TestFindComparablesFallback:
    async def test_rentcast_used_when_no_arcgis_dataset(self):
        """SD path: no curated source + no Hub dataset → RentCast supplies comps."""
        from plotlot.core.types import CompAnalysis
        from plotlot.pipeline.comps import find_comparables

        subject = PropertyRecord(county="San Diego", lat=32.76, lng=-117.19, lot_size_sqft=7710.0)
        rc_result = CompAnalysis()
        rc_result.adv_per_unit = 850000
        rc_result.adv_source = "comps"

        with (
            patch(
                "plotlot.pipeline.comps_sources.resolve_sales_dataset",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "plotlot.pipeline.comps._discover_sales_dataset", new=AsyncMock(return_value=None)
            ),
            patch(
                "plotlot.pipeline.comps_rentcast.rentcast_configured",
                new=MagicMock(return_value=True),
            ),
            patch(
                "plotlot.pipeline.comps_rentcast.fetch_rentcast_comps",
                new=AsyncMock(return_value=rc_result),
            ),
        ):
            out = await find_comparables(subject, state="CA")

        assert out.adv_source == "comps"
        assert out.adv_per_unit == 850000

    async def test_no_rentcast_key_falls_through_to_regional_default(self):
        from plotlot.pipeline.comps import find_comparables

        subject = PropertyRecord(county="San Diego", lat=32.76, lng=-117.19, lot_size_sqft=7710.0)
        with (
            patch(
                "plotlot.pipeline.comps_sources.resolve_sales_dataset",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "plotlot.pipeline.comps._discover_sales_dataset", new=AsyncMock(return_value=None)
            ),
            patch(
                "plotlot.pipeline.comps_rentcast.rentcast_configured",
                new=MagicMock(return_value=False),
            ),
        ):
            out = await find_comparables(subject, state="CA")

        assert out.adv_source != "comps"  # stays a regional-default estimate
        assert any("No sales dataset" in n for n in out.notes)
