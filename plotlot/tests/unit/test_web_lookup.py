from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from plotlot.domain.types import ToolContext
from plotlot.harness.web_lookup import (
    WebLookupStatus,
    WebSearchProvider,
    WebSearchResult,
    WebSearchResultItem,
    execute_web_search,
    web_search_payload,
)


def _tool_context() -> ToolContext:
    return ToolContext(
        workspace_id="ws_fixture",
        actor_user_id="analyst_fixture",
        run_id="run_fixture_web_lookup",
        live_network_allowed=True,
        risk_budget_cents=100,
    )


@pytest.mark.asyncio
async def test_execute_web_search_auto_prefers_exa_and_does_not_fall_back_to_jina() -> None:
    response = Mock(status_code=200)
    response.raise_for_status = Mock()
    response.json.return_value = {
        "results": [
            {
                "title": "Miami zoning update",
                "url": "https://example.com/exa-result",
                "summary": "Fixture summary",
                "text": "Fixture content from Exa.",
            }
        ]
    }
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.post = AsyncMock(return_value=response)

    with patch("plotlot.harness.web_lookup_clients.httpx.AsyncClient", return_value=client):
        result = await execute_web_search(
            "Miami zoning update",
            provider=WebSearchProvider.AUTO,
            exa_api_key="exa-key",
        )

    assert result.status == WebLookupStatus.SUCCESS
    assert result.provider == WebSearchProvider.EXA
    assert result.results[0].url == "https://example.com/exa-result"
    assert result.results[0].description == "Fixture summary"
    client.post.assert_awaited_once()
    assert client.post.await_args.args[0] == "https://api.exa.ai/search"
    assert client.post.await_args.kwargs["headers"]["x-api-key"] == "exa-key"


@pytest.mark.asyncio
async def test_execute_web_search_accepts_exa_provider_as_string() -> None:
    response = Mock(status_code=200)
    response.raise_for_status = Mock()
    response.json.return_value = {
        "results": [
            {
                "title": "Miami zoning update",
                "url": "https://example.com/exa-result",
                "summary": "Fixture summary",
                "text": "Fixture content from Exa.",
            }
        ]
    }
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.post = AsyncMock(return_value=response)

    with patch("plotlot.harness.web_lookup_clients.httpx.AsyncClient", return_value=client):
        result = await execute_web_search(
            "Miami zoning update",
            provider="exa",
            exa_api_key="exa-key",
        )

    assert result.provider == WebSearchProvider.EXA
    client.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_web_search_treats_jina_provider_name_as_exa() -> None:
    response = Mock(status_code=200)
    response.raise_for_status = Mock()
    response.json.return_value = {
        "results": [
            {
                "title": "Miami zoning update",
                "url": "https://example.com/exa-result",
                "summary": "Fixture summary",
                "text": "Fixture content from Exa.",
            }
        ]
    }
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.post = AsyncMock(return_value=response)

    with patch("plotlot.harness.web_lookup_clients.httpx.AsyncClient", return_value=client):
        result = await execute_web_search(
            "Miami zoning update",
            provider="jina",
            exa_api_key="exa-key",
        )

    assert result.status == WebLookupStatus.SUCCESS
    assert result.provider == WebSearchProvider.EXA
    client.post.assert_awaited_once()
    assert client.post.await_args.kwargs["headers"]["x-api-key"] == "exa-key"


@pytest.mark.asyncio
async def test_execute_web_search_without_keys_mentions_exa_key() -> None:
    result = await execute_web_search(
        "Miami zoning update",
        provider=WebSearchProvider.AUTO,
        exa_api_key=None,
    )

    assert result.status == WebLookupStatus.NOT_CONFIGURED
    assert result.message is not None
    assert "EXA_API_KEY" in result.message


def test_web_search_payload_uses_provider_specific_publisher() -> None:
    payload = web_search_payload(
        WebSearchResult(
            status=WebLookupStatus.SUCCESS,
            provider=WebSearchProvider.EXA,
            results=[
                WebSearchResultItem(
                    title="Exa result",
                    url="https://example.com/exa-result",
                    description="Fixture summary",
                    content="Fixture content from Exa.",
                )
            ],
        ),
        query="Miami zoning update",
        context=_tool_context(),
    )

    assert payload["provider"] == WebSearchProvider.EXA.value
    assert payload["provider_policy"] == "exa_only"
    assert payload["legacy_provider_aliases"] == ["jina"]
    assert payload["results"][0]["citation"]["publisher"] == "Exa Search"
    assert payload["evidence"][0]["citation"]["publisher"] == "Exa Search"


def test_web_search_payload_normalizes_legacy_jina_provider_to_exa() -> None:
    payload = web_search_payload(
        WebSearchResult(
            status=WebLookupStatus.SUCCESS,
            provider=WebSearchProvider.JINA,
            results=[
                WebSearchResultItem(
                    title="Legacy provider result",
                    url="https://example.com/legacy-result",
                    description="Fixture summary",
                    content="Fixture content from Exa.",
                )
            ],
        ),
        query="Miami zoning update",
        context=_tool_context(),
    )

    assert payload["provider"] == WebSearchProvider.EXA.value
    assert payload["provider_policy"] == "exa_only"
    assert payload["legacy_provider_aliases"] == ["jina"]
    assert payload["results"][0]["citation"]["publisher"] == "Exa Search"
    assert payload["evidence"][0]["citation"]["publisher"] == "Exa Search"
