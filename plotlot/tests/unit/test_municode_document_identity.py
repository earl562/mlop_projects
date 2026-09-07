from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

import httpx
import pytest

from plotlot.core.types import MUNICODE_CONFIGS
from plotlot.ingestion.scraper import BASE_URL, MunicodeScraper
from plotlot.ingestion.source_acquisition import (
    SourceAcquisitionError,
    SourceFailureReason,
)


type JsonValue = str | int | float | bool | None | Sequence[JsonValue] | Mapping[str, JsonValue]
type JsonPayload = Mapping[str, JsonValue]
type ResponseHandler = Callable[[httpx.Request], httpx.Response]


def _handler(payload: JsonPayload) -> ResponseHandler:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload, request=request)

    return respond


async def _get_section_content(payload: JsonPayload, node_id: str) -> str:
    scraper = MunicodeScraper()
    config = MUNICODE_CONFIGS["miami_dade"]
    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler(payload))) as client:
        return await scraper.get_section_content(client, config, node_id)


@pytest.mark.asyncio
async def test_missing_requested_id_abstains_with_identity_mismatch() -> None:
    payload = {
        "Docs": [{"Id": "other", "TitleHtml": "<h3>Other</h3>", "Content": "<p>Other text.</p>"}]
    }

    with pytest.raises(SourceAcquisitionError) as caught:
        await _get_section_content(payload, "requested")

    assert caught.value.source_url == f"{BASE_URL}/CodesContent"
    assert caught.value.reason is SourceFailureReason.IDENTITY_MISMATCH


@pytest.mark.asyncio
async def test_doc_without_id_abstains_with_identity_mismatch() -> None:
    payload = {"Docs": [{"TitleHtml": "<h3>Untyped</h3>", "Content": "<p>Text.</p>"}]}

    with pytest.raises(SourceAcquisitionError) as caught:
        await _get_section_content(payload, "requested")

    assert caught.value.reason is SourceFailureReason.IDENTITY_MISMATCH


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "docs",
    [
        [
            {"Id": "requested", "TitleHtml": "<h3>Same</h3>", "Content": "<p>Text.</p>"},
            {"Id": "requested", "TitleHtml": "<h3>Same</h3>", "Content": "<p>Text.</p>"},
        ],
        [
            {"Id": "requested", "TitleHtml": "<h3>First</h3>", "Content": "<p>One.</p>"},
            {"Id": "requested", "TitleHtml": "<h3>Second</h3>", "Content": "<p>Two.</p>"},
        ],
    ],
    ids=["same-content", "conflicting-content"],
)
async def test_duplicate_requested_id_abstains_with_identity_mismatch(
    docs: list[dict[str, str]],
) -> None:
    with pytest.raises(SourceAcquisitionError) as caught:
        await _get_section_content({"Docs": docs}, "requested")

    assert caught.value.reason is SourceFailureReason.IDENTITY_MISMATCH


@pytest.mark.asyncio
@pytest.mark.parametrize("matching_index", [0, 1])
async def test_unique_match_preserves_exact_title_and_content_in_either_order(
    matching_index: int,
) -> None:
    matching_doc = {
        "Id": "requested",
        "TitleHtml": "<h3>Requested title</h3>",
        "Content": "<p>Requested content.</p>",
    }
    unrelated_doc = {
        "Id": "other",
        "TitleHtml": "<h3>Unrelated title</h3>",
        "Content": "<p>Unrelated content.</p>",
    }
    docs = [matching_doc, unrelated_doc] if matching_index == 0 else [unrelated_doc, matching_doc]

    result = await _get_section_content({"Docs": docs}, "requested")

    assert result == "<h3>Requested title</h3><p>Requested content.</p>"
    assert "Unrelated" not in result


@pytest.mark.asyncio
async def test_malformed_doc_content_still_abstains_with_parse_error() -> None:
    payload = {"Docs": [{"Id": "requested", "TitleHtml": "<h3>Bad</h3>", "Content": None}]}

    with pytest.raises(SourceAcquisitionError) as caught:
        await _get_section_content(payload, "requested")

    assert caught.value.reason is SourceFailureReason.PARSE_ERROR


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy_key", ["Document", "document"])
async def test_empty_docs_legacy_document_response_remains_compatible(legacy_key: str) -> None:
    result = await _get_section_content(
        {"Docs": [], legacy_key: "<p>Legacy text.</p>"}, "requested"
    )

    assert result == "<p>Legacy text.</p>"
