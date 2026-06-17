"""Unit tests for San Diego Coastal Height Limit Overlay (Prop D) detection.

The live ArcGIS call is mocked; we test the in/out/unverified/not-applicable
classification and the jurisdiction gate. No network is exercised.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from plotlot.core.types import CoastalHeightOverlay
from plotlot.pipeline.coastal_overlay import (
    PROP_D_HEIGHT_LIMIT_FT,
    fetch_coastal_height_overlay,
    is_san_diego_city,
)

# A point west of I-5 in San Diego (Point Loma area) — illustrative only; the
# polygon membership is mocked, so the exact coordinates do not matter.
_SD_LAT, _SD_LNG = 32.7325, -117.2310


# ---------------------------------------------------------------------------
# Jurisdiction gate
# ---------------------------------------------------------------------------


class TestJurisdictionGate:
    def test_city_san_diego_ca(self):
        assert is_san_diego_city("San Diego", "San Diego", "CA") is True

    def test_county_san_diego_empty_city(self):
        assert is_san_diego_city("", "San Diego County", "CA") is True

    def test_other_ca_city_in_sd_county_still_attempts(self):
        # Chula Vista is in San Diego County — the authoritative polygon will
        # return "out", so attempting is correct (and cheap).
        assert is_san_diego_city("Chula Vista", "San Diego", "CA") is True

    def test_non_ca_rejected(self):
        assert is_san_diego_city("San Diego", "San Diego", "TX") is False

    def test_other_ca_county_rejected(self):
        assert is_san_diego_city("Los Angeles", "Los Angeles", "CA") is False

    def test_full_state_name_accepted(self):
        assert is_san_diego_city("San Diego", "San Diego", "California") is True


# ---------------------------------------------------------------------------
# Detection classification (mocked spatial query)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_in_overlay_applies_30ft_cap():
    feature = {"attributes": {"ZONENAME": "Coastal Height Limit", "ORDNUM": "10960"}}
    with patch(
        "plotlot.pipeline.coastal_overlay.spatial_query",
        new=AsyncMock(return_value=[feature]),
    ):
        result = await fetch_coastal_height_overlay(
            _SD_LAT, _SD_LNG, city="San Diego", county="San Diego", state="CA"
        )
    assert isinstance(result, CoastalHeightOverlay)
    assert result.applies is True
    assert result.status == "in"
    assert result.height_limit_ft == PROP_D_HEIGHT_LIMIT_FT
    assert result.zone_name == "Coastal Height Limit"
    assert "Prop" in result.citation
    assert result.note


@pytest.mark.asyncio
async def test_in_overlay_blank_zonename_falls_back():
    feature = {"attributes": {"ZONENAME": "", "ORDNUM": ""}}
    with patch(
        "plotlot.pipeline.coastal_overlay.spatial_query",
        new=AsyncMock(return_value=[feature]),
    ):
        result = await fetch_coastal_height_overlay(
            _SD_LAT, _SD_LNG, city="San Diego", county="San Diego", state="CA"
        )
    assert result.applies is True
    assert result.zone_name == "Coastal Height Limitation Overlay Zone"


@pytest.mark.asyncio
async def test_out_of_overlay_no_cap():
    with patch(
        "plotlot.pipeline.coastal_overlay.spatial_query",
        new=AsyncMock(return_value=[]),
    ):
        result = await fetch_coastal_height_overlay(
            _SD_LAT, _SD_LNG, city="San Diego", county="San Diego", state="CA"
        )
    assert result.applies is False
    assert result.status == "out"
    assert result.height_limit_ft is None


@pytest.mark.asyncio
async def test_service_unavailable_is_unverified_not_silent():
    with patch(
        "plotlot.pipeline.coastal_overlay.spatial_query",
        new=AsyncMock(side_effect=RuntimeError("connection reset")),
    ):
        result = await fetch_coastal_height_overlay(
            _SD_LAT, _SD_LNG, city="San Diego", county="San Diego", state="CA"
        )
    # Fail loud, not silently wrong: no cap applied, but a verify-warning surfaced.
    assert result.applies is False
    assert result.status == "unverified"
    assert result.height_limit_ft is None
    assert "could not be confirmed" in result.note


@pytest.mark.asyncio
async def test_non_san_diego_short_circuits_without_query():
    mock = AsyncMock(return_value=[])
    with patch("plotlot.pipeline.coastal_overlay.spatial_query", new=mock):
        result = await fetch_coastal_height_overlay(
            34.0522, -118.2437, city="Los Angeles", county="Los Angeles", state="CA"
        )
    assert result.status == "not_applicable"
    assert result.applies is False
    mock.assert_not_called()  # gated out before any network call
