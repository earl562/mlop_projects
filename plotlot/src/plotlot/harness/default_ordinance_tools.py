from __future__ import annotations

from typing import Any

from plotlot.harness.default_runtime_support import ev_id, project_id
from plotlot.land_use.models import (
    EvidenceConfidence,
    EvidenceItem,
    SourceType,
    ToolContext,
)


async def handle_search_zoning_ordinance(
    args: dict[str, Any], context: ToolContext
) -> dict[str, Any]:
    from plotlot.land_use.citations import ordinance_citation
    from plotlot.retrieval.search import hybrid_search
    from plotlot.storage.db import get_session

    municipality = str(args.get("municipality", "")).strip()
    query = str(args.get("query", "")).strip()
    zone_code_boost = str(args.get("zone_code_boost", "") or "").strip() or None

    session = await get_session()
    try:
        results = await hybrid_search(
            session, municipality, query, limit=15, zone_code_boost=zone_code_boost
        )
        out: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        for r in results:
            evidence_id = ev_id()
            source_url = getattr(r, "source_url", None)
            municode_node_id = getattr(r, "municode_node_id", None)
            if not source_url and municode_node_id:
                source_url = f"https://api.municode.com/codescontent?nodeId={municode_node_id}"

            citation = ordinance_citation(
                title=(r.section_title or r.section or "Ordinance section"),
                url=source_url,
                jurisdiction=municipality,
                path=[p for p in [getattr(r, "chapter", None), r.section] if p],
                raw_text_for_hash=f"{municipality}:{r.section}:{r.section_title}:{r.chunk_text[:300]}",
            )
            out.append(
                {
                    "section": r.section,
                    "title": r.section_title,
                    "zone_codes": r.zone_codes,
                    "text": r.chunk_text,
                    "evidence_id": evidence_id,
                    "citation": citation.model_dump(mode="json"),
                }
            )
            evidence_item = EvidenceItem(
                id=evidence_id,
                workspace_id=context.workspace_id,
                project_id=project_id(context),
                site_id=context.site_id,
                analysis_id=context.analysis_id,
                analysis_run_id=context.analysis_run_id,
                tool_run_id=context.tool_run_id,
                claim_key="ordinance.chunk",
                payload={
                    "municipality": municipality,
                    "query": query,
                    "section": r.section,
                    "section_title": r.section_title,
                    "chunk_text": r.chunk_text,
                },
                source_type=SourceType.ORDINANCE,
                tool_name="search_zoning_ordinance",
                confidence=EvidenceConfidence.MEDIUM,
                citation=citation,
            )
            evidence.append(evidence_item.model_dump(mode="json"))
        return {"status": "success", "results": out, "evidence": evidence}
    finally:
        await session.close()


async def handle_search_ordinances(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    from plotlot.land_use.citations import ordinance_citation
    from plotlot.land_use.models import OrdinanceSearchResult
    from plotlot.retrieval.search import hybrid_search
    from plotlot.storage.db import get_session

    municipality = str(args.get("municipality", "")).strip()
    query = str(args.get("query", "")).strip()
    limit = int(args.get("limit", 8) or 8)

    session = await get_session()
    try:
        results = await hybrid_search(session, municipality, query, limit=limit)
        out: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        for r in results:
            evidence_id = ev_id()
            source_url = getattr(r, "source_url", None)
            municode_node_id = getattr(r, "municode_node_id", None)
            chapter = getattr(r, "chapter", None)
            if not source_url and municode_node_id:
                source_url = f"https://api.municode.com/codescontent?nodeId={municode_node_id}"

            heading = (r.section_title or r.section or "Ordinance section").strip()
            snippet = (r.chunk_text or "").replace("\n", " ").strip()
            snippet = snippet[:300] if snippet else heading
            citation = ordinance_citation(
                title=heading,
                url=source_url,
                jurisdiction=municipality,
                path=[p for p in [chapter, r.section] if p],
                raw_text_for_hash=f"{municipality}:{r.section}:{heading}:{snippet}",
            )
            result = OrdinanceSearchResult(
                section_id=municode_node_id or r.section or None,
                heading=heading,
                path=[p for p in [chapter] if p],
                snippet=snippet or heading,
                citation=citation,
                evidence_id=evidence_id,
            )
            out.append(result.model_dump(mode="json"))
            evidence.append(
                EvidenceItem(
                    id=evidence_id,
                    workspace_id=context.workspace_id,
                    project_id=project_id(context),
                    site_id=context.site_id,
                    analysis_id=context.analysis_id,
                    analysis_run_id=context.analysis_run_id,
                    tool_run_id=context.tool_run_id,
                    claim_key="ordinance.search_result",
                    payload={
                        "municipality": municipality,
                        "query": query,
                        "section": r.section,
                        "section_title": r.section_title,
                        "chunk_text": r.chunk_text,
                    },
                    source_type=SourceType.ORDINANCE,
                    tool_name="search_ordinances",
                    confidence=EvidenceConfidence.MEDIUM,
                    citation=citation,
                ).model_dump(mode="json")
            )
        return {"status": "success", "results": out, "evidence": evidence}
    finally:
        await session.close()


async def handle_fetch_ordinance_section(
    args: dict[str, Any], context: ToolContext
) -> dict[str, Any]:
    from plotlot.land_use.citations import ordinance_citation
    from plotlot.retrieval.search import hybrid_search
    from plotlot.storage.db import get_session

    municipality = str(args.get("municipality", "")).strip()
    section_id = str(args.get("section_id", "")).strip()
    if not section_id:
        return {
            "status": "error",
            "result": {},
            "evidence": [],
            "message": "section_id is required",
        }

    session = await get_session()
    try:
        candidates = await hybrid_search(session, municipality, section_id, limit=3)
        if not candidates:
            return {
                "status": "no_results",
                "result": {},
                "evidence": [],
                "message": f"No local ordinance chunks found for {section_id}",
            }
        r = candidates[0]
        evidence_id = ev_id()
        source_url = getattr(r, "source_url", None)
        municode_node_id = getattr(r, "municode_node_id", None)
        chapter = getattr(r, "chapter", None)
        if not source_url and municode_node_id:
            source_url = f"https://api.municode.com/codescontent?nodeId={municode_node_id}"

        heading = (r.section_title or r.section or "Ordinance section").strip()
        path = [p for p in [chapter, r.section] if p]
        text = (r.chunk_text or "").strip()
        snippet = text.replace("\n", " ")[:300].strip() or heading
        citation = ordinance_citation(
            title=heading,
            url=source_url,
            jurisdiction=municipality,
            path=path,
            raw_text_for_hash=f"{municipality}:{section_id}:{heading}:{snippet}",
        )
        return {
            "status": "success",
            "result": {
                "section_id": municode_node_id or r.section or section_id,
                "heading": heading,
                "path": path,
                "text": text,
                "citation": citation.model_dump(mode="json"),
                "evidence_id": evidence_id,
            },
            "evidence": [
                EvidenceItem(
                    id=evidence_id,
                    workspace_id=context.workspace_id,
                    project_id=project_id(context),
                    site_id=context.site_id,
                    analysis_id=context.analysis_id,
                    analysis_run_id=context.analysis_run_id,
                    tool_run_id=context.tool_run_id,
                    claim_key="ordinance.section",
                    payload={
                        "municipality": municipality,
                        "section_id": section_id,
                        "section": r.section,
                        "section_title": r.section_title,
                        "chunk_text": r.chunk_text,
                    },
                    source_type=SourceType.ORDINANCE,
                    tool_name="fetch_ordinance_section",
                    confidence=EvidenceConfidence.MEDIUM,
                    citation=citation,
                ).model_dump(mode="json")
            ],
        }
    finally:
        await session.close()
