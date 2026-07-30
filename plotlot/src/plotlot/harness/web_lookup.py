from __future__ import annotations

import hashlib
import uuid
from typing import Final

from pydantic import HttpUrl, TypeAdapter

from plotlot.harness.contracts import JsonObject
from plotlot.harness.web_lookup_clients import (
    execute_jina_web_search,
    execute_web_contents,
    execute_web_search,
)
from plotlot.harness.web_lookup_models import (
    WebLookupStatus,
    WebSearchProvider,
    WebSearchResult,
    WebSearchResultItem,
)
from plotlot.land_use.models import (
    EvidenceCitation,
    EvidenceConfidence,
    EvidenceItem,
    SourceType,
    ToolContext,
)

JsonObjectAdapter = TypeAdapter(JsonObject)
HttpUrlAdapter = TypeAdapter(HttpUrl)
_DEFAULT_PROJECT_NAMESPACE: Final = "plotlot:{workspace_id}:default_project"

__all__ = [
    "WebLookupStatus",
    "WebSearchProvider",
    "WebSearchResult",
    "WebSearchResultItem",
    "execute_jina_web_search",
    "execute_web_contents",
    "execute_web_search",
    "enrich_web_search_payload",
    "web_contents_payload",
    "web_search_payload",
]


def enrich_web_search_payload(
    payload: JsonObject,
    *,
    query: str,
    context: ToolContext,
    project_id: str,
) -> JsonObject:
    return _enrich_web_lookup_payload(
        payload,
        query=query,
        context=context,
        project_id=project_id,
        tool_name="web_search",
        claim_key="web.search_result",
    )


def _enrich_web_lookup_payload(
    payload: JsonObject,
    *,
    query: str,
    context: ToolContext,
    project_id: str,
    tool_name: str,
    claim_key: str,
) -> JsonObject:
    result = WebSearchResult.model_validate(payload)
    if result.status != WebLookupStatus.SUCCESS or not result.results:
        return payload

    enriched_results: list[JsonObject] = []
    evidence_payloads: list[JsonObject] = []
    for index, item in enumerate(result.results):
        evidence_id = str(uuid.uuid4())
        citation = _web_search_citation(
            query=query,
            item=item,
            provider=result.provider,
        )
        evidence = EvidenceItem(
            id=evidence_id,
            workspace_id=context.workspace_id,
            project_id=project_id,
            site_id=context.site_id,
            analysis_id=context.analysis_id,
            analysis_run_id=context.analysis_run_id,
            tool_run_id=context.tool_run_id,
            claim_key=claim_key,
            payload={
                "query": query,
                "position": index,
                "title": item.title,
                "url": item.url,
                "description": item.description,
                "content": item.content,
                "provider": result.provider.value,
            },
            source_type=SourceType.WEB_PAGE,
            tool_name=tool_name,
            confidence=EvidenceConfidence.LOW,
            citation=citation,
        )
        result_item = JsonObjectAdapter.validate_python(item.model_dump(mode="json"))
        result_item["evidence_id"] = evidence_id
        result_item["citation"] = citation.model_dump(mode="json")
        enriched_results.append(result_item)
        evidence_payloads.append(
            JsonObjectAdapter.validate_python(evidence.model_dump(mode="json"))
        )

    enriched_payload = JsonObjectAdapter.validate_python(result.model_dump(mode="json"))
    return JsonObjectAdapter.validate_python(
        {
            **enriched_payload,
            "results": enriched_results,
            "evidence": evidence_payloads,
        }
    )


def web_search_payload(
    result: WebSearchResult,
    *,
    query: str,
    context: ToolContext | None = None,
) -> JsonObject:
    payload = JsonObjectAdapter.validate_python(
        _normalized_result_payload(result).model_dump(mode="json", exclude_none=True)
    )
    if context is None:
        return _with_exa_only_policy(payload)
    return _with_exa_only_policy(
        enrich_web_search_payload(
            payload,
            query=query,
            context=context,
            project_id=_project_id_for_context(context),
        )
    )


def web_contents_payload(
    result: WebSearchResult,
    *,
    urls: list[str],
    context: ToolContext | None = None,
) -> JsonObject:
    payload = JsonObjectAdapter.validate_python(
        _normalized_result_payload(result).model_dump(mode="json", exclude_none=True)
    )
    if context is None:
        return _with_exa_only_policy(payload)
    return _with_exa_only_policy(
        _enrich_web_lookup_payload(
            payload,
            query=" ".join(urls),
            context=context,
            project_id=_project_id_for_context(context),
            tool_name="fetch_web_contents",
            claim_key="web.content_result",
        )
    )


def _project_id_for_context(context: ToolContext) -> str:
    if context.project_id:
        return context.project_id
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            _DEFAULT_PROJECT_NAMESPACE.format(workspace_id=context.workspace_id),
        )
    )


def _web_search_citation(
    *,
    query: str,
    item: WebSearchResultItem,
    provider: WebSearchProvider,
) -> EvidenceCitation:
    raw_hash = hashlib.sha256(
        f"{provider.value}:{query}:{item.url}:{item.title}:{item.content}".encode("utf-8")
    ).hexdigest()
    return EvidenceCitation(
        source_type=SourceType.WEB_PAGE,
        title=item.title or item.url or query,
        url=HttpUrlAdapter.validate_python(item.url) if item.url else None,
        jurisdiction=None,
        publisher=_publisher(provider),
        raw_source_hash=raw_hash,
    )


def _publisher(provider: WebSearchProvider) -> str:
    match provider:
        case WebSearchProvider.EXA:
            return "Exa Search"
        case WebSearchProvider.JINA | WebSearchProvider.AUTO:
            return "Exa Search"


def _normalized_result_payload(result: WebSearchResult) -> WebSearchResult:
    if result.provider is not WebSearchProvider.JINA:
        return result
    return result.model_copy(update={"provider": WebSearchProvider.EXA})


def _with_exa_only_policy(payload: JsonObject) -> JsonObject:
    return JsonObjectAdapter.validate_python(
        {
            **payload,
            "provider_policy": "exa_only",
            "legacy_provider_aliases": ["jina"],
        }
    )
