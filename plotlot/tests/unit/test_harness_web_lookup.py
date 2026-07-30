from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from plotlot.harness.web_lookup import WebLookupStatus, execute_web_contents, execute_web_search


class _RecordingSpan:
    def __init__(self) -> None:
        self.attributes: dict[str, str | int | float | bool] = {}

    def set_attribute(self, key: str, value: str | int | float | bool) -> None:
        self.attributes[key] = value


@pytest.mark.asyncio
async def test_execute_web_search_exa_maps_results_and_traces_provider() -> None:
    span = _RecordingSpan()
    response = AsyncMock(spec=httpx.Response)
    response.status_code = 200
    response.json.return_value = {
        "results": [
            {
                "title": "RM-3-7 zoning summary",
                "url": "https://example.com/rm-3-7",
                "publishedDate": "2026-01-05T00:00:00.000Z",
                "highlights": ["Front setback 15 feet.", "Height limit 45 feet."],
                "text": "RM-3-7 allows medium-density residential development.",
            }
        ]
    }
    response.raise_for_status.return_value = None

    @contextmanager
    def _span_cm(*_args, **_kwargs):
        yield span

    with (
        patch("plotlot.harness.web_lookup_clients.start_otel_span", _span_cm),
        patch("httpx.AsyncClient") as mock_client_cls,
    ):
        mock_client = mock_client_cls.return_value
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.post = AsyncMock(return_value=response)

        result = await execute_web_search(
            "RM-3-7 zoning",
            provider="exa",
            exa_api_key="exa-test-key",
        )

    assert result.status == WebLookupStatus.SUCCESS
    assert len(result.results) == 1
    assert result.results[0].title == "RM-3-7 zoning summary"
    assert result.results[0].url == "https://example.com/rm-3-7"
    assert result.results[0].description == "Front setback 15 feet. Height limit 45 feet."
    assert result.results[0].content == "RM-3-7 allows medium-density residential development."
    assert span.attributes["plotlot.web_search.provider"] == "exa"
    assert span.attributes["plotlot.web_search.status"] == "success"
    assert span.attributes["plotlot.web_search.result_count"] == 1


@pytest.mark.asyncio
async def test_execute_web_search_exa_without_key_returns_not_configured() -> None:
    result = await execute_web_search(
        "RM-3-7 zoning",
        provider="exa",
        exa_api_key=None,
    )

    assert result.status == WebLookupStatus.NOT_CONFIGURED
    assert result.message is not None
    assert "EXA_API_KEY" in result.message
    assert "search_zoning_ordinance" in result.message


@pytest.mark.asyncio
async def test_execute_web_contents_exa_maps_content_results_and_traces_provider() -> None:
    span = _RecordingSpan()
    response = AsyncMock(spec=httpx.Response)
    response.status_code = 200
    response.json.return_value = {
        "results": [
            {
                "title": "17605 NW 19th Avenue, Miami Gardens, FL 33056 | Zillow",
                "url": "https://www.zillow.com/homedetails/example-land",
                "highlights": ["Sold for $135,000.", "Lot size: 9,000 sqft."],
                "text": "Public sold listing. Sold for $135,000. Lot size 9,000 sqft.",
            }
        ]
    }
    response.raise_for_status.return_value = None

    @contextmanager
    def _span_cm(*_args, **_kwargs):
        yield span

    with (
        patch("plotlot.harness.web_lookup_clients.start_otel_span", _span_cm),
        patch("httpx.AsyncClient") as mock_client_cls,
    ):
        mock_client = mock_client_cls.return_value
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.post = AsyncMock(return_value=response)

        result = await execute_web_contents(
            ["https://www.zillow.com/homedetails/example-land"],
            provider="exa",
            exa_api_key="exa-test-key",
        )

    assert result.status == WebLookupStatus.SUCCESS
    assert result.results[0].title.startswith("17605 NW 19th Avenue")
    assert "Sold for $135,000." in result.results[0].description
    assert "Lot size 9,000 sqft." in result.results[0].content
    assert span.attributes["plotlot.web_contents.provider"] == "exa"
    assert span.attributes["plotlot.web_contents.status"] == "success"
    assert span.attributes["plotlot.web_contents.result_count"] == 1
