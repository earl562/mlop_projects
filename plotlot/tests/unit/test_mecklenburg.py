"""Tests for the Mecklenburg County PropertyProvider.

All external API calls are mocked — no real HTTP requests are made.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import partial
from typing import Final
from unittest.mock import patch

import httpx
import pytest
from pydantic import JsonValue, ValidationError

from plotlot.core.types import PropertyRecord
from plotlot.property.mecklenburg import (
    MecklenburgProvider,
    MECKLENBURG_PARCEL_URL,
    MECKLENBURG_OWNERSHIP_URL,
    MECKLENBURG_ZONING_URL,
    _Attributes,
)
from plotlot.property.registry import get_provider, registered_counties


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_FEATURE: Final[dict[str, JsonValue]] = {
    "attributes": {
        "pid": "12345678",
        "parcelid": "12345678",
        "address": "600 E 4TH ST CHARLOTTE NC",
        "loccity": "CHARLOTTE",
        "ownrlstnme": "SMITH",
        "ownrfrstnme": "JOHN",
        "lusecode": "R100",
        "landuse_description": "Single Family",
        "legalacres": 2.0,
        "totalvalue": 350000.0,
        "totmarkval": 375000.0,
        "yearbuilt": 1998,
        "heatedarea": 2200.0,
    }
}


SAMPLE_FEATURE_ALT_FIELDS: Final[dict[str, JsonValue]] = {
    "attributes": {
        "PARCEL_ID": "ALT-9999",
        "ADDRESS": "100 MAIN ST",
        "JURIS": "Huntersville",
        "OWNER": "DOE JANE",
        "ZONING": "MX-2",
        "ZONE_DESC": "",
        "LU_CODE": "200",
        "LU_DESC": "Mixed Use",
        "LAND_AREA": 4000.0,
        "ASSESSED_VALUE": 200000.0,
        "TOTAL_VALUE": 0,
        "MARKET_VALUE": 0,
        "YEAR_BUILT": 2005,
        "HEATED_AREA": 1800.0,
    }
}


def _make_response(features: list[dict[str, JsonValue]]) -> httpx.Response:
    return httpx.Response(200, json={"features": features})


def _make_current_response(request: httpx.Request) -> httpx.Response:
    url = str(request.url.copy_with(query=None))
    if url == MECKLENBURG_OWNERSHIP_URL:
        return _make_response(
            [
                {
                    "attributes": {
                        "pid": "12345678",
                        "camapid": "12345678",
                        "municipality_desc": "CHARLOTTE",
                        "situsaddress1": "600 E 4TH ST CHARLOTTE NC",
                    }
                }
            ]
        )
    if url == MECKLENBURG_ZONING_URL:
        return _make_response([{"attributes": {"pid": "12345678", "zone_class": "N1-A"}}])
    return _make_response([SAMPLE_FEATURE])


@contextmanager
def _mock_api(
    respond: Callable[[httpx.Request], httpx.Response] = _make_current_response,
) -> Iterator[None]:
    client_factory = partial(httpx.AsyncClient, transport=httpx.MockTransport(respond))
    with patch("plotlot.property.mecklenburg.httpx.AsyncClient", new=client_factory):
        yield


# ---------------------------------------------------------------------------
# Provider registration
# ---------------------------------------------------------------------------


class TestMecklenburgRegistration:
    def test_registered_in_registry(self):
        """Mecklenburg provider should be registered after package import."""
        assert "mecklenburg" in registered_counties()

    def test_get_provider_returns_mecklenburg(self):
        provider = get_provider("mecklenburg")
        assert provider is not None
        assert isinstance(provider, MecklenburgProvider)

    def test_get_provider_case_insensitive(self):
        assert get_provider("Mecklenburg") is not None
        assert get_provider("MECKLENBURG") is not None


# ---------------------------------------------------------------------------
# Spatial query
# ---------------------------------------------------------------------------


class TestSpatialQuery:
    @pytest.mark.asyncio
    async def test_spatial_query_returns_property_record(self):
        provider = MecklenburgProvider()

        with _mock_api():
            result = await provider.lookup(
                "600 E 4th St, Charlotte, NC",
                "Mecklenburg",
                lat=35.227,
                lng=-80.843,
            )

        assert result is not None
        assert isinstance(result, PropertyRecord)
        assert result.folio == "12345678"
        assert result.address == "600 E 4TH ST CHARLOTTE NC"
        assert result.municipality == "CHARLOTTE"
        assert result.county == "Mecklenburg"
        assert result.owner == "JOHN SMITH"
        assert result.zoning_code == "N1-A"
        assert result.zoning_description == ""
        assert result.year_built == 1998
        assert result.building_area_sqft == 2200.0

    @pytest.mark.asyncio
    async def test_spatial_query_empty_returns_none_then_address_fallback(self):
        """When spatial query returns no features, falls back to address query."""
        provider = MecklenburgProvider()
        call_urls: list[str] = []

        def respond(request: httpx.Request) -> httpx.Response:
            call_urls.append(str(request.url.copy_with(query=None)))
            # First call (spatial) returns empty, second (address) returns data
            if len(call_urls) == 1:
                return _make_response([])
            return _make_current_response(request)

        with _mock_api(respond):
            result = await provider.lookup(
                "600 E 4th St, Charlotte, NC",
                "Mecklenburg",
                lat=35.227,
                lng=-80.843,
            )

        assert result is not None
        assert result.folio == "12345678"
        assert call_urls == [
            MECKLENBURG_PARCEL_URL,
            MECKLENBURG_PARCEL_URL,
            MECKLENBURG_OWNERSHIP_URL,
            MECKLENBURG_ZONING_URL,
        ]


# ---------------------------------------------------------------------------
# Address query
# ---------------------------------------------------------------------------


class TestAddressQuery:
    @pytest.mark.asyncio
    async def test_address_query_returns_property_record(self):
        """When no lat/lng provided, goes straight to address query."""
        provider = MecklenburgProvider()

        with _mock_api():
            result = await provider.lookup(
                "600 E 4th St, Charlotte, NC",
                "Mecklenburg",
            )

        assert result is not None
        assert result.folio == "12345678"

    @pytest.mark.asyncio
    async def test_address_query_empty_returns_none(self):
        provider = MecklenburgProvider()

        with _mock_api(lambda request: _make_response([])):
            result = await provider.lookup(
                "999 Nonexistent St, Charlotte, NC",
                "Mecklenburg",
            )

        assert result is None


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_api_error_returns_none(self):
        """HTTP errors are caught and None is returned."""
        provider = MecklenburgProvider()

        with _mock_api(lambda request: httpx.Response(500)):
            result = await provider.lookup(
                "600 E 4th St, Charlotte, NC",
                "Mecklenburg",
                lat=35.227,
                lng=-80.843,
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_timeout_returns_none(self):
        """Timeout errors are caught gracefully."""
        provider = MecklenburgProvider()

        def respond(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("Connection timed out", request=request)

        with _mock_api(respond):
            result = await provider.lookup(
                "600 E 4th St, Charlotte, NC",
                "Mecklenburg",
                lat=35.227,
                lng=-80.843,
            )

        assert result is None


# ---------------------------------------------------------------------------
# _parse_feature field extraction
# ---------------------------------------------------------------------------


class TestParseFeature:
    def test_parses_primary_field_names(self):
        provider = MecklenburgProvider()
        record = provider._parse_feature(_Attributes.model_validate(SAMPLE_FEATURE["attributes"]))

        assert record.folio == "12345678"
        assert record.address == "600 E 4TH ST CHARLOTTE NC"
        assert record.municipality == ""
        assert record.county == "Mecklenburg"
        assert record.owner == "JOHN SMITH"
        assert record.zoning_code == ""
        assert record.zoning_description == ""
        assert record.land_use_code == "R100"
        assert record.land_use_description == "Single Family"
        assert record.lot_size_sqft == 87120.0
        assert record.lot_size_source == "assessor"
        assert record.assessed_value == 350000.0
        assert record.market_value == 375000.0
        assert record.year_built == 1998
        assert record.building_area_sqft == 2200.0

    def test_unverified_alternate_field_names_cannot_establish_identity(self):
        # Given the obsolete fixture's aliases, absent from the current county schema.
        attrs = SAMPLE_FEATURE_ALT_FIELDS["attributes"]
        # When parsing that incompatible payload, then identity is not invented.
        with pytest.raises(ValidationError):
            _Attributes.model_validate(attrs)

    def test_handles_empty_attributes(self):
        provider = MecklenburgProvider()
        # Given no county identity fields.
        attrs: dict[str, JsonValue] = {}
        # When parsing the empty boundary payload, then no blank record is created.
        with pytest.raises(ValidationError):
            provider._parse_feature(_Attributes.model_validate(attrs))

    def test_large_ambiguous_area_does_not_invent_units(self):
        # Given ambiguous area fields without explicit legal or GIS acres.
        provider = MecklenburgProvider()
        attrs = {"pid": "12345678", "SHAPE_Area": 75000.0, "totalac": 75000.0}
        # When parsing the current parcel, then magnitude supplies no area evidence.
        record = provider._parse_feature(_Attributes.model_validate(attrs))
        assert (record.lot_size_sqft, record.lot_size_source) == (0.0, "")

    def test_small_gis_acres_have_explicit_geometry_provenance(self):
        # Given measured GIS acreage without assessor acreage.
        provider = MecklenburgProvider()
        attrs = {"pid": "12345678", "gisacres": 0.01}
        # When parsing the parcel, then acres use an explicit square-foot conversion.
        record = provider._parse_feature(_Attributes.model_validate(attrs))
        assert record.lot_size_sqft == pytest.approx(435.6)
        assert record.lot_size_source == "geometry"
