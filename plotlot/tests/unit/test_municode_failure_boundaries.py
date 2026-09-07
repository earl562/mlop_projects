from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from plotlot.core.types import MUNICODE_CONFIGS
from plotlot.ingestion.scraper import MunicodeScraper
from plotlot.ingestion.source_acquisition import SourceAcquisitionError
from plotlot.land_use.models import OrdinanceJurisdiction, OrdinanceSearchArgs
from plotlot.land_use.ordinances.service import search_municode_live


@pytest.mark.parametrize("during_toc", [True, False], ids=["toc", "leaf"])
@pytest.mark.parametrize("transport_failure", [False, True], ids=["503", "timeout"])
async def test_live_search_retains_safe_http_failure_behavior(
    during_toc: bool, transport_failure: bool
) -> None:
    # Given a failed TOC or one failed leaf alongside one valid leaf.
    def respond(request: httpx.Request) -> httpx.Response:
        is_toc = request.url.path == "/codesToc/children"
        if (is_toc and during_toc) or (not is_toc and request.url.params["nodeId"] == "bad"):
            if transport_failure:
                raise httpx.ReadTimeout("fixture timeout", request=request)
            return httpx.Response(503)
        if is_toc:
            return httpx.Response(
                200,
                json=[
                    {"Id": "bad", "Heading": "Parking A", "HasChildren": False},
                    {"Id": "good", "Heading": "Parking B", "HasChildren": False},
                ],
            )
        return httpx.Response(200, json={"Docs": [{"Id": "good", "Content": "<p>Parking</p>"}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    # When the service uses the real scraper, with isolated config/cache and HTTP.
    with (
        patch("plotlot.land_use.ordinances.service.httpx.AsyncClient", return_value=client),
        patch("plotlot.land_use.ordinances.service._TOC_CACHE", new={}),
        patch(
            "plotlot.land_use.ordinances.service.get_municode_configs",
            new=AsyncMock(return_value={"miami_dade": MUNICODE_CONFIGS["miami_dade"]}),
        ),
    ):
        results = await search_municode_live(
            OrdinanceSearchArgs(
                jurisdiction=OrdinanceJurisdiction(state="FL", municipality="Miami-Dade"),
                query="parking",
                limit=2,
            )
        )
    # Then failed source content is omitted without crashing or losing the valid leaf.
    assert [result.section_id for result in results] == ([] if during_toc else ["good"])


@pytest.mark.parametrize("duplicate", [False, True], ids=["missing-id", "duplicate-id"])
async def test_live_search_omits_identity_conflicts(duplicate: bool) -> None:
    # Given a selected section with an ambiguous or absent requested identity.
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/codesToc/children":
            return httpx.Response(
                200, json=[{"Id": "A", "Heading": "Parking", "HasChildren": False}]
            )
        document = {"Id": "A" if duplicate else "B", "Content": "<p>Wrong evidence</p>"}
        return httpx.Response(200, json={"Docs": [document, document] if duplicate else [document]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    # When live search requests that section through the actual scraper.
    with (
        patch("plotlot.land_use.ordinances.service.httpx.AsyncClient", return_value=client),
        patch("plotlot.land_use.ordinances.service._TOC_CACHE", new={}),
        patch(
            "plotlot.land_use.ordinances.service.get_municode_configs",
            new=AsyncMock(return_value={"miami_dade": MUNICODE_CONFIGS["miami_dade"]}),
        ),
    ):
        results = await search_municode_live(
            OrdinanceSearchArgs(
                jurisdiction=OrdinanceJurisdiction(state="FL", municipality="Miami-Dade"),
                query="parking",
            )
        )
    # Then the mismatched text never becomes a cited result.
    assert results == []


async def test_section_sdk_preserves_http_status_error_for_api_consumers() -> None:
    # Given a real upstream HTTP failure.
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(503))
    ) as client:
        # When an API consumer requests the section through the shared SDK.
        with pytest.raises(httpx.HTTPStatusError) as caught:
            await MunicodeScraper().get_section_content(client, MUNICODE_CONFIGS["miami_dade"], "A")
    # Then callers retain the upstream HTTP status contract.
    assert caught.value.response.status_code == 503


@pytest.mark.parametrize("branches", [False, True], ids=["leaf-requests", "toc-requests"])
@pytest.mark.parametrize("caller_cancel", [False, True], ids=["source-failure", "caller-cancel"])
async def test_chapter_awaits_sibling_cleanup_before_closing_client(
    branches: bool, caller_cancel: bool
) -> None:
    # Given two concurrent requests, one held open until cancellation or test cleanup.
    ready, release, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()
    client_closed_on_cancel: list[bool] = []
    config = MUNICODE_CONFIGS["miami_dade"]

    async def respond(request: httpx.Request) -> httpx.Response:
        node_id = request.url.params["nodeId"]
        if node_id == config.zoning_node_id:
            return httpx.Response(
                200,
                json=[
                    {"Id": "slow", "Heading": "Slow", "HasChildren": branches},
                    {"Id": "fail", "Heading": "Fail", "HasChildren": branches},
                ],
            )
        if node_id == "slow":
            ready.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                client_closed_on_cancel.append(client.is_closed)
                raise
            finally:
                finished.set()
            return httpx.Response(
                200, json=[] if branches else {"Docs": [{"Id": "slow", "Content": "ok"}]}
            )
        await ready.wait()
        if caller_cancel:
            await release.wait()
        return httpx.Response(503)

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    with patch("plotlot.ingestion.scraper.httpx.AsyncClient", return_value=client):
        task = asyncio.create_task(MunicodeScraper().scrape_zoning_chapter(config))
        try:
            await asyncio.wait_for(ready.wait(), timeout=1)
            # When a source fails or the caller cancels the chapter.
            if caller_cancel:
                task.cancel()
            with pytest.raises(asyncio.CancelledError if caller_cancel else SourceAcquisitionError):
                await asyncio.wait_for(task, timeout=1)
            # Then sibling cancellation finishes while its HTTP client is still open.
            assert finished.is_set()
            assert client_closed_on_cancel == [False]
        finally:
            release.set()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await asyncio.wait_for(finished.wait(), timeout=1)
