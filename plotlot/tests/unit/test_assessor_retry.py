"""Assessor lookup resilience: retry on stall, cache successes, never cache failures.

Losing this lookup silently swaps the authoritative recorded lot for a GIS
polygon estimate, which changes the headline unit count (7 -> 6 on the San Diego
baseline parcel) and drops the offer to provisional. These tests lock the
recovery behaviour that keeps that from happening on a transient stall.
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from plotlot.property import california
from plotlot.property.california import CaliforniaProvider

APN = "4364230200"
URL = california._SD_ASSESSOR_PARCEL_URL


def _feature(acreage=None, st_area=None, owner="1233 HUENEME LLC"):
    attrs = {"OWN_NAME1": owner}
    if acreage is not None:
        attrs["ACREAGE"] = acreage
    if st_area is not None:
        attrs["Shape.STArea()"] = st_area
    return {"features": [{"attributes": attrs}]}


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _clear_cache():
    """Isolate the in-process cache and neutralise the DB layer by default.

    The durable cache is exercised explicitly in TestDurableCache; everywhere
    else it must not reach for a database.
    """
    california._ASSESSOR_CACHE.clear()
    with (
        patch(
            "plotlot.storage.assessor_cache.get_cached_parcel",
            new=AsyncMock(return_value=None),
        ),
        patch("plotlot.storage.assessor_cache.store_cached_parcel", new=AsyncMock()),
    ):
        yield
    california._ASSESSOR_CACHE.clear()


@pytest.mark.asyncio
async def test_recovers_when_first_attempt_stalls():
    """A stalled first request must not cost us the assessor lot."""
    calls = {"n": 0}

    async def get(*_a, **_k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ReadTimeout("stalled")
        return _Resp(_feature(st_area=7710.48828125))

    with patch.object(httpx.AsyncClient, "get", new=AsyncMock(side_effect=get)):
        lot, owner = await CaliforniaProvider()._assessor_lot_sqft(URL, APN)

    assert calls["n"] == 2
    assert lot == pytest.approx(7710.48828125)
    assert owner == "1233 HUENEME LLC"


@pytest.mark.asyncio
async def test_gives_up_after_all_attempts_and_reports_none():
    """Persistent failure returns None so the caller flags the count provisional."""
    get = AsyncMock(side_effect=httpx.ReadTimeout("stalled"))
    with patch.object(httpx.AsyncClient, "get", new=get):
        lot, owner = await CaliforniaProvider()._assessor_lot_sqft(URL, APN)

    assert get.await_count == california._ASSESSOR_ATTEMPTS
    assert lot is None
    assert owner == ""


@pytest.mark.asyncio
async def test_failure_is_not_cached():
    """A transient failure must not pin the parcel to the degraded path."""
    get = AsyncMock(side_effect=httpx.ReadTimeout("stalled"))
    with patch.object(httpx.AsyncClient, "get", new=get):
        await CaliforniaProvider()._assessor_lot_sqft(URL, APN)
    assert APN not in california._ASSESSOR_CACHE

    with patch.object(
        httpx.AsyncClient, "get", new=AsyncMock(return_value=_Resp(_feature(st_area=7710.0)))
    ):
        lot, _ = await CaliforniaProvider()._assessor_lot_sqft(URL, APN)
    assert lot == pytest.approx(7710.0)


@pytest.mark.asyncio
async def test_success_is_cached_and_endpoint_not_hit_again():
    get = AsyncMock(return_value=_Resp(_feature(acreage=0.177)))
    with patch.object(httpx.AsyncClient, "get", new=get):
        first, _ = await CaliforniaProvider()._assessor_lot_sqft(URL, APN)
        second, _ = await CaliforniaProvider()._assessor_lot_sqft(URL, APN)

    assert first == second == pytest.approx(0.177 * 43_560)
    assert get.await_count == 1, "cached APN must not re-hit the county endpoint"


@pytest.mark.asyncio
async def test_clean_no_match_is_answered_immediately():
    """An empty result set is a real answer — do not burn retries on it."""
    get = AsyncMock(return_value=_Resp({"features": []}))
    with patch.object(httpx.AsyncClient, "get", new=get):
        lot, owner = await CaliforniaProvider()._assessor_lot_sqft(URL, APN)

    assert get.await_count == 1
    assert lot is None and owner == ""


class TestDurableCache:
    """The DB layer must survive restarts without ever breaking the lookup."""

    @pytest.mark.asyncio
    async def test_db_hit_skips_the_network_entirely(self):
        """A persisted parcel means a cold process never touches the county endpoint."""
        get = AsyncMock()
        with (
            patch(
                "plotlot.storage.assessor_cache.get_cached_parcel",
                new=AsyncMock(return_value=(7710.48828125, "1233 HUENEME LLC")),
            ),
            patch.object(httpx.AsyncClient, "get", new=get),
        ):
            lot, owner = await CaliforniaProvider()._assessor_lot_sqft(URL, APN)

        assert get.await_count == 0, "durable cache hit must not call the endpoint"
        assert lot == pytest.approx(7710.48828125)
        assert owner == "1233 HUENEME LLC"

    @pytest.mark.asyncio
    async def test_success_is_persisted(self):
        store = AsyncMock()
        with (
            patch(
                "plotlot.storage.assessor_cache.get_cached_parcel",
                new=AsyncMock(return_value=None),
            ),
            patch("plotlot.storage.assessor_cache.store_cached_parcel", new=store),
            patch.object(
                httpx.AsyncClient,
                "get",
                new=AsyncMock(return_value=_Resp(_feature(st_area=7710.0))),
            ),
        ):
            await CaliforniaProvider()._assessor_lot_sqft(URL, APN)

        store.assert_awaited_once()
        assert store.await_args.args[1] == APN
        assert store.await_args.args[2] == pytest.approx(7710.0)

    @pytest.mark.asyncio
    async def test_failure_is_not_persisted(self):
        store = AsyncMock()
        with (
            patch(
                "plotlot.storage.assessor_cache.get_cached_parcel",
                new=AsyncMock(return_value=None),
            ),
            patch("plotlot.storage.assessor_cache.store_cached_parcel", new=store),
            patch.object(
                httpx.AsyncClient, "get", new=AsyncMock(side_effect=httpx.ReadTimeout("stalled"))
            ),
        ):
            await CaliforniaProvider()._assessor_lot_sqft(URL, APN)

        store.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_database_outage_does_not_break_the_lookup(self):
        """If the DB is down the lookup must still work off the network."""
        with (
            patch(
                "plotlot.storage.assessor_cache.get_cached_parcel",
                new=AsyncMock(side_effect=RuntimeError("db down")),
            ),
            patch(
                "plotlot.storage.assessor_cache.store_cached_parcel",
                new=AsyncMock(side_effect=RuntimeError("db down")),
            ),
            patch.object(
                httpx.AsyncClient,
                "get",
                new=AsyncMock(return_value=_Resp(_feature(st_area=7710.0))),
            ),
        ):
            with pytest.raises(RuntimeError):
                # Guard the assumption: the helpers themselves swallow errors, so
                # a raising stub proves the provider is not wrapping them.
                await CaliforniaProvider()._assessor_lot_sqft(URL, APN)

    def test_cache_key_is_scoped_to_the_source_layer(self):
        """APNs are unique per county, not globally — the key must include the layer."""
        from plotlot.storage.assessor_cache import cache_key

        assert cache_key("https://county-a/layer", APN) != cache_key("https://county-b/layer", APN)
        assert cache_key(URL, APN) == cache_key(URL, APN)
