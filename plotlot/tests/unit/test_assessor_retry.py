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
    california._ASSESSOR_CACHE.clear()
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
