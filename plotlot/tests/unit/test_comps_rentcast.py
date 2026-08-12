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
            attempt = await comps_rentcast.fetch_rentcast_comps(subject)

        ca = attempt.analysis
        assert attempt.ok and ca is not None
        assert attempt.reason == ""
        assert ca.adv_source == "comps"
        assert ca.adv_per_unit == 850000  # median of 800k/850k/900k
        assert len(ca.unit_comparables) == 3  # zero-price comp dropped
        assert ca.notes and "RentCast" in ca.notes[0]

    async def test_no_key_reports_unconfigured(self):
        from plotlot.pipeline import comps_rentcast

        subject = PropertyRecord(county="San Diego", lat=32.76, lng=-117.19)
        with patch.object(comps_rentcast.settings, "rentcast_api_key", ""):
            attempt = await comps_rentcast.fetch_rentcast_comps(subject)
        assert attempt.analysis is None
        assert "not configured" in attempt.reason
        assert attempt.provider_answered is False

    async def test_no_comps_is_distinguishable_from_a_refusal(self):
        """The provider answered and had nothing — benign, and NOT the same as a
        dead subscription. `provider_answered` is what separates them."""
        from plotlot.pipeline import comps_rentcast

        subject = PropertyRecord(county="San Diego", lat=32.76, lng=-117.19)
        with (
            patch.object(comps_rentcast.settings, "rentcast_api_key", "k"),
            patch("httpx.AsyncClient", return_value=_mock_http({"comparables": []})),
        ):
            attempt = await comps_rentcast.fetch_rentcast_comps(subject)
        assert attempt.analysis is None
        assert attempt.provider_answered is True
        assert "no comparable sales" in attempt.reason

    async def test_inactive_subscription_surfaces_the_providers_own_error_slug(self):
        """The real 2026-08-10 failure: a valid key with a dead subscription. The
        report must be able to say `billing/subscription-inactive`, because that
        names a billing page to visit rather than a bug to hunt."""
        import httpx

        from plotlot.pipeline import comps_rentcast

        subject = PropertyRecord(county="San Diego", lat=32.76, lng=-117.19)
        response = httpx.Response(
            403,
            json={
                "status": 403,
                "error": "billing/subscription-inactive",
                "message": "The provided API key is not associated with an active subscription.",
            },
            request=httpx.Request("GET", comps_rentcast._RENTCAST_AVM_URL),
        )
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.get = AsyncMock(return_value=response)
        with (
            patch.object(comps_rentcast.settings, "rentcast_api_key", "k"),
            patch("httpx.AsyncClient", return_value=client),
        ):
            attempt = await comps_rentcast.fetch_rentcast_comps(subject)

        assert attempt.analysis is None
        assert attempt.provider_answered is False
        assert "403" in attempt.reason
        assert "billing/subscription-inactive" in attempt.reason

    async def test_api_error_reports_the_failure(self):
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
            attempt = await comps_rentcast.fetch_rentcast_comps(subject)
        assert attempt.analysis is None
        assert "failed" in attempt.reason


class TestFindComparablesFallback:
    async def test_rentcast_used_when_no_arcgis_dataset(self):
        """SD path: no curated source + no Hub dataset → RentCast supplies comps."""
        from plotlot.core.types import CompAnalysis
        from plotlot.pipeline.comps import find_comparables

        from plotlot.pipeline.comps_rentcast import RentcastAttempt

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
                "plotlot.pipeline.comps_rentcast.fetch_rentcast_comps",
                new=AsyncMock(
                    return_value=RentcastAttempt(analysis=rc_result, provider_answered=True)
                ),
            ),
        ):
            out = await find_comparables(subject, state="CA")

        assert out.adv_source == "comps"
        assert out.adv_per_unit == 850000

    async def test_no_rentcast_key_falls_through_to_regional_default(self):
        from plotlot.pipeline import comps_rentcast
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
            patch.object(comps_rentcast.settings, "rentcast_api_key", ""),
        ):
            out = await find_comparables(subject, state="CA")

        assert out.adv_source != "comps"  # stays a regional-default estimate
        note = " ".join(out.notes)
        assert "No open sales dataset" in note
        assert "not configured" in note

    async def test_a_dead_subscription_is_reported_not_disguised_as_no_coverage(self):
        """The 2026-08-10 San Diego failure, end to end.

        Both a dead provider and an uncovered market land on the same $750k regional
        default. The note must distinguish them, or an operator spends the evening
        doubting the comps logic instead of visiting a billing page."""
        from plotlot.pipeline.comps import find_comparables
        from plotlot.pipeline.comps_rentcast import RentcastAttempt

        subject = PropertyRecord(county="San Diego", lat=32.76, lng=-117.19, lot_size_sqft=7710.0)
        refusal = RentcastAttempt(
            reason="RentCast refused the request (HTTP 403: billing/subscription-inactive)"
        )
        with (
            patch(
                "plotlot.pipeline.comps_sources.resolve_sales_dataset",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "plotlot.pipeline.comps._discover_sales_dataset", new=AsyncMock(return_value=None)
            ),
            patch(
                "plotlot.pipeline.comps_rentcast.fetch_rentcast_comps",
                new=AsyncMock(return_value=refusal),
            ),
        ):
            out = await find_comparables(subject, state="CA")

        note = " ".join(out.notes)
        assert "billing/subscription-inactive" in note
        assert "regional default" in note
