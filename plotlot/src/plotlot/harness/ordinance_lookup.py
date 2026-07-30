from __future__ import annotations

import uuid
from typing import Any

from pydantic import Field

from plotlot.harness.contracts.base import HarnessContract
from plotlot.core.types import SearchResult
from plotlot.land_use.citations import ordinance_citation
from plotlot.land_use.models import EvidenceConfidence, EvidenceItem, SourceType, ToolContext
from plotlot.observability.tracing import start_span
from plotlot.retrieval.search import hybrid_search
from plotlot.storage.db import get_session


class IndexedZoningSearchArgs(HarnessContract):
    municipality: str = Field(min_length=1)
    query: str = Field(min_length=1)
    limit: int = Field(default=8, ge=1, le=25)
    zone_code_boost: str | None = None
    known_zoning_code: str | None = None


def _ev_id() -> str:
    return str(uuid.uuid4())


def _default_project_id(workspace_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"plotlot:{workspace_id}:default_project"))


def _project_id(context: ToolContext) -> str:
    return context.project_id or _default_project_id(context.workspace_id)


def _clean_optional(value: str | None) -> str:
    return (value or "").strip()


def _normalize_municipality_name(value: str) -> str:
    return " ".join(value.casefold().replace("-", " ").split())


def _municipality_match_rank(requested: str, candidate: str) -> int:
    requested_norm = _normalize_municipality_name(requested)
    candidate_norm = _normalize_municipality_name(candidate)
    if requested_norm == candidate_norm:
        return 3
    if (
        requested_norm
        and candidate_norm
        and (requested_norm in candidate_norm or candidate_norm in requested_norm)
    ):
        return 2
    requested_tokens = set(requested_norm.split())
    candidate_tokens = set(candidate_norm.split())
    if requested_tokens and candidate_tokens and requested_tokens & candidate_tokens:
        return 1
    return 0


def _rank_search_result(
    result: SearchResult, *, municipality: str, zone_code_boost: str | None
) -> tuple[int, int, float]:
    municipality_rank = _municipality_match_rank(municipality, result.municipality)
    boosted = int(
        bool(zone_code_boost)
        and zone_code_boost is not None
        and zone_code_boost in (result.zone_codes or [])
    )
    return (municipality_rank, boosted, float(result.score))


def _rerank_search_results(
    results: list[SearchResult],
    *,
    municipality: str,
    zone_code_boost: str | None,
) -> list[SearchResult]:
    return sorted(
        results,
        key=lambda item: _rank_search_result(
            item,
            municipality=municipality,
            zone_code_boost=zone_code_boost,
        ),
        reverse=True,
    )


def _no_results_payload(args: IndexedZoningSearchArgs) -> dict[str, Any]:
    known_zoning_code = _clean_optional(args.known_zoning_code)
    if known_zoning_code:
        guidance = (
            f"The zoning code ({known_zoning_code}) is already confirmed for this parcel "
            "from lookup_property_info — STATE IT PLAINLY. Its dimensional standards are "
            f"simply not yet indexed in the PlotLot database for {args.municipality}. Tell the "
            "user that and offer to ingest the ordinance. Do NOT say the zoning could not "
            "be retrieved, and NEVER fabricate phone numbers, office names, URLs, or "
            "numeric zoning values."
        )
    else:
        guidance = (
            f"No indexed ordinance text for {args.municipality}. Report this honestly and offer "
            "to ingest the municipality's ordinance or run a web_search. NEVER fabricate "
            "phone numbers, office names, URLs, or numeric zoning values."
        )
    return {
        "status": "no_results",
        "message": f"No ordinance sections found for '{args.query}' in {args.municipality}",
        "known_zoning_code": known_zoning_code,
        "presentation_guidance": guidance,
        "results": [],
        "evidence": [],
    }


def _source_url(result: Any) -> str | None:
    source_url = getattr(result, "source_url", None)
    if source_url:
        return str(source_url)
    municode_node_id = getattr(result, "municode_node_id", None)
    if municode_node_id:
        return f"https://api.municode.com/codescontent?nodeId={municode_node_id}"
    return None


def _result_chunk(result: Any, evidence_id: str | None) -> dict[str, Any]:
    source_url = _source_url(result)
    citation = ordinance_citation(
        title=(result.section_title or result.section or "Ordinance section"),
        url=source_url,
        jurisdiction=result.municipality,
        path=[p for p in [getattr(result, "chapter", None), result.section] if p],
        raw_text_for_hash=(
            f"{result.municipality}:{result.section}:{result.section_title}:"
            f"{result.chunk_text[:300]}"
        ),
    )
    chunk: dict[str, Any] = {
        "section": result.section,
        "title": result.section_title,
        "zone_codes": result.zone_codes,
        "text": result.chunk_text,
    }
    if evidence_id is not None:
        chunk["evidence_id"] = evidence_id
        chunk["citation"] = citation.model_dump(mode="json")
    return chunk


def _evidence_item(
    *,
    result: Any,
    args: IndexedZoningSearchArgs,
    context: ToolContext,
    evidence_id: str,
) -> dict[str, Any]:
    source_url = _source_url(result)
    citation = ordinance_citation(
        title=(result.section_title or result.section or "Ordinance section"),
        url=source_url,
        jurisdiction=args.municipality,
        path=[p for p in [getattr(result, "chapter", None), result.section] if p],
        raw_text_for_hash=(
            f"{args.municipality}:{result.section}:{result.section_title}:{result.chunk_text[:300]}"
        ),
    )
    evidence_item = EvidenceItem(
        id=evidence_id,
        workspace_id=context.workspace_id,
        project_id=_project_id(context),
        site_id=context.site_id,
        analysis_id=context.analysis_id,
        analysis_run_id=context.analysis_run_id,
        tool_run_id=context.tool_run_id,
        claim_key="ordinance.chunk",
        payload={
            "municipality": args.municipality,
            "query": args.query,
            "section": result.section,
            "section_title": result.section_title,
            "chunk_text": result.chunk_text,
        },
        source_type=SourceType.ORDINANCE,
        tool_name="search_zoning_ordinance",
        confidence=EvidenceConfidence.MEDIUM,
        citation=citation,
    )
    return evidence_item.model_dump(mode="json")


async def execute_indexed_zoning_search(
    args: IndexedZoningSearchArgs,
    *,
    context: ToolContext | None = None,
) -> dict[str, Any]:
    with start_span(name="indexed_zoning_search", span_type="RETRIEVER") as span:
        span.set_inputs(
            {
                "municipality": args.municipality,
                "query": args.query,
                "limit": args.limit,
                "zone_code_boost": args.zone_code_boost,
            }
        )

        session = await get_session()
        try:
            search_kwargs: dict[str, Any] = {"limit": args.limit}
            boost = _clean_optional(args.zone_code_boost)
            if boost:
                search_kwargs["zone_code_boost"] = boost
            results = await hybrid_search(
                session,
                args.municipality,
                args.query,
                **search_kwargs,
            )
        finally:
            await session.close()

        if not results:
            span.set_outputs({"result_count": 0, "status": "no_results"})
            return _no_results_payload(args)

        results = _rerank_search_results(
            list(results),
            municipality=args.municipality,
            zone_code_boost=boost or None,
        )

        chunks: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        for result in results:
            evidence_id = _ev_id() if context is not None else None
            chunks.append(_result_chunk(result, evidence_id))
            if context is not None and evidence_id is not None:
                evidence.append(
                    _evidence_item(
                        result=result,
                        args=args,
                        context=context,
                        evidence_id=evidence_id,
                    )
                )

        span.set_outputs(
            {
                "result_count": len(results),
                "status": "success",
                "top_sections": [chunk["section"] for chunk in chunks[:5]],
            }
        )
        return {"status": "success", "results": chunks, "evidence": evidence}
