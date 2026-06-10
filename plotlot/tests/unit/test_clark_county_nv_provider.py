"""Unit tests for ClarkCountyNVProvider.

Validates the spatial-query-based lookup for Clark County, Nevada (Las Vegas).
All HTTP calls are mocked — no live ArcGIS requests.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from plotlot.property.clark_county_nv import ClarkCountyNVProvider

# Real coordinates for 2975 Montessouri St, Las Vegas NV (geocoded via Nominatim)
_LAT = 36.1520769
_LNG = -115.2482421


def _arcgis_response(features: list[dict]) -> MagicMock:
    """Build a fake httpx response for an ArcGIS query."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"features": features}
    return mock_resp


def _lv_zoning_feature() -> dict:
    return {"attributes": {"ZONE": "R-E", "DESCRIPTIO": "Residential Estates"}}


def _parcel_feature() -> dict:
    return {"attributes": {"APN": "16303605012", "ASSR_ACRES": 0.54, "CALC_ACRES": None}}


def _cc_zoning_feature() -> dict:
    return {"attributes": {"ZNCLASS": "CITY", "Description": "Incorporated Clark County"}}


# ---------------------------------------------------------------------------
# Core lookup tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lookup_returns_record_with_zoning_and_lot() -> None:
    """Full happy path: parcel + LV zoning both return data."""
    provider = ClarkCountyNVProvider()

    async def fake_get(url: str, params: dict | None = None):
        if "LandApp" in url:
            return _arcgis_response([_parcel_feature()])
        if "MapServer/7" in url:
            return _arcgis_response([_lv_zoning_feature()])
        return _arcgis_response([])

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=fake_get)

    with patch("plotlot.property.clark_county_nv.httpx.AsyncClient", return_value=mock_client):
        record = await provider.lookup(
            "2975 Montessouri St, Las Vegas, NV 89117",
            "Clark",
            lat=_LAT,
            lng=_LNG,
            state="NV",
        )

    assert record is not None
    assert record.zoning_code == "R-E"
    assert record.zoning_description == "Residential Estates"
    assert record.folio == "16303605012"
    assert abs(record.lot_size_sqft - 0.54 * 43560) < 1.0
    assert record.county == "Clark"
    # City of Las Vegas layer (7) returned the code → incorporated → "Las Vegas"
    assert record.municipality == "Las Vegas"
    assert record.lat == _LAT
    assert record.lng == _LNG


@pytest.mark.asyncio
async def test_lookup_falls_back_to_cc_zoning_when_lv_empty() -> None:
    """When LV zoning returns no features, use Clark County unincorporated layer."""
    provider = ClarkCountyNVProvider()

    async def fake_get(url: str, params: dict | None = None):
        if "LandApp" in url:
            return _arcgis_response([_parcel_feature()])
        if "MapServer/7" in url:
            return _arcgis_response([])  # no LV zoning
        if "MapServer/11" in url:
            return _arcgis_response([{"attributes": {"ZNCLASS": "R-U", "Description": "Rural"}}])
        return _arcgis_response([])

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=fake_get)

    with patch("plotlot.property.clark_county_nv.httpx.AsyncClient", return_value=mock_client):
        record = await provider.lookup("some address", "Clark", lat=_LAT, lng=_LNG)

    assert record is not None
    assert record.zoning_code == "R-U"
    assert record.zoning_description == "Rural"
    # County layer (11) matched → unincorporated → jurisdiction is "Clark County",
    # NOT the mailing city. This label is what routes ordinance ingest/search to
    # the body that actually adopted the code (Clark County is on Municode).
    assert record.municipality == "Clark County"
    assert record.zoning_layer_url.endswith("MapServer/11")


@pytest.mark.asyncio
async def test_unincorporated_rs20_labels_clark_county() -> None:
    """The real test case: GIS layer reports 'RS20' from the county layer.

    The City of Las Vegas layer returns ZNCLASS=CITY (parcel is outside the
    incorporated city), so the county layer is authoritative and the
    jurisdiction must be labeled 'Clark County'.
    """
    provider = ClarkCountyNVProvider()

    async def fake_get(url: str, params: dict | None = None):
        if "LandApp" in url:
            return _arcgis_response([_parcel_feature()])
        if "MapServer/7" in url:
            return _arcgis_response([_cc_zoning_feature()])  # ZNCLASS=CITY → not in city
        if "MapServer/11" in url:
            return _arcgis_response(
                [{"attributes": {"ZNCLASS": "RS20", "Description": "Residential Single-Family 20"}}]
            )
        return _arcgis_response([])

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=fake_get)

    with patch("plotlot.property.clark_county_nv.httpx.AsyncClient", return_value=mock_client):
        record = await provider.lookup(
            "2975 Montessouri St, Las Vegas, NV 89117", "Clark", lat=_LAT, lng=_LNG, state="NV"
        )

    assert record is not None
    assert record.zoning_code == "RS20"
    assert record.municipality == "Clark County"


@pytest.mark.asyncio
async def test_lookup_returns_none_when_lat_lng_missing() -> None:
    """Provider requires lat/lng — returns None when not provided."""
    provider = ClarkCountyNVProvider()
    record = await provider.lookup("2975 Montessouri St", "Clark", lat=None, lng=None)
    assert record is None


@pytest.mark.asyncio
async def test_lookup_returns_none_when_no_data_at_location() -> None:
    """When both parcel and zoning return empty, returns None."""
    provider = ClarkCountyNVProvider()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=_arcgis_response([]))

    with patch("plotlot.property.clark_county_nv.httpx.AsyncClient", return_value=mock_client):
        record = await provider.lookup("unknown address", "Clark", lat=_LAT, lng=_LNG)

    assert record is None


@pytest.mark.asyncio
async def test_lookup_still_returns_record_when_parcel_fails() -> None:
    """If parcel query fails but zoning succeeds, return partial record."""
    provider = ClarkCountyNVProvider()

    async def fake_get(url: str, params: dict | None = None):
        if "LandApp" in url:
            raise Exception("ArcGIS timeout")
        if "MapServer/7" in url:
            return _arcgis_response([_lv_zoning_feature()])
        return _arcgis_response([])

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=fake_get)

    with patch("plotlot.property.clark_county_nv.httpx.AsyncClient", return_value=mock_client):
        record = await provider.lookup("2975 Montessouri St", "Clark", lat=_LAT, lng=_LNG)

    assert record is not None
    assert record.zoning_code == "R-E"
    assert record.folio == ""  # parcel failed — no APN
    assert record.lot_size_sqft == 0.0


# ---------------------------------------------------------------------------
# Provider registration test
# ---------------------------------------------------------------------------


def test_clark_county_registered_in_property_package() -> None:
    """Verify 'clark' maps to ClarkCountyNVProvider in the registry."""
    from plotlot.property.registry import get_provider

    provider = get_provider("Clark")
    assert provider is not None
    assert isinstance(provider, ClarkCountyNVProvider)


def test_clark_lowercase_also_resolves() -> None:
    """Registry lookup is case-insensitive."""
    from plotlot.property.registry import get_provider

    provider = get_provider("clark")
    assert isinstance(provider, ClarkCountyNVProvider)
