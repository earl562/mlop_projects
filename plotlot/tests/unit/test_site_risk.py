"""Unit tests for site risk pipeline — FEMA + NWI with mocked HTTP."""

from __future__ import annotations

import json
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
    ):
        result = await fetch_site_risk(32.7, -117.1)

    assert result.overall_risk == "unknown"
    assert result.flood_zone is None
    assert "USFWS National Wetlands Inventory (NWI)" in result.data_sources
