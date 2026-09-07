"""Unit tests for the Marin authoritative parcel-lot resolver (HTTP mocked)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from plotlot.core.types import PropertyRecord
from plotlot.property.california import CaliforniaProvider
from plotlot.property.marin_lot import resolve_marin_lot_sqft


def _mock_client(query_json: dict, capture: dict | None = None) -> MagicMock:
    def get(url, params=None):
        if capture is not None:
            capture["params"] = params
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = query_json
        return resp

    client = AsyncMock()
    client.get = AsyncMock(side_effect=get)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


class TestResolveMarinLotSqft:
    @pytest.mark.asyncio
    async def test_returns_area_and_strips_apn_dashes(self):
        capture: dict = {}
        client = _mock_client({"features": [{"attributes": {"Shape__Area": 1162.4}}]}, capture)
        with patch("plotlot.property.marin_lot.httpx.AsyncClient", return_value=client):
            lot = await resolve_marin_lot_sqft("065-234-10")
        assert lot == pytest.approx(1162.4)
        # APN queried with non-digits stripped (Parcel field format)
        assert capture["params"]["where"] == "Parcel='06523410'"

    @pytest.mark.asyncio
    async def test_none_on_miss(self):
        client = _mock_client({"features": []})
        with patch("plotlot.property.marin_lot.httpx.AsyncClient", return_value=client):
            assert await resolve_marin_lot_sqft("065-234-10") is None

    @pytest.mark.asyncio
    async def test_none_for_short_apn(self):
        # Too few digits — never even queries (guards against matching the wrong parcel).
        assert await resolve_marin_lot_sqft("12-34") is None

    @pytest.mark.asyncio
    async def test_none_on_network_failure(self):
        client = AsyncMock()
        client.get = AsyncMock(side_effect=Exception("boom"))
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        with patch("plotlot.property.marin_lot.httpx.AsyncClient", return_value=client):
            assert await resolve_marin_lot_sqft("065-234-10") is None

    @pytest.mark.asyncio
    async def test_none_when_area_zero_or_missing(self):
        client = _mock_client({"features": [{"attributes": {"Shape__Area": 0}}]})
        with patch("plotlot.property.marin_lot.httpx.AsyncClient", return_value=client):
            assert await resolve_marin_lot_sqft("065-234-10") is None


class TestEnrichMarinLot:
    @pytest.mark.asyncio
    async def test_overrides_lot_and_marks_assessor(self):
        rec = PropertyRecord(
            folio="065-234-10",
            address="a",
            county="Marin",
            lot_size_sqft=765.0,
            lot_size_source="geometry",
        )
        with patch(
            "plotlot.property.marin_lot.resolve_marin_lot_sqft",
            new=AsyncMock(return_value=1162.4),
        ):
            await CaliforniaProvider._enrich_marin_lot(rec, "Marin")
        assert rec.lot_size_sqft == pytest.approx(1162.4)
        assert rec.lot_size_source == "assessor"

    @pytest.mark.asyncio
    async def test_keeps_estimate_when_resolver_misses(self):
        rec = PropertyRecord(
            folio="065-234-10",
            address="a",
            county="Marin",
            lot_size_sqft=765.0,
            lot_size_source="geometry",
        )
        with patch(
            "plotlot.property.marin_lot.resolve_marin_lot_sqft", new=AsyncMock(return_value=None)
        ):
            await CaliforniaProvider._enrich_marin_lot(rec, "Marin")
        # Unconfirmed estimate preserved, NOT silently upgraded to "assessor".
        assert rec.lot_size_sqft == pytest.approx(765.0)
        assert rec.lot_size_source == "geometry"

    @pytest.mark.asyncio
    async def test_skips_non_marin_county(self):
        rec = PropertyRecord(folio="1", address="a", county="Sonoma", lot_size_sqft=100.0)
        with patch(
            "plotlot.property.marin_lot.resolve_marin_lot_sqft", new=AsyncMock()
        ) as mock_resolve:
            await CaliforniaProvider._enrich_marin_lot(rec, "Sonoma")
        mock_resolve.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_already_assessor(self):
        rec = PropertyRecord(
            folio="1",
            address="a",
            county="Marin",
            lot_size_sqft=7710.0,
            lot_size_source="assessor",
        )
        with patch(
            "plotlot.property.marin_lot.resolve_marin_lot_sqft", new=AsyncMock()
        ) as mock_resolve:
            await CaliforniaProvider._enrich_marin_lot(rec, "Marin")
        mock_resolve.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_no_folio(self):
        rec = PropertyRecord(folio="", address="a", county="Marin", lot_size_sqft=765.0)
        with patch(
            "plotlot.property.marin_lot.resolve_marin_lot_sqft", new=AsyncMock()
        ) as mock_resolve:
            await CaliforniaProvider._enrich_marin_lot(rec, "Marin")
        mock_resolve.assert_not_called()
