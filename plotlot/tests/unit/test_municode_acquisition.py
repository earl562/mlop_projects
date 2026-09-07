from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from plotlot.core.types import MUNICODE_CONFIGS
from plotlot.ingestion.acp_coordinator import IngestRequest, run_on_demand_ingestion
from plotlot.ingestion.scraper import MunicodeScraper
from plotlot.ingestion.source_acquisition import SourceAcquisitionError, SourceFailureReason


@pytest.mark.parametrize(
    ("status", "content", "reason"),
    [
        (503, "", SourceFailureReason.HTTP_ERROR),
        (200, "", SourceFailureReason.EMPTY_CONTENT),
        (200, "<p> </p>", SourceFailureReason.EMPTY_CONTENT),
    ],
)
async def test_failed_expected_leaf_rejects_successful_subset(
    status: int, content: str, reason: SourceFailureReason
) -> None:
    # Given two expected leaves, with one valid response and one failed/empty response.
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/codesToc/children":
            return httpx.Response(
                200,
                json=[
                    {"Id": "good", "Heading": "Section 1", "HasChildren": False},
                    {"Id": "bad", "Heading": "Section 2", "HasChildren": False},
                ],
            )
        node_id = request.url.params["nodeId"]
        body = "<p>Residential zoning standards. </p>" * 10 if node_id == "good" else content
        return httpx.Response(
            200 if node_id == "good" else status,
            json={"Docs": [{"Id": node_id, "TitleHtml": "", "Content": body}]},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    scraper = MunicodeScraper()
    # When the real crawler fetches the chapter through HTTP-level responses.
    with (
        patch("plotlot.ingestion.scraper.httpx.AsyncClient", return_value=client),
        pytest.raises(SourceAcquisitionError) as caught,
    ):
        await scraper.scrape_zoning_chapter(MUNICODE_CONFIGS["miami_dade"])
    # Then no successful subset is returned, and the failure stays typed.
    assert caught.value.reason is reason
    assert caught.value.status_code == (503 if status == 503 else None)


async def test_successful_chapter_preserves_both_requested_leaf_identities() -> None:
    # Given a complete two-leaf chapter, with different content per identity.
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/codesToc/children":
            return httpx.Response(
                200,
                json=[
                    {"Id": "A", "Heading": "Section A", "HasChildren": False},
                    {"Id": "B", "Heading": "Section B", "HasChildren": False},
                ],
            )
        node_id = request.url.params["nodeId"]
        return httpx.Response(
            200,
            json={"Docs": [{"Id": node_id, "Content": f"<p>Content for {node_id}.</p>"}]},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    # When the real crawler obtains both leaves.
    with patch("plotlot.ingestion.scraper.httpx.AsyncClient", return_value=client):
        sections = await MunicodeScraper().scrape_zoning_chapter(MUNICODE_CONFIGS["miami_dade"])
    # Then content remains bound to the requested identity in TOC order.
    assert [(section.node_id, section.html_content) for section in sections] == [
        ("A", "<p>Content for A.</p>"),
        ("B", "<p>Content for B.</p>"),
    ]


async def test_unvisited_branch_at_depth_limit_rejects_partial_inventory() -> None:
    # Given a leaf and another branch at the configured traversal boundary.
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {"Id": "leaf", "Heading": "Section", "HasChildren": False},
                {"Id": "branch", "Heading": "Article", "HasChildren": True},
            ],
        )

    scraper = MunicodeScraper()
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        # When traversal would need to pass its configured bound.
        with pytest.raises(SourceAcquisitionError) as caught:
            await scraper.walk_toc(client, MUNICODE_CONFIGS["miami_dade"], "root", max_depth=1)
    # Then the leaf is not mistaken for a complete inventory.
    assert caught.value.reason is SourceFailureReason.DEPTH_LIMIT


@pytest.mark.parametrize("during_resolution", [True, False], ids=["resolving", "fetching"])
async def test_coordinator_stops_before_models_or_storage_on_acquisition_failure(
    during_resolution: bool,
) -> None:
    # Given a known source acquisition error at either acquisition boundary.
    source_error = SourceAcquisitionError(
        "https://example.invalid/code?token=private",
        SourceFailureReason.HTTP_ERROR,
        503,
    )
    adapter = AsyncMock()
    adapter.name = "municode"
    adapter.fetch_chunks.side_effect = source_error
    resolver = AsyncMock(return_value=adapter)
    if during_resolution:
        resolver.side_effect = source_error
    embed = AsyncMock(side_effect=AssertionError("model call forbidden"))
    init_db = AsyncMock(side_effect=AssertionError("database call forbidden"))
    session = AsyncMock(side_effect=AssertionError("database call forbidden"))
    # When the actual coordinator handles that acquisition.
    with (
        patch("plotlot.ingestion.acp_coordinator.resolve_adapter", new=resolver),
        patch("plotlot.ingestion.acp_coordinator.embed_texts", new=embed),
        patch("plotlot.ingestion.acp_coordinator.init_db", new=init_db),
        patch("plotlot.ingestion.acp_coordinator.get_session", new=session),
    ):
        events = [
            event
            async for event in run_on_demand_ingestion(
                IngestRequest(municipality="Fixture City", state="FL")
            )
        ]
    # Then callers see a terminal source failure without credentials or side effects.
    assert events[-1].error == "incomplete_source"
    assert events[-1].stage == "error"
    assert events[-1].complete is True
    assert "private" not in events[-1].message
    assert not {"embedding", "storing", "complete"}.intersection(e.stage for e in events)
    assert embed.call_count == init_db.call_count == session.call_count == 0
