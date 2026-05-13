"""Tests for NC Charlotte metro Municode auto-discovery."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from plotlot.core.types import MunicodeConfig, _NC_FALLBACK_CONFIGS, NC_MUNICODE_CONFIGS
from plotlot.ingestion.discovery import (
    NC_CHARLOTTE_METRO,
    NC_CHARLOTTE_METRO_KEYS,
    _make_key,
    clear_cache,
    discover_nc,
    get_all_municode_configs,
    get_municode_configs,
    get_nc_municode_configs,
)


# ---------------------------------------------------------------------------
# NC Charlotte metro municipality list
# ---------------------------------------------------------------------------


class TestNCCharlotteMetro:
    def test_has_four_counties(self):
        assert "mecklenburg" in NC_CHARLOTTE_METRO
        assert "union" in NC_CHARLOTTE_METRO
        assert "cabarrus" in NC_CHARLOTTE_METRO
        assert "iredell" in NC_CHARLOTTE_METRO

    def test_mecklenburg_includes_charlotte(self):
        assert "Charlotte" in NC_CHARLOTTE_METRO["mecklenburg"]

    def test_total_municipalities(self):
        total = sum(len(v) for v in NC_CHARLOTTE_METRO.values())
        assert total == 18

    def test_charlotte_metro_keys_are_lowercase(self):
        for key in NC_CHARLOTTE_METRO_KEYS:
            assert key == key.lower()
            assert " " not in key  # underscores, not spaces

    def test_charlotte_metro_keys_contains_expected(self):
        assert "charlotte" in NC_CHARLOTTE_METRO_KEYS
        assert "huntersville" in NC_CHARLOTTE_METRO_KEYS
        assert "cornelius" in NC_CHARLOTTE_METRO_KEYS
        assert "concord" in NC_CHARLOTTE_METRO_KEYS
        assert "mooresville" in NC_CHARLOTTE_METRO_KEYS
        assert "indian_trail" in NC_CHARLOTTE_METRO_KEYS
        assert "mint_hill" in NC_CHARLOTTE_METRO_KEYS

    def test_filter_by_county(self):
        """Can filter NC metro keys to just Mecklenburg."""
        meck_keys = {_make_key(n) for n in NC_CHARLOTTE_METRO["mecklenburg"]}
        assert "charlotte" in meck_keys
        assert "concord" not in meck_keys  # Cabarrus county


# ---------------------------------------------------------------------------
# Static NC configs
# ---------------------------------------------------------------------------


class TestNCStaticConfigs:
    def test_nc_fallback_configs_not_empty(self):
        assert len(_NC_FALLBACK_CONFIGS) > 0

    def test_nc_fallback_has_charlotte(self):
        assert "charlotte" in _NC_FALLBACK_CONFIGS

    def test_nc_fallback_has_expected_keys(self):
        expected = {
            "charlotte",
            "huntersville",
            "cornelius",
            "davidson",
            "matthews",
            "mint_hill",
            "pineville",
            "concord",
            "kannapolis",
            "mooresville",
            "monroe",
            "waxhaw",
        }
        assert expected.issubset(set(_NC_FALLBACK_CONFIGS.keys()))

    def test_nc_configs_alias(self):
        """NC_MUNICODE_CONFIGS is the public alias for _NC_FALLBACK_CONFIGS."""
        assert NC_MUNICODE_CONFIGS is _NC_FALLBACK_CONFIGS

    def test_nc_configs_are_municode_config(self):
        for key, cfg in _NC_FALLBACK_CONFIGS.items():
            assert isinstance(cfg, MunicodeConfig)
            assert cfg.municipality != ""
            assert cfg.county != ""
            assert cfg.client_id > 0

    def test_charlotte_config_fields(self):
        cfg = _NC_FALLBACK_CONFIGS["charlotte"]
        assert cfg.municipality == "Charlotte"
        assert cfg.county == "mecklenburg"
        assert cfg.client_id > 0
        assert cfg.product_id > 0
        assert cfg.job_id > 0
        assert cfg.zoning_node_id != ""


# ---------------------------------------------------------------------------
# get_nc_municode_configs() synchronous fallback
# ---------------------------------------------------------------------------


class TestGetNCMunicodeConfigs:
    def test_returns_dict(self):
        configs = get_nc_municode_configs()
        assert isinstance(configs, dict)
        assert len(configs) > 0

    def test_returns_copy(self):
        """Should return a copy, not the mutable original."""
        configs = get_nc_municode_configs()
        configs["fake_city"] = MunicodeConfig(
            municipality="Fake",
            county="fake",
            client_id=0,
            product_id=0,
            job_id=0,
            zoning_node_id="",
        )
        # Original should be unchanged
        assert "fake_city" not in _NC_FALLBACK_CONFIGS

    def test_contains_charlotte(self):
        configs = get_nc_municode_configs()
        assert "charlotte" in configs


# ---------------------------------------------------------------------------
# discover_nc() async discovery with mocked HTTP
# ---------------------------------------------------------------------------


def _mock_nc_clients():
    return [
        {"ClientID": 19970, "ClientName": "Charlotte"},
        {"ClientID": 7619, "ClientName": "Huntersville"},
        {"ClientID": 7475, "ClientName": "Concord"},
        {"ClientID": 9999, "ClientName": "Raleigh"},  # not in Charlotte metro
    ]


def _mock_products():
    return [
        {
            "ProductID": 14045,
            "ProductName": "Code of Ordinances",
            "ContentType": {"Id": "CODES"},
        }
    ]


def _mock_job():
    return {"Id": 489001}


def _mock_root_toc():
    return [
        {"Id": "CH1", "Heading": "Chapter 1 - General", "HasChildren": True},
        {"Id": "APXA_ZO", "Heading": "Appendix A - ZONING ORDINANCE", "HasChildren": True},
    ]


def _mock_zoning_children():
    return [
        {"Id": "SEC1", "Heading": "Sec. 1. Definitions", "HasChildren": False},
        {"Id": "SEC2", "Heading": "Sec. 2. Districts", "HasChildren": True},
    ]


class TestDiscoverNC:
    @pytest.mark.asyncio
    async def test_discover_nc_finds_charlotte(self):
        async def mock_get(url, params=None, headers=None):
            request = httpx.Request("GET", url)

            if "Clients/stateAbbr" in url:
                return httpx.Response(200, json=_mock_nc_clients(), request=request)
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

            configs = await discover_nc(max_concurrent=10)

        assert len(configs) > 0
        assert any("charlotte" in k for k in configs)

    @pytest.mark.asyncio
    async def test_discover_nc_empty_on_api_failure(self):
        async def mock_get(url, params=None, headers=None):
            request = httpx.Request("GET", url)
            return httpx.Response(500, request=request)

        with patch("plotlot.ingestion.discovery.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            configs = await discover_nc()

        assert configs == {}


# ---------------------------------------------------------------------------
# Combined FL + NC config retrieval
# ---------------------------------------------------------------------------


class TestGetAllMunicodeConfigs:
    @pytest.fixture(autouse=True)
    def _clear(self):
        clear_cache()
        yield
        clear_cache()

    @pytest.mark.asyncio
    async def test_combined_includes_fl_and_nc(self):
        async def mock_fl(*a, **kw):
            return {
                "fort_lauderdale": MunicodeConfig(
                    municipality="Fort Lauderdale",
                    county="broward",
                    client_id=2247,
                    product_id=13463,
                    job_id=482747,
                    zoning_node_id="FL_ZO",
                )
            }

        async def mock_nc(*a, **kw):
            return {
                "charlotte": MunicodeConfig(
                    municipality="Charlotte",
                    county="mecklenburg",
                    client_id=19970,
                    product_id=14045,
                    job_id=489001,
                    zoning_node_id="NC_ZO",
                )
            }

        with (
            patch("plotlot.ingestion.discovery.discover_all", side_effect=mock_fl),
            patch("plotlot.ingestion.discovery.discover_nc", side_effect=mock_nc),
        ):
            configs = await get_all_municode_configs()

        assert "fort_lauderdale" in configs
        assert "charlotte" in configs

    @pytest.mark.asyncio
    async def test_fallback_on_combined_failure(self):
        async def mock_fail(*a, **kw):
            raise ConnectionError("API down")

        with (
            patch("plotlot.ingestion.discovery.discover_all", side_effect=mock_fail),
            patch("plotlot.ingestion.discovery.discover_nc", side_effect=mock_fail),
        ):
            configs = await get_all_municode_configs()

        # Should have both FL and NC fallbacks
        assert "miami_dade" in configs
        assert "charlotte" in configs

    @pytest.mark.asyncio
    async def test_get_municode_configs_delegates_to_all(self):
        """get_municode_configs() now returns FL + NC combined."""

        async def mock_fl(*a, **kw):
            return {
                "miami_dade": MunicodeConfig(
                    municipality="Miami-Dade",
                    county="miami_dade",
                    client_id=11719,
                    product_id=10620,
                    job_id=483425,
                    zoning_node_id="FL_ZO",
                )
            }

        async def mock_nc(*a, **kw):
            return {
                "charlotte": MunicodeConfig(
                    municipality="Charlotte",
                    county="mecklenburg",
                    client_id=19970,
                    product_id=14045,
                    job_id=489001,
                    zoning_node_id="NC_ZO",
                )
            }

        with (
            patch("plotlot.ingestion.discovery.discover_all", side_effect=mock_fl),
            patch("plotlot.ingestion.discovery.discover_nc", side_effect=mock_nc),
        ):
            configs = await get_municode_configs()

        assert "miami_dade" in configs
        assert "charlotte" in configs
