"""Tests for NorCal Municode auto-discovery."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from plotlot.ingestion.discovery import (
    NORCAL_METROS,
    NORCAL_METROS_KEYS,
    _make_key,
    clear_cache,
    discover_ca,
    get_all_municode_configs,
)
from plotlot.core.types import MunicodeConfig


# ---------------------------------------------------------------------------
# NORCAL_METROS data structure
# ---------------------------------------------------------------------------


class TestNorCalMetros:
    def test_has_six_counties(self):
        assert "santa_clara" in NORCAL_METROS
        assert "san_francisco" in NORCAL_METROS
        assert "alameda" in NORCAL_METROS
        assert "san_mateo" in NORCAL_METROS
        assert "contra_costa" in NORCAL_METROS
        assert "sacramento" in NORCAL_METROS

    def test_santa_clara_includes_key_cities(self):
        sc = NORCAL_METROS["santa_clara"]
        assert "San Jose" in sc
        assert "Palo Alto" in sc
        assert "Sunnyvale" in sc
        assert "Mountain View" in sc
        assert "Cupertino" in sc

    def test_san_francisco_county_has_sf(self):
        assert "San Francisco" in NORCAL_METROS["san_francisco"]

    def test_alameda_includes_key_cities(self):
        al = NORCAL_METROS["alameda"]
        assert "Oakland" in al
        assert "Berkeley" in al
        assert "Fremont" in al

    def test_sacramento_includes_key_cities(self):
        sac = NORCAL_METROS["sacramento"]
        assert "Sacramento" in sac
        assert "Elk Grove" in sac
        assert "Folsom" in sac

    def test_total_municipalities_above_threshold(self):
        total = sum(len(v) for v in NORCAL_METROS.values())
        assert total >= 50  # 57 cities defined

    def test_keys_are_lowercase_underscored(self):
        for key in NORCAL_METROS_KEYS:
            assert key == key.lower()
            assert " " not in key

    def test_keys_contain_expected_cities(self):
        assert "san_jose" in NORCAL_METROS_KEYS
        assert "palo_alto" in NORCAL_METROS_KEYS
        assert "oakland" in NORCAL_METROS_KEYS
        assert "san_francisco" in NORCAL_METROS_KEYS
        assert "sacramento" in NORCAL_METROS_KEYS
        assert "elk_grove" in NORCAL_METROS_KEYS
        assert "redwood_city" in NORCAL_METROS_KEYS
        assert "concord" in NORCAL_METROS_KEYS

    def test_filter_by_county(self):
        """Can extract keys for a single county."""
        sc_keys = {_make_key(n) for n in NORCAL_METROS["santa_clara"]}
        assert "palo_alto" in sc_keys
        assert "oakland" not in sc_keys  # Alameda county


# ---------------------------------------------------------------------------
# discover_ca() async discovery with mocked HTTP
# ---------------------------------------------------------------------------


def _mock_ca_clients():
    return [
        {"ClientID": 8888, "ClientName": "San Jose"},
        {"ClientID": 9101, "ClientName": "City of Palo Alto"},
        {"ClientID": 7777, "ClientName": "Oakland"},
        {"ClientID": 6543, "ClientName": "Los Angeles"},  # not in target list
    ]


def _mock_products():
    return [
        {
            "ProductID": 55001,
            "ProductName": "Municipal Code",
            "ContentType": {"Id": "CODES"},
        }
    ]


def _mock_job():
    return {"Id": 600001}


def _mock_root_toc():
    return [
        {"Id": "CH1", "Heading": "Chapter 1 - General", "HasChildren": True},
        {"Id": "T17_ZO", "Heading": "Title 17 - ZONING", "HasChildren": True},
    ]


def _mock_zoning_children():
    return [
        {"Id": "SEC1", "Heading": "Sec. 1. Definitions", "HasChildren": False},
        {"Id": "SEC2", "Heading": "Sec. 2. Districts", "HasChildren": True},
    ]


class TestDiscoverCA:
    @pytest.mark.asyncio
    async def test_discover_ca_finds_san_jose(self):
        async def mock_get(url, params=None, headers=None):
            request = httpx.Request("GET", url)
            if "Clients/stateAbbr" in url:
                return httpx.Response(200, json=_mock_ca_clients(), request=request)
            elif "Products/clientId" in url:
                return httpx.Response(200, json=_mock_products(), request=request)
            elif "Jobs/latest" in url:
                return httpx.Response(200, json=_mock_job(), request=request)
            elif "codesToc/children" in url:
                if params and "nodeId" in (params or {}):
                    return httpx.Response(200, json=_mock_zoning_children(), request=request)
                return httpx.Response(200, json=_mock_root_toc(), request=request)
            return httpx.Response(404, request=request)

        with patch("plotlot.ingestion.discovery.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            configs = await discover_ca(max_concurrent=10)

        assert len(configs) > 0
        assert any("san_jose" in k for k in configs)

    @pytest.mark.asyncio
    async def test_discover_ca_excludes_non_target_cities(self):
        """Los Angeles is not in NORCAL_METROS — should not appear in results."""

        async def mock_get(url, params=None, headers=None):
            request = httpx.Request("GET", url)
            if "Clients/stateAbbr" in url:
                return httpx.Response(200, json=_mock_ca_clients(), request=request)
            elif "Products/clientId" in url:
                return httpx.Response(200, json=_mock_products(), request=request)
            elif "Jobs/latest" in url:
                return httpx.Response(200, json=_mock_job(), request=request)
            elif "codesToc/children" in url:
                if params and "nodeId" in (params or {}):
                    return httpx.Response(200, json=_mock_zoning_children(), request=request)
                return httpx.Response(200, json=_mock_root_toc(), request=request)
            return httpx.Response(404, request=request)

        with patch("plotlot.ingestion.discovery.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            configs = await discover_ca(max_concurrent=10)

        assert "los_angeles" not in configs

    @pytest.mark.asyncio
    async def test_discover_ca_empty_on_api_failure(self):
        async def mock_get(url, params=None, headers=None):
            request = httpx.Request("GET", url)
            return httpx.Response(500, request=request)

        with patch("plotlot.ingestion.discovery.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            configs = await discover_ca()

        assert configs == {}


# ---------------------------------------------------------------------------
# get_all_municode_configs() now includes CA
# ---------------------------------------------------------------------------


class TestGetAllConfigsIncludesCA:
    @pytest.fixture(autouse=True)
    def _clear(self):
        clear_cache()
        yield
        clear_cache()

    @pytest.mark.asyncio
    async def test_combined_includes_ca(self):
        async def mock_empty(*a, **kw):
            return {}

        async def mock_ca(*a, **kw):
            return {
                "san_jose": MunicodeConfig(
                    municipality="San Jose",
                    county="santa_clara",
                    client_id=8888,
                    product_id=55001,
                    job_id=600001,
                    zoning_node_id="T17_ZO",
                )
            }

        with (
            patch("plotlot.ingestion.discovery.discover_all", side_effect=mock_empty),
            patch("plotlot.ingestion.discovery.discover_nc", side_effect=mock_empty),
            patch("plotlot.ingestion.discovery.discover_tx", side_effect=mock_empty),
            patch("plotlot.ingestion.discovery.discover_ga", side_effect=mock_empty),
            patch("plotlot.ingestion.discovery.discover_sc", side_effect=mock_empty),
            patch("plotlot.ingestion.discovery.discover_ca", side_effect=mock_ca),
            patch(
                "plotlot.ingestion.discovery.discover_county_authorities",
                side_effect=mock_empty,
            ),
        ):
            configs = await get_all_municode_configs()

        assert "san_jose" in configs
        cfg = configs["san_jose"]
        assert cfg.municipality == "San Jose"
        assert cfg.county == "santa_clara"
        assert cfg.client_id == 8888
