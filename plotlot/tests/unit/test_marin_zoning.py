"""Unit tests for the Marin per-city zoning resolver (HTTP mocked)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from plotlot.core.types import PropertyRecord
from plotlot.property.california import CaliforniaProvider
from plotlot.property import marin_zoning
from plotlot.property.marin_zoning import _service_candidates, resolve_marin_zone


class TestServiceCandidates:
    def test_simple_city(self):
        assert _service_candidates("Sausalito") == [
            "Zoning_of_Sausalito",
            "Zoning_of_Unincorporated_Marin_County",
        ]

    def test_composite_cdp_splits_into_towns(self):
        # "Belvedere Tiburon" is two separate towns — the real parcel is in Tiburon.
        cands = _service_candidates("Belvedere Tiburon")
        assert "Zoning_of_Tiburon" in cands
        assert "Zoning_of_Belvedere" in cands
        assert cands[-1] == "Zoning_of_Unincorporated_Marin_County"

    def test_multiword_city_uses_full_name_first(self):
        assert _service_candidates("Mill Valley")[0] == "Zoning_of_Mill_Valley"

    def test_strips_county_suffix(self):
        cands = _service_candidates("Marin County")
        assert "Zoning_of_Marin_County" not in cands  # " County" suffix stripped
        assert cands[-1] == "Zoning_of_Unincorporated_Marin_County"

    def test_empty_municipality_falls_back_to_unincorporated(self):
        assert _service_candidates("") == ["Zoning_of_Unincorporated_Marin_County"]


def _mock_client(layers_json: dict, query_json: dict) -> MagicMock:
    """An httpx.AsyncClient stand-in: returns layers_json for FeatureServer
    metadata GETs and query_json for /<id>/query GETs."""

    def get(url, params=None):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = query_json if url.endswith("/query") else layers_json
        return resp

    client = AsyncMock()
    client.get = AsyncMock(side_effect=get)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


@pytest.fixture(autouse=True)
def _clear_layer_cache():
    marin_zoning._layer_id_cache.clear()
    yield
    marin_zoning._layer_id_cache.clear()


class TestResolveMarinZone:
    @pytest.mark.asyncio
    async def test_returns_zone_and_description(self):
        layers = {"layers": [{"id": 124, "name": "Zoning of Tiburon"}]}
        query = {
            "features": [
                {"attributes": {"Zoning": "RO-2", "ZoningDescription": "Residential Open"}}
            ]
        }
        client = _mock_client(layers, query)
        with patch("plotlot.property.marin_zoning.httpx.AsyncClient", return_value=client):
            code, desc = await resolve_marin_zone("Tiburon", 37.8777, -122.4475)
        assert code == "RO-2"
        assert desc == "Residential Open"

    @pytest.mark.asyncio
    async def test_empty_when_point_outside_all_polygons(self):
        layers = {"layers": [{"id": 0, "name": "z"}]}
        query: dict = {"features": []}  # point not in any polygon
        client = _mock_client(layers, query)
        with patch("plotlot.property.marin_zoning.httpx.AsyncClient", return_value=client):
            code, desc = await resolve_marin_zone("Sausalito", 0.0, 0.0)
        assert code == ""
        assert desc == ""

    @pytest.mark.asyncio
    async def test_network_failure_degrades_to_empty(self):
        client = AsyncMock()
        client.get = AsyncMock(side_effect=Exception("boom"))
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        with patch("plotlot.property.marin_zoning.httpx.AsyncClient", return_value=client):
            code, desc = await resolve_marin_zone("Tiburon", 37.8, -122.4)
        assert (code, desc) == ("", "")


class TestProviderEnrichment:
    @pytest.mark.asyncio
    async def test_enriches_marin_parcel_with_empty_zoning(self):
        rec = PropertyRecord(folio="1", address="a", county="Marin", municipality="Sausalito")
        with patch(
            "plotlot.property.marin_zoning.resolve_marin_zone",
            new=AsyncMock(return_value=("R-2-2.5", "")),
        ):
            await CaliforniaProvider._enrich_marin_zoning(rec, "Marin", 37.85, -122.48)
        assert rec.zoning_code == "R-2-2.5"

    @pytest.mark.asyncio
    async def test_skips_when_zoning_already_present(self):
        rec = PropertyRecord(folio="1", address="a", county="Marin", zoning_code="R-1")
        with patch(
            "plotlot.property.marin_zoning.resolve_marin_zone", new=AsyncMock()
        ) as mock_resolve:
            await CaliforniaProvider._enrich_marin_zoning(rec, "Marin", 37.85, -122.48)
        mock_resolve.assert_not_called()
        assert rec.zoning_code == "R-1"

    @pytest.mark.asyncio
    async def test_skips_for_non_marin_county(self):
        rec = PropertyRecord(folio="1", address="a", county="Sonoma")
        with patch(
            "plotlot.property.marin_zoning.resolve_marin_zone", new=AsyncMock()
        ) as mock_resolve:
            await CaliforniaProvider._enrich_marin_zoning(rec, "Sonoma", 38.4, -122.7)
        mock_resolve.assert_not_called()
        assert rec.zoning_code == ""
