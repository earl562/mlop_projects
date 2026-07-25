from __future__ import annotations

from typing import Protocol

import httpx
from pydantic import TypeAdapter, ValidationError

from plotlot.harness.contracts import JsonObject
from plotlot.harness.web_lookup_models import (
    WebLookupStatus,
    WebSearchProvider,
    WebSearchResult,
    WebSearchResultItem,
)
from plotlot.observability.tracing import start_otel_span

JsonObjectAdapter = TypeAdapter(JsonObject)
JsonObjectListAdapter = TypeAdapter(list[JsonObject])
_DEFAULT_GUIDANCE = "Use search_zoning_ordinance for zoning questions."
_EXA_API_URL = "https://api.exa.ai/search"
_EXA_CONTENTS_API_URL = "https://api.exa.ai/contents"


class _SpanLike(Protocol):
    def set_attribute(self, key: str, value: str | int | float | bool) -> None: ...


async def execute_web_search(
    query: str,
    *,
    provider: WebSearchProvider | str = WebSearchProvider.EXA,
    exa_api_key: str | None,
) -> WebSearchResult:
    normalized_provider = _normalize_provider(provider)
    normalized_query = query.strip()
    if not normalized_query:
        return WebSearchResult(
            status=WebLookupStatus.ERROR,
            provider=normalized_provider,
            message="query is required",
        )

    resolved_provider = _resolve_provider(
        provider=normalized_provider,
        exa_api_key=exa_api_key,
    )
    if resolved_provider is None:
        return WebSearchResult(
            status=WebLookupStatus.NOT_CONFIGURED,
            provider=normalized_provider,
            message=(
                "Web search is not available (set EXA_API_KEY). " f"{_DEFAULT_GUIDANCE}"
            ),
        )

    with start_otel_span(
        "plotlot.harness.web_search",
        attributes={
            "plotlot.web_search.provider": resolved_provider.value,
            "plotlot.web_search.query_length": len(normalized_query),
        },
    ) as span:
        span.set_attribute("plotlot.web_search.provider", resolved_provider.value)
        span.set_attribute("plotlot.web_search.query_length", len(normalized_query))
        api_key = _provider_api_key(
            provider=resolved_provider,
            exa_api_key=exa_api_key,
        )
        if not api_key:
            result = WebSearchResult(
                status=WebLookupStatus.NOT_CONFIGURED,
                provider=resolved_provider,
                message=(
                    "Web search is not available "
                    f"({_provider_env_var(resolved_provider)} not set). {_DEFAULT_GUIDANCE}"
                ),
            )
            _set_span_result(span, result)
            return result

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await _execute_provider_request(
                    client=client,
                    provider=resolved_provider,
                    query=normalized_query,
                    api_key=api_key,
                )
            span.set_attribute("plotlot.web_search.http_status", response.status_code)
            status_result = _response_status_result(
                provider=resolved_provider,
                status_code=response.status_code,
            )
            if status_result is not None:
                _set_span_result(span, status_result)
                return status_result
            response.raise_for_status()
            payload = JsonObjectAdapter.validate_python(response.json())
        except httpx.HTTPError as exc:
            result = WebSearchResult(
                status=WebLookupStatus.ERROR,
                provider=resolved_provider,
                message=f"Web search failed: {exc}",
            )
            _set_span_result(span, result)
            return result
        except (ValidationError, ValueError) as exc:
            result = WebSearchResult(
                status=WebLookupStatus.ERROR,
                provider=resolved_provider,
                message=f"Web search response could not be parsed: {exc}",
            )
            _set_span_result(span, result)
            return result

        result = WebSearchResult(
            status=WebLookupStatus.SUCCESS,
            provider=resolved_provider,
            results=_result_items(payload, provider=resolved_provider),
        )
        _set_span_result(span, result)
        return result


async def execute_web_contents(
    urls: list[str],
    *,
    provider: WebSearchProvider | str = WebSearchProvider.EXA,
    exa_api_key: str | None,
) -> WebSearchResult:
    normalized_provider = _normalize_provider(provider)
    normalized_urls = [url.strip() for url in urls if url.strip()]
    if not normalized_urls:
        return WebSearchResult(
            status=WebLookupStatus.ERROR,
            provider=normalized_provider,
            message="at least one url is required",
        )
    resolved_provider = _resolve_provider(
        provider=normalized_provider,
        exa_api_key=exa_api_key,
    )
    if resolved_provider is None:
        return WebSearchResult(
            status=WebLookupStatus.NOT_CONFIGURED,
            provider=normalized_provider,
            message="Web contents are not available (set EXA_API_KEY).",
        )

    with start_otel_span(
        "plotlot.harness.web_contents",
        attributes={
            "plotlot.web_contents.provider": resolved_provider.value,
            "plotlot.web_contents.url_count": len(normalized_urls),
        },
    ) as span:
        span.set_attribute("plotlot.web_contents.provider", resolved_provider.value)
        span.set_attribute("plotlot.web_contents.url_count", len(normalized_urls))
        if not exa_api_key:
            result = WebSearchResult(
                status=WebLookupStatus.NOT_CONFIGURED,
                provider=resolved_provider,
                message=f"Web contents are not available ({_provider_env_var(resolved_provider)} not set).",
            )
            _set_contents_span_result(span, result)
            return result
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    _EXA_CONTENTS_API_URL,
                    headers={
                        "x-api-key": exa_api_key,
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                    json={
                        "urls": normalized_urls[:5],
                        "text": {"maxCharacters": 4000, "includeHtmlTags": False},
                        "highlights": {"numSentences": 2},
                    },
                )
            span.set_attribute("plotlot.web_contents.http_status", response.status_code)
            status_result = _response_status_result(
                provider=resolved_provider,
                status_code=response.status_code,
            )
            if status_result is not None:
                _set_contents_span_result(span, status_result)
                return status_result
            response.raise_for_status()
            payload = JsonObjectAdapter.validate_python(response.json())
        except httpx.HTTPError as exc:
            result = WebSearchResult(
                status=WebLookupStatus.ERROR,
                provider=resolved_provider,
                message=f"Web contents lookup failed: {exc}",
            )
            _set_contents_span_result(span, result)
            return result
        except (ValidationError, ValueError) as exc:
            result = WebSearchResult(
                status=WebLookupStatus.ERROR,
                provider=resolved_provider,
                message=f"Web contents response could not be parsed: {exc}",
            )
            _set_contents_span_result(span, result)
            return result

        result = WebSearchResult(
            status=WebLookupStatus.SUCCESS,
            provider=resolved_provider,
            results=_result_items(payload, provider=resolved_provider),
        )
        _set_contents_span_result(span, result)
        return result


async def execute_jina_web_search(
    query: str,
    *,
    api_key: str | None,
) -> WebSearchResult:
    return await execute_web_search(
        query,
        provider=WebSearchProvider.EXA,
        exa_api_key=api_key,
    )


def _normalize_provider(provider: WebSearchProvider | str) -> WebSearchProvider:
    if provider == WebSearchProvider.AUTO or provider == "auto":
        return WebSearchProvider.AUTO
    if (
        provider == WebSearchProvider.EXA
        or provider == "exa"
        or provider == WebSearchProvider.JINA
        or provider == "jina"
    ):
        return WebSearchProvider.EXA
    return WebSearchProvider.EXA


def _resolve_provider(
    *,
    provider: WebSearchProvider,
    exa_api_key: str | None,
) -> WebSearchProvider | None:
    match provider:
        case WebSearchProvider.AUTO:
            if exa_api_key:
                return WebSearchProvider.EXA
            return None
        case WebSearchProvider.JINA | WebSearchProvider.EXA:
            if exa_api_key:
                return WebSearchProvider.EXA
            return None


def _provider_api_key(
    *,
    provider: WebSearchProvider,
    exa_api_key: str | None,
) -> str | None:
    match provider:
        case WebSearchProvider.JINA:
            return exa_api_key
        case WebSearchProvider.EXA:
            return exa_api_key
        case WebSearchProvider.AUTO:
            return None


def _provider_env_var(provider: WebSearchProvider) -> str:
    match provider:
        case WebSearchProvider.JINA:
            return "EXA_API_KEY"
        case WebSearchProvider.EXA:
            return "EXA_API_KEY"
        case WebSearchProvider.AUTO:
            return "EXA_API_KEY"


def _provider_name(provider: WebSearchProvider) -> str:
    match provider:
        case WebSearchProvider.JINA:
            return "Exa"
        case WebSearchProvider.EXA:
            return "Exa"
        case WebSearchProvider.AUTO:
            return "Web search"


async def _execute_provider_request(
    *,
    client: httpx.AsyncClient,
    provider: WebSearchProvider,
    query: str,
    api_key: str,
) -> httpx.Response:
    match provider:
        case WebSearchProvider.JINA:
            return await client.post(
                _EXA_API_URL,
                headers={
                    "x-api-key": api_key,
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json={
                    "query": query,
                    "numResults": 5,
                    "type": "auto",
                    "contents": {
                        "text": True,
                        "highlights": {"numSentences": 2},
                    },
                },
            )
        case WebSearchProvider.EXA:
            return await client.post(
                _EXA_API_URL,
                headers={
                    "x-api-key": api_key,
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json={
                    "query": query,
                    "numResults": 5,
                    "type": "auto",
                    "contents": {
                        "text": True,
                        "highlights": {"numSentences": 2},
                    },
                },
            )
        case WebSearchProvider.AUTO:
            raise ValueError("AUTO provider must be resolved before request execution")


def _response_status_result(
    *,
    provider: WebSearchProvider,
    status_code: int,
) -> WebSearchResult | None:
    if status_code in (402, 429):
        return WebSearchResult(
            status=WebLookupStatus.QUOTA_EXCEEDED,
            provider=provider,
            message=f"Web search quota exhausted for {_provider_name(provider)}. {_DEFAULT_GUIDANCE}",
        )
    if status_code in (401, 403):
        return WebSearchResult(
            status=WebLookupStatus.AUTH_ERROR,
            provider=provider,
            message=(
                f"Web search authentication failed (invalid {_provider_env_var(provider)}). "
                f"{_DEFAULT_GUIDANCE}"
            ),
        )
    return None


def _result_items(
    payload: JsonObject,
    *,
    provider: WebSearchProvider,
) -> list[WebSearchResultItem]:
    raw_items = _payload_items(payload, provider=provider)
    return [
        _result_item(item, provider=provider)
        for item in raw_items[:5]
        if isinstance(item, dict)
    ]


def _payload_items(
    payload: JsonObject,
    *,
    provider: WebSearchProvider,
) -> list[JsonObject]:
    match provider:
        case WebSearchProvider.JINA:
            raw_items = payload.get("results", [])
        case WebSearchProvider.EXA:
            raw_items = payload.get("results", [])
        case WebSearchProvider.AUTO:
            raw_items = []
    if not isinstance(raw_items, list):
        return []
    return JsonObjectListAdapter.validate_python(raw_items)


def _result_item(
    item: JsonObject,
    *,
    provider: WebSearchProvider,
) -> WebSearchResultItem:
    match provider:
        case WebSearchProvider.JINA:
            summary = str(item.get("summary", "")).strip()
            highlights = item.get("highlights", [])
            highlight_list = (
                [str(highlight) for highlight in highlights]
                if isinstance(highlights, list)
                else None
            )
            description = summary or _exa_description(highlight_list)
            content = str(item.get("text", ""))[:500]
            return WebSearchResultItem(
                title=str(item.get("title", "")),
                url=str(item.get("url", "")),
                description=description[:300],
                content=content,
            )
        case WebSearchProvider.EXA:
            summary = str(item.get("summary", "")).strip()
            highlights = item.get("highlights", [])
            highlight_list = (
                [str(highlight) for highlight in highlights]
                if isinstance(highlights, list)
                else None
            )
            description = summary or _exa_description(highlight_list)
            content = str(item.get("text", ""))[:500]
            return WebSearchResultItem(
                title=str(item.get("title", "")),
                url=str(item.get("url", "")),
                description=description[:300],
                content=content,
            )
        case WebSearchProvider.AUTO:
            raise ValueError("AUTO provider must be resolved before parsing results")


def _exa_description(highlights: list[str] | None) -> str:
    if highlights is None:
        return ""
    snippets = [highlight.strip() for highlight in highlights if highlight.strip()]
    return " ".join(snippets[:2])


def _set_span_result(span: _SpanLike, result: WebSearchResult) -> None:
    span.set_attribute("plotlot.web_search.status", result.status.value)
    span.set_attribute("plotlot.web_search.result_count", len(result.results))


def _set_contents_span_result(span: _SpanLike, result: WebSearchResult) -> None:
    span.set_attribute("plotlot.web_contents.status", result.status.value)
    span.set_attribute("plotlot.web_contents.result_count", len(result.results))
