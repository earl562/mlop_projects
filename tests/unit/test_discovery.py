"""Tests for Municode auto-discovery module."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from plotlot.core.types import MunicodeConfig
from plotlot.ingestion.discovery import (
    SOUTH_FLORIDA_MUNICIPALITIES,
    _make_key,
    _match_client,
    _normalize,
    _search_toc_for_zoning,
    clear_cache,
    discover_all,
    get_municode_configs,
)


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------

class TestMakeKey:
    def test_simple_name(self):
        assert _make_key("Fort Lauderdale") == "fort_lauderdale"

    def test_hyphenated_name(self):
        assert _make_key("Miami-Dade") == "miami_dade"

    def test_apostrophe(self):
        assert _make_key("Opa-locka") == "opa_locka"

    def test_multi_word(self):
        assert _make_key("North Miami Beach") == "north_miami_beach"

    def test_extra_spaces(self):
        assert _make_key("  Palm Beach  ") == "palm_beach"

    def test_village_suffix(self):
        assert _make_key("Indian Creek Village") == "indian_creek_village"


class TestNormalize:
    def test_basic(self):
        assert _normalize("Fort Lauderdale") == "fort lauderdale"

    def test_hyphen_removal(self):
        assert _normalize("Miami-Dade") == "miami dade"

    def test_village_removal(self):
        assert _normalize("Indian Creek Village") == "indian creek"


class TestMatchClient:
    def test_exact_match(self):
        clients = [
            {"ClientID": 100, "ClientName": "Fort Lauderdale"},
            {"ClientID": 200, "ClientName": "Miami"},
        ]
        result = _match_client("Fort Lauderdale", clients)
        assert result is not None
        assert result["ClientID"] == 100

    def test_no_match(self):
        clients = [{"ClientID": 100, "ClientName": "Orlando"}]
        result = _match_client("Fort Lauderdale", clients)
        assert result is None

    def test_name_map_alias(self):
        clients = [
            {"ClientID": 300, "ClientName": "Indian Creek"},
        ]
        result = _match_client("Indian Creek Village", clients)
        assert result is not None
        assert result["ClientID"] == 300

    def test_case_insensitive(self):
        clients = [{"ClientID": 400, "ClientName": "CORAL GABLES"}]
        result = _match_client("Coral Gables", clients)
        assert result is not None

    def test_substring_match_with_length_guard(self):
        clients = [
            {"ClientID": 500, "ClientName": "Miami Beach"},
        ]
        result = _match_client("Miami", clients)
        assert result is None


class TestSearchTocForZoning:
    def test_finds_zoning_chapter(self):
        toc = [
            {"Heading": "Chapter 1 - General", "Id": "CH1"},
            {"Heading": "Chapter 33 - ZONING", "Id": "CH33"},
            {"Heading": "Chapter 50 - Traffic", "Id": "CH50"},
        ]
        matches = _search_toc_for_zoning(toc)
        assert len(matches) == 1
        assert matches[0]["Id"] == "CH33"

    def test_finds_land_development(self):
        toc = [
            {"Heading": "Unified Land Development Code", "Id": "ULDC"},
        ]
        matches = _search_toc_for_zoning(toc)
        assert len(matches) == 1

    def test_no_match(self):
        toc = [
            {"Heading": "Chapter 1 - General", "Id": "CH1"},
            {"Heading": "Chapter 2 - Admin", "Id": "CH2"},
        ]
        matches = _search_toc_for_zoning(toc)
        assert len(matches) == 0

    def test_empty_toc(self):
        assert _search_toc_for_zoning([]) == []

    def test_uldc_keyword(self):
        toc = [{"Heading": "ULDC - Regulations", "Title": "", "Id": "ULDC1"}]
        matches = _search_toc_for_zoning(toc)
        assert len(matches) == 1


# ---------------------------------------------------------------------------
# Integration tests with mocked HTTP
# ---------------------------------------------------------------------------

def _mock_fl_clients():
    return [
        {"ClientID": 2247, "ClientName": "Fort Lauderdale"},
        {"ClientID": 11719, "ClientName": "Miami-Dade County"},
        {"ClientID": 9999, "ClientName": "Coral Gables"},
    ]


def _mock_products(client_id: int):
    return [
        {
            "ProductID": 13463,
            "ProductName": "Code of Ordinances",
            "ContentType": {"Id": "CODES"},
        }
    ]


def _mock_job():
    return {"Id": 482747}


def _mock_root_toc():
    return [
        {"Id": "CH1", "Heading": "Chapter 1 - General", "HasChildren": True},
        {"Id": "CH47_ZONING", "Heading": "Chapter 47 - ZONING", "HasChildren": True},
    ]


def _mock_zoning_children():
    return [
        {"Id": "SEC1", "Heading": "Sec. 47-1. Definitions", "HasChildren": False},
        {"Id": "SEC2", "Heading": "Sec. 47-2. Districts", "HasChildren": True},
    ]


class TestDiscoverAll:
    @pytest.mark.asyncio
    async def test_discover_single_municipality(self):
        call_count = {"n": 0}

        async def mock_get(url, params=None, headers=None):
            call_count["n"] += 1
            request = httpx.Request("GET", url)

            if "Clients/stateAbbr" in url:
                return httpx.Response(200, json=_mock_fl_clients(), request=request)
            elif "Products/clientId" in url:
                return httpx.Response(200, json=_mock_products(2247), request=request)
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

            configs = await discover_all(max_concurrent=10)

        assert len(configs) > 0
        assert any("fort_lauderdale" in k for k in configs)

    @pytest.mark.asyncio
    async def test_discover_empty_on_api_failure(self):
        async def mock_get(url, params=None, headers=None):
            request = httpx.Request("GET", url)
            return httpx.Response(500, request=request)

        with patch("plotlot.ingestion.discovery.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            configs = await discover_all()

        assert configs == {}


class TestGetMunicodeConfigs:
    @pytest.mark.asyncio
    async def test_caches_results(self):
        call_count = {"n": 0}

        async def mock_discover(*args, **kwargs):
            call_count["n"] += 1
            return {"test_city": MunicodeConfig(
                municipality="Test City", county="test",
                client_id=1, product_id=2, job_id=3, zoning_node_id="NODE1",
            )}

        with patch("plotlot.ingestion.discovery.discover_all", side_effect=mock_discover):
            result1 = await get_municode_configs()
            result2 = await get_municode_configs()

        assert call_count["n"] == 1
        assert result1 is result2
        assert "test_city" in result1

    @pytest.mark.asyncio
    async def test_force_refresh(self):
        call_count = {"n": 0}

        async def mock_discover(*args, **kwargs):
            call_count["n"] += 1
            return {"test_city": MunicodeConfig(
                municipality="Test City", county="test",
                client_id=1, product_id=2, job_id=3, zoning_node_id="NODE1",
            )}

        with patch("plotlot.ingestion.discovery.discover_all", side_effect=mock_discover):
            await get_municode_configs()
            await get_municode_configs(force_refresh=True)

        assert call_count["n"] == 2

    @pytest.mark.asyncio
    async def test_fallback_on_discovery_failure(self):
        async def mock_discover(*args, **kwargs):
            raise ConnectionError("API down")

        with patch("plotlot.ingestion.discovery.discover_all", side_effect=mock_discover):
            configs = await get_municode_configs()

        assert "miami_dade" in configs
        assert "fort_lauderdale" in configs

    @pytest.mark.asyncio
    async def test_fallback_on_empty_discovery(self):
        async def mock_discover(*args, **kwargs):
            return {}

        with patch("plotlot.ingestion.discovery.discover_all", side_effect=mock_discover):
            configs = await get_municode_configs()

        assert "miami_dade" in configs
        assert "fort_lauderdale" in configs

    @pytest.mark.asyncio
    async def test_merges_fallback_configs(self):
        async def mock_discover(*args, **kwargs):
            return {"coral_gables": MunicodeConfig(
                municipality="Coral Gables", county="miami_dade",
                client_id=100, product_id=200, job_id=300, zoning_node_id="CG_ZO",
            )}

        with patch("plotlot.ingestion.discovery.discover_all", side_effect=mock_discover):
            configs = await get_municode_configs()

        assert "coral_gables" in configs
        assert "miami_dade" in configs
        assert "fort_lauderdale" in configs


class TestClearCache:
    @pytest.mark.asyncio
    async def test_clear_cache_forces_rediscovery(self):
        call_count = {"n": 0}

        async def mock_discover(*args, **kwargs):
            call_count["n"] += 1
            return {"test": MunicodeConfig(
                municipality="Test", county="test",
                client_id=1, product_id=2, job_id=3, zoning_node_id="N",
            )}

        with patch("plotlot.ingestion.discovery.discover_all", side_effect=mock_discover):
            await get_municode_configs()
            clear_cache()
            await get_municode_configs()

        assert call_count["n"] == 2


class TestSouthFloridaMunicipalities:
    def test_has_three_counties(self):
        assert "miami_dade" in SOUTH_FLORIDA_MUNICIPALITIES
        assert "broward" in SOUTH_FLORIDA_MUNICIPALITIES
        assert "palm_beach" in SOUTH_FLORIDA_MUNICIPALITIES

    def test_miami_dade_count(self):
        assert len(SOUTH_FLORIDA_MUNICIPALITIES["miami_dade"]) == 32

    def test_broward_count(self):
        assert len(SOUTH_FLORIDA_MUNICIPALITIES["broward"]) == 25

    def test_palm_beach_count(self):
        assert len(SOUTH_FLORIDA_MUNICIPALITIES["palm_beach"]) == 36

    def test_total_municipalities(self):
        total = sum(len(v) for v in SOUTH_FLORIDA_MUNICIPALITIES.values())
        assert total == 93
