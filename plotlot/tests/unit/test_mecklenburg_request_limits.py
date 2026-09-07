from __future__ import annotations

import asyncio
from unittest.mock import patch

import httpx
import pytest

from plotlot.property.mecklenburg import MecklenburgProvider


@pytest.mark.parametrize("address", ["", "Main St", "600 % ST", "600 _ ST"])
async def test_invalid_address_abstains_without_network(address: str) -> None:
    # Given an input that cannot identify an exact numbered street.
    with patch("plotlot.property.mecklenburg.httpx.AsyncClient") as factory:
        # When lookup receives that input.
        record = await MecklenburgProvider().lookup(address, "Mecklenburg", state="NC")
    # Then it makes no county request.
    assert record is None
    factory.assert_not_called()


@pytest.mark.parametrize(
    ("lat", "lng"),
    [(35.0, None), (None, -80.0), (float("nan"), -80.0), (91.0, -80.0), (35.0, 181.0)],
)
async def test_invalid_coordinates_abstain_without_network(
    lat: float | None, lng: float | None
) -> None:
    # Given incomplete or invalid coordinate evidence.
    with patch("plotlot.property.mecklenburg.httpx.AsyncClient") as factory:
        # When lookup receives those coordinates.
        record = await MecklenburgProvider().lookup("600 E 4TH ST", "Mecklenburg", lat=lat, lng=lng)
    # Then the malformed spatial query is not submitted.
    assert record is None
    factory.assert_not_called()


@pytest.mark.parametrize(("county", "state"), [("Gaston", "NC"), ("Mecklenburg", "FL")])
async def test_wrong_jurisdiction_abstains_without_network(county: str, state: str) -> None:
    # Given a location outside this provider's county/state contract.
    with patch("plotlot.property.mecklenburg.httpx.AsyncClient") as factory:
        # When lookup receives the location.
        record = await MecklenburgProvider().lookup("600 E 4TH ST", county, state=state)
    # Then it cannot silently return a Charlotte property.
    assert record is None
    factory.assert_not_called()


async def test_address_query_escapes_quotes_and_bounds_candidate_inventory() -> None:
    # Given an exact street containing an apostrophe.
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"features": []})

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    with patch("plotlot.property.mecklenburg.httpx.AsyncClient", return_value=client):
        # When the provider submits the candidate query.
        record = await MecklenburgProvider().lookup("100 O'BRIEN ST", "Mecklenburg")
    # Then it escapes literals and requests a bounded overflow sentinel without geometry.
    assert record is None
    assert len(requests) == 1
    params = requests[0].url.params
    assert params["where"] == (
        "UPPER(address) = '100 O''BRIEN ST' OR UPPER(address) LIKE '100 O''BRIEN ST %'"
    )
    assert params["resultRecordCount"] == "21"
    assert params["returnGeometry"] == "false"
    assert "*" not in params["outFields"]
    assert client.is_closed


async def test_caller_cancellation_propagates_and_closes_client() -> None:
    # Given an in-flight county request that has not completed.
    started, stopped = asyncio.Event(), asyncio.Event()

    async def respond(request: httpx.Request) -> httpx.Response:
        started.set()
        try:
            await asyncio.Event().wait()
            return httpx.Response(200, json={"features": []})
        finally:
            stopped.set()

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    with patch("plotlot.property.mecklenburg.httpx.AsyncClient", return_value=client):
        async with asyncio.timeout(1):
            task = asyncio.create_task(MecklenburgProvider().lookup("600 E 4TH ST", "Mecklenburg"))
            await started.wait()
            # When the caller cancels the lookup.
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    # Then cancellation remains distinguishable from no match and releases the client.
    assert stopped.is_set()
    assert client.is_closed


async def test_aggregate_deadline_abstains_and_releases_inflight_request() -> None:
    # Given a county request that outlives the one overall lookup budget.
    deadline = asyncio.timeout(20)
    stopped = asyncio.Event()

    async def respond(request: httpx.Request) -> httpx.Response:
        deadline.reschedule(asyncio.get_running_loop().time())
        try:
            await asyncio.Event().wait()
            return httpx.Response(200, json={"features": []})
        finally:
            stopped.set()

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    with (
        patch("plotlot.property.mecklenburg.httpx.AsyncClient", return_value=client),
        patch("plotlot.property.mecklenburg.asyncio.timeout", return_value=deadline) as timeout,
    ):
        # When the aggregate deadline expires inside the HTTP request.
        record = await MecklenburgProvider().lookup("600 E 4TH ST", "Mecklenburg")
    # Then lookup abstains without leaving the network task running.
    assert record is None
    timeout.assert_called_once_with(20)
    assert stopped.is_set()
    assert client.is_closed
