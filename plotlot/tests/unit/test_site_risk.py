"""Unit tests for site risk pipeline — FEMA + NWI with mocked HTTP."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from plotlot.pipeline.site_risk import (
    FloodZoneInfo,
    SiteRisk,
    WetlandInfo,
    _fetch_fema_flood_zone,
    _fetch_nwi_wetlands,
    fetch_site_risk,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _fema_response(zone: str, subty: str = "", sfha: str = "T") -> dict:
    return {
        "features": [
            {
                "attributes": {
                    "FLD_ZONE": zone,
                    "ZONE_SUBTY": subty,
                    "SFHA_TF": sfha,
                }
            }
        ]
    }


def _nwi_response(types: list[tuple[str, float]]) -> dict:
    return {"features": [{"attributes": {"WETLAND_TYPE": t, "ACRES": a}} for t, a in types]}


def _mock_http(json_data: dict):
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=json_data)
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(return_value=resp)
    return client


# ---------------------------------------------------------------------------
# FEMA tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fema_high_risk_ae_zone():
    with patch("httpx.AsyncClient", return_value=_mock_http(_fema_response("AE"))):
        result = await _fetch_fema_flood_zone(32.7, -117.1)
    assert isinstance(result, FloodZoneInfo)
    assert result.zone == "AE"
    assert result.risk_level == "high"
    assert result.in_sfha is True


@pytest.mark.asyncio
async def test_fema_minimal_x_zone():
    with patch("httpx.AsyncClient", return_value=_mock_http(_fema_response("X", sfha="F"))):
        result = await _fetch_fema_flood_zone(32.7, -117.1)
    assert result.zone == "X"
    assert result.risk_level == "minimal"
    assert result.in_sfha is False


@pytest.mark.asyncio
async def test_fema_x500_moderate_zone():
    subty = "0.2 PCT ANNUAL CHANCE FLOOD HAZARD"
    with patch(
        "httpx.AsyncClient", return_value=_mock_http(_fema_response("X", subty=subty, sfha="F"))
    ):
        result = await _fetch_fema_flood_zone(32.7, -117.1)
    assert result.zone == "X"
    assert result.risk_level == "moderate"


@pytest.mark.asyncio
async def test_fema_no_features_returns_minimal():
    data = {"features": []}
    with patch("httpx.AsyncClient", return_value=_mock_http(data)):
        result = await _fetch_fema_flood_zone(32.7, -117.1)
    assert result is not None
    assert result.zone == "X"
    assert result.risk_level == "minimal"


@pytest.mark.asyncio
async def test_fema_api_error_returns_none():
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(side_effect=Exception("Connection refused"))
    with patch("httpx.AsyncClient", return_value=client):
        result = await _fetch_fema_flood_zone(32.7, -117.1)
    assert result is None


@pytest.mark.asyncio
async def test_fema_ve_zone_high_risk():
    with patch("httpx.AsyncClient", return_value=_mock_http(_fema_response("VE"))):
        result = await _fetch_fema_flood_zone(25.7, -80.2)
    assert result.zone == "VE"
    assert result.risk_level == "high"
    assert result.in_sfha is True


# ---------------------------------------------------------------------------
# NWI tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nwi_wetlands_detected():
    data = _nwi_response(
        [
            ("Freshwater Emergent Wetland", 0.5),
            ("Freshwater Forested/Shrub Wetland", 1.2),
        ]
    )
    with patch("httpx.AsyncClient", return_value=_mock_http(data)):
        result = await _fetch_nwi_wetlands(32.7, -117.1)
    assert len(result) == 2
    assert result[0].wetland_type == "Freshwater Emergent Wetland"
    assert result[0].acres == pytest.approx(0.5)
    assert result[1].acres == pytest.approx(1.2)


@pytest.mark.asyncio
async def test_nwi_no_wetlands():
    data = {"features": []}
    with patch("httpx.AsyncClient", return_value=_mock_http(data)):
        result = await _fetch_nwi_wetlands(32.7, -117.1)
    assert result == []


@pytest.mark.asyncio
async def test_nwi_api_error_returns_empty():
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(side_effect=Exception("timeout"))
    with patch("httpx.AsyncClient", return_value=client):
        result = await _fetch_nwi_wetlands(32.7, -117.1)
    assert result == []


# ---------------------------------------------------------------------------
# fetch_site_risk integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_site_risk_high_flood_with_wetlands():
    flood = FloodZoneInfo(
        zone="AE",
        zone_subtype="",
        in_sfha=True,
        risk_level="high",
        description="Special Flood Hazard Area — 1% annual chance flood with base flood elevation",
    )
    wetlands = [WetlandInfo(wetland_type="Freshwater Emergent Wetland", acres=0.3)]

    with (
        patch(
            "plotlot.pipeline.site_risk._fetch_fema_flood_zone", new=AsyncMock(return_value=flood)
        ),
        patch(
            "plotlot.pipeline.site_risk._fetch_nwi_wetlands", new=AsyncMock(return_value=wetlands)
        ),
        patch(
            "plotlot.pipeline.site_risk._fetch_geologic_hazard", new=AsyncMock(return_value=None)
        ),
        patch(
            "plotlot.pipeline.site_risk._fetch_airport_influence", new=AsyncMock(return_value=[])
        ),
    ):
        result = await fetch_site_risk(32.7, -117.1)

    assert isinstance(result, SiteRisk)
    assert result.overall_risk == "high"
    assert result.has_wetlands is True
    assert len(result.risk_flags) >= 2  # flood flag + wetland flag
    assert any("SFHA" in f for f in result.risk_flags)
    assert any("Wetland" in f or "wetland" in f.lower() for f in result.risk_flags)
    assert "FEMA National Flood Hazard Layer (NFHL)" in result.data_sources


@pytest.mark.asyncio
async def test_fetch_site_risk_minimal_no_wetlands():
    flood = FloodZoneInfo(
        zone="X",
        zone_subtype="",
        in_sfha=False,
        risk_level="minimal",
        description="Minimal flood hazard",
    )
    with (
        patch(
            "plotlot.pipeline.site_risk._fetch_fema_flood_zone", new=AsyncMock(return_value=flood)
        ),
        patch("plotlot.pipeline.site_risk._fetch_nwi_wetlands", new=AsyncMock(return_value=[])),
        patch(
            "plotlot.pipeline.site_risk._fetch_geologic_hazard", new=AsyncMock(return_value=None)
        ),
        patch(
            "plotlot.pipeline.site_risk._fetch_airport_influence", new=AsyncMock(return_value=[])
        ),
    ):
        result = await fetch_site_risk(32.7, -117.1)

    assert result.overall_risk == "low"
    assert result.has_wetlands is False
    assert result.risk_flags == []


@pytest.mark.asyncio
async def test_fetch_site_risk_fema_unavailable_degrades_gracefully():
    wetlands = []
    with (
        patch(
            "plotlot.pipeline.site_risk._fetch_fema_flood_zone", new=AsyncMock(return_value=None)
        ),
        patch(
            "plotlot.pipeline.site_risk._fetch_nwi_wetlands", new=AsyncMock(return_value=wetlands)
        ),
        patch(
            "plotlot.pipeline.site_risk._fetch_geologic_hazard", new=AsyncMock(return_value=None)
        ),
        patch(
            "plotlot.pipeline.site_risk._fetch_airport_influence", new=AsyncMock(return_value=[])
        ),
    ):
        result = await fetch_site_risk(32.7, -117.1)

    assert result.overall_risk == "unknown"
    assert result.flood_zone is None
    assert "USFWS National Wetlands Inventory (NWI)" in result.data_sources


# ---------------------------------------------------------------------------
# CGS geologic / seismic hazard tests
# ---------------------------------------------------------------------------

from plotlot.core.types import GeologicHazard  # noqa: E402
from plotlot.pipeline.site_risk import _fetch_geologic_hazard  # noqa: E402


def _geo_feature(fault: int, landslide: int, liquefaction: int) -> list[dict]:
    return [
        {
            "attributes": {
                "FaultZone": fault,
                "LandslideZone": landslide,
                "LiquefactionZone": liquefaction,
            }
        }
    ]


async def test_geologic_not_evaluated_is_honest_unknown():
    # 1233 Hueneme St: fault=1 (not in zone), landslide=4 / liquefaction=4 (NOT evaluated).
    with patch(
        "plotlot.property.arcgis_utils.spatial_query",
        new=AsyncMock(return_value=_geo_feature(1, 4, 4)),
    ):
        geo = await _fetch_geologic_hazard(32.7677, -117.1858)

    assert isinstance(geo, GeologicHazard)
    assert "not within" in geo.fault_zone.lower()
    assert geo.in_any_hazard_zone is False
    assert geo.evaluated is False  # NOT a clearance — CGS hasn't mapped it
    assert any("not evaluated" in f.lower() and "geotechnical" in f.lower() for f in geo.flags)


async def test_geologic_within_landslide_zone_raises_flag():
    with patch(
        "plotlot.property.arcgis_utils.spatial_query",
        new=AsyncMock(return_value=_geo_feature(1, 1, 2)),
    ):
        geo = await _fetch_geologic_hazard(34.0, -118.0)

    assert geo is not None
    assert geo.in_any_hazard_zone is True
    assert any("landslide" in f.lower() for f in geo.flags)


async def test_geologic_within_fault_zone_raises_flag():
    with patch(
        "plotlot.property.arcgis_utils.spatial_query",
        new=AsyncMock(return_value=_geo_feature(2, 2, 2)),
    ):
        geo = await _fetch_geologic_hazard(34.0, -118.0)

    assert geo is not None
    assert geo.in_any_hazard_zone is True
    assert geo.evaluated is True
    assert any("fault" in f.lower() for f in geo.flags)


async def test_geologic_outside_california_returns_none():
    with patch(
        "plotlot.property.arcgis_utils.spatial_query",
        new=AsyncMock(return_value=[]),
    ):
        assert await _fetch_geologic_hazard(25.76, -80.19) is None  # Miami → no CA parcel


async def test_geologic_api_error_returns_none():
    with patch(
        "plotlot.property.arcgis_utils.spatial_query",
        new=AsyncMock(side_effect=Exception("timeout")),
    ):
        assert await _fetch_geologic_hazard(32.7, -117.1) is None


async def test_fetch_site_risk_includes_geologic():
    with (
        patch("httpx.AsyncClient", return_value=_mock_http(_fema_response("X", sfha="F"))),
        patch(
            "plotlot.property.arcgis_utils.spatial_query",
            new=AsyncMock(return_value=_geo_feature(1, 4, 4)),
        ),
    ):
        risk = await fetch_site_risk(32.7677, -117.1858)

    assert risk.geologic is not None
    assert risk.geologic.evaluated is False
    assert any("CGS" in s for s in risk.data_sources)
    assert any("not evaluated" in f.lower() for f in risk.risk_flags)


# ---------------------------------------------------------------------------
# City of San Diego Airport Influence Area tests
# ---------------------------------------------------------------------------

from plotlot.pipeline.site_risk import _fetch_airport_influence  # noqa: E402


async def test_airport_influence_returns_zone_labels():
    feats = [
        {"attributes": {"Airport": "San Diego International Airport", "Label": "Review Area 2"}},
        {"attributes": {"Airport": "San Diego International Airport", "Label": "Review Area 2"}},
    ]
    with patch("plotlot.property.arcgis_utils.spatial_query", new=AsyncMock(return_value=feats)):
        out = await _fetch_airport_influence(32.7677, -117.1858)
    # De-duplicated, human-readable.
    assert out == ["San Diego International Airport — Review Area 2"]


async def test_airport_influence_empty_when_not_in_area():
    with patch("plotlot.property.arcgis_utils.spatial_query", new=AsyncMock(return_value=[])):
        assert await _fetch_airport_influence(40.0, -100.0) == []


async def test_airport_influence_api_error_returns_empty():
    with patch(
        "plotlot.property.arcgis_utils.spatial_query",
        new=AsyncMock(side_effect=Exception("boom")),
    ):
        assert await _fetch_airport_influence(32.7, -117.1) == []
