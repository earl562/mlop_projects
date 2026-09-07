"""Default harness runtime wiring.

This is the shared execution seam for REST tool routes and the MCP adapter.
Chat currently uses bespoke tool execution; the long-term goal is to route chat
through this runtime too.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from plotlot.harness.policy import HarnessPolicyEngine
from plotlot.harness.runtime import HarnessRuntime
from plotlot.land_use.models import (
    EvidenceConfidence,
    EvidenceBackedReportSection,
    EvidenceItem,
    OrdinanceJurisdiction,
    OrdinanceSearchArgs,
    ReportClaim,
    SourceType,
    ToolContext,
)
from plotlot.land_use.policy import ToolPolicy


def _ev_id() -> str:
    return str(uuid.uuid4())


def _default_project_id(workspace_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"plotlot:{workspace_id}:default_project"))


def _project_id(context: ToolContext) -> str:
    return context.project_id or _default_project_id(context.workspace_id)


@dataclass
class _RuntimeDataset:
    records: list[dict[str, Any]]
    search_params: dict[str, Any]
    query_description: str
    total_available: int
    fetched_at: str


_RUNTIME_DATASETS: dict[str, _RuntimeDataset] = {}


async def _handle_geocode_address(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    from plotlot.retrieval.geocode import geocode_address
    from plotlot.land_use.citations import geocode_citation

    address = str(args.get("address", "")).strip()
    try:
        result = await geocode_address(address)
    except Exception as e:
        return {"status": "error", "message": f"Geocoding failed: {type(e).__name__}: {e}"}
    if not result:
        return {"status": "not_found", "result": {}}

    ev_id = _ev_id()
    citation = geocode_citation(
        title="Geocoding result",
        publisher="Geocodio/Census",
        raw_text_for_hash=f"{address}:{result.get('lat')}:{result.get('lng')}",
    )
    evidence_item = EvidenceItem(
        id=ev_id,
        workspace_id=context.workspace_id,
        project_id=_project_id(context),
        site_id=context.site_id,
        analysis_id=context.analysis_id,
        analysis_run_id=context.analysis_run_id,
        tool_run_id=context.tool_run_id,
        claim_key="site.geocode",
        payload={"address": address, **result},
        source_type=SourceType.WEB_PAGE,
        tool_name="geocode_address",
        confidence=EvidenceConfidence.MEDIUM,
        citation=citation,
    )

    return {
        "status": "success",
        "result": result,
        "evidence": [evidence_item.model_dump(mode="json")],
    }


async def _handle_lookup_property_info(
    args: dict[str, Any], context: ToolContext
) -> dict[str, Any]:
    from plotlot.retrieval.property import lookup_property
    from plotlot.land_use.citations import county_record_citation

    address = str(args.get("address", "")).strip()
    county = str(args.get("county", "")).strip()
    state = str(args.get("state", "") or "").strip()
    lat = args.get("lat")
    lng = args.get("lng")
    if lat is None or lng is None:
        return {"status": "error", "message": "lat and lng are required"}

    try:
        record = await lookup_property(address, county, lat=float(lat), lng=float(lng), state=state)
    except Exception as e:
        return {"status": "error", "message": f"Property lookup failed: {type(e).__name__}: {e}"}
    if not record:
        return {"status": "not_found", "result": {}}

    property_payload: dict[str, Any] = {
        "folio": record.folio,
        "address": record.address,
        "municipality": record.municipality,
        "county": record.county,
        "owner": record.owner,
        "zoning_code": record.zoning_code,
        "zoning_description": record.zoning_description,
        "lot_size_sqft": record.lot_size_sqft,
        "lot_dimensions": record.lot_dimensions,
        "year_built": record.year_built,
        "assessed_value": record.assessed_value,
        "lat": record.lat,
        "lng": record.lng,
        "zoning_layer_url": record.zoning_layer_url,
    }
    result: dict[str, Any] = {
        "status": "success",
        "result": property_payload,
    }

    ev_id = _ev_id()
    citation = county_record_citation(
        title="County property appraiser record",
        url=record.zoning_layer_url or None,
        jurisdiction=record.county,
        publisher=None,
        raw_text_for_hash=f"{record.folio}:{record.owner}:{record.zoning_code}:{record.lot_size_sqft}",
    )
    evidence_item = EvidenceItem(
        id=ev_id,
        workspace_id=context.workspace_id,
        project_id=_project_id(context),
        site_id=context.site_id,
        analysis_id=context.analysis_id,
        analysis_run_id=context.analysis_run_id,
        tool_run_id=context.tool_run_id,
        claim_key="site.property_record",
        payload=property_payload,
        source_type=SourceType.COUNTY_RECORD,
        tool_name="lookup_property_info",
        confidence=EvidenceConfidence.MEDIUM,
        citation=citation,
    )

    result["evidence"] = [evidence_item.model_dump(mode="json")]
    return result


async def _handle_search_zoning_ordinance(
    args: dict[str, Any], context: ToolContext
) -> dict[str, Any]:
    """Search locally indexed ordinance chunks and return cited results.

    This produces evidence items so downstream reports can reference `evidence_id`s
    rather than uncited prose.
    """

    from plotlot.retrieval.search import hybrid_search
    from plotlot.storage.db import get_session
    from plotlot.land_use.citations import ordinance_citation

    municipality = str(args.get("municipality", "")).strip()
    query = str(args.get("query", "")).strip()

    session = await get_session()
    try:
        results = await hybrid_search(session, municipality, query, limit=8)

        out: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []

        for r in results:
            ev_id = _ev_id()
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
                    "evidence_id": ev_id,
                    "citation": citation.model_dump(mode="json"),
                }
            )
            evidence_item = EvidenceItem(
                id=ev_id,
                workspace_id=context.workspace_id,
                project_id=_project_id(context),
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


async def _handle_search_ordinances(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    """Search locally indexed ordinance chunks and return citation-rich results.

    This is a higher-level, schema-stable tool that maps local chunks into the
    canonical OrdinanceSearchResult shape (heading/path/snippet/citation).
    """

    from plotlot.retrieval.search import hybrid_search
    from plotlot.storage.db import get_session
    from plotlot.land_use.citations import ordinance_citation
    from plotlot.land_use.models import OrdinanceSearchResult

    municipality = str(args.get("municipality", "")).strip()
    query = str(args.get("query", "")).strip()
    limit = int(args.get("limit", 8) or 8)

    session = await get_session()
    try:
        results = await hybrid_search(session, municipality, query, limit=limit)

        out: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []

        for r in results:
            ev_id = _ev_id()
            source_url = getattr(r, "source_url", None)
            municode_node_id = getattr(r, "municode_node_id", None)
            chapter = getattr(r, "chapter", None)
            if not source_url and municode_node_id:
                source_url = f"https://api.municode.com/codescontent?nodeId={municode_node_id}"

            heading = (r.section_title or r.section or "Ordinance section").strip()
            path = [p for p in [chapter, r.section] if p]
            snippet = (r.chunk_text or "").replace("\n", " ").strip()
            snippet = snippet[:300] if snippet else heading

            citation = ordinance_citation(
                title=heading,
                url=source_url,
                jurisdiction=municipality,
                path=path,
                raw_text_for_hash=f"{municipality}:{r.section}:{heading}:{snippet}",
            )

            result = OrdinanceSearchResult(
                section_id=municode_node_id or r.section or None,
                heading=heading,
                path=[p for p in [chapter] if p],
                snippet=snippet or heading,
                citation=citation,
                evidence_id=ev_id,
            )
            out.append(result.model_dump(mode="json"))

            evidence_item = EvidenceItem(
                id=ev_id,
                workspace_id=context.workspace_id,
                project_id=_project_id(context),
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
            )
            evidence.append(evidence_item.model_dump(mode="json"))

        return {"status": "success", "results": out, "evidence": evidence}
    finally:
        await session.close()


async def _handle_fetch_ordinance_section(
    args: dict[str, Any], context: ToolContext
) -> dict[str, Any]:
    """Fetch a locally indexed ordinance section/chunk by section_id.

    This is intentionally conservative: it searches the local chunk index for a
    best match and returns a single cited chunk. It does not perform live
    scraping; use `search_municode_live` for live retrieval.
    """

    from plotlot.retrieval.search import hybrid_search
    from plotlot.storage.db import get_session
    from plotlot.land_use.citations import ordinance_citation

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
        ev_id = _ev_id()
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

        result = {
            "section_id": municode_node_id or r.section or section_id,
            "heading": heading,
            "path": path,
            "text": text,
            "citation": citation.model_dump(mode="json"),
            "evidence_id": ev_id,
        }

        evidence_item = EvidenceItem(
            id=ev_id,
            workspace_id=context.workspace_id,
            project_id=_project_id(context),
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
        )

        return {
            "status": "success",
            "result": result,
            "evidence": [evidence_item.model_dump(mode="json")],
        }
    finally:
        await session.close()


def _is_pdf_scraped(municipality: str) -> bool:
    """True when the municipality is served by a PDF-only adapter (not on Municode).

    Registry-driven (see :func:`pdf_registered_municipalities`), so adding a PDF
    city is a single registry entry — no per-city change here.
    """
    from plotlot.ingestion.adapters.registry import pdf_registered_municipalities

    return municipality.strip().lower() in pdf_registered_municipalities()


async def _indexed_ordinance_fallback(
    args: dict[str, Any], context: ToolContext, municipality: str
) -> dict[str, Any]:
    """Serve indexed ordinance sections when no live Municode authority exists.

    Used for PDF/HTML-sourced cities (e.g. San Diego) and any jurisdiction not on
    Municode. Delegates to the indexed ordinance search so the agent gets real,
    cited ordinance content in ONE call instead of a dead-end redirect. A live
    PDF/HTML re-scrape is deliberately avoided here — it would risk the 30s proxy
    timeout, and the content is already in pgvector. Degrades honestly when nothing
    is indexed: never fabricates sections, values, or URLs.
    """
    indexed = await _handle_search_ordinances({**args, "municipality": municipality}, context)
    if indexed.get("results"):
        indexed["source"] = "indexed"
        indexed["message"] = (
            f"{municipality} is not on Municode; returning indexed ordinance sections "
            "from the local PlotLot database."
        )
        return indexed
    return {
        "status": "no_results",
        "results": [],
        "evidence": [],
        "message": (
            f"{municipality} is not on Municode and has no indexed ordinance text yet. "
            "Ingest the municipality, then use search_zoning_ordinance. Do not fabricate "
            "ordinance sections, numeric values, office names, or URLs."
        ),
    }


async def _handle_search_municode_live(
    args: dict[str, Any], context: ToolContext
) -> dict[str, Any]:
    from plotlot.land_use.ordinances.service import search_municode_live
    from plotlot.ingestion.discovery import (
        discover_municode_authority_for_name,
        get_municode_configs,
        resolve_municode_config,
    )

    municipality = str(args.get("municipality", "")).strip()
    query = str(args.get("query", "")).strip()

    # Known non-Municode (PDF/HTML) source → its ordinance lives in the local index.
    # Serve it directly rather than dead-ending against Municode.
    if _is_pdf_scraped(municipality):
        return await _indexed_ordinance_fallback(args, context, municipality)

    state = str(args.get("state") or "").strip().upper()
    configs = await get_municode_configs()
    config = resolve_municode_config(configs, municipality, state=state)
    if config is None and state:
        config = await discover_municode_authority_for_name(municipality, state)
    if config is None:
        # Not on Municode at all — fall back to the local index so the agent gets
        # real ordinance text (any indexed non-Municode city) instead of nothing.
        return await _indexed_ordinance_fallback(args, context, municipality)

    state = str(state or config.state or "").strip().upper()
    if not state:
        return {
            "status": "error",
            "results": [],
            "evidence": [],
            "message": "state is required (two-letter code)",
        }

    results = await search_municode_live(
        OrdinanceSearchArgs(
            jurisdiction=OrdinanceJurisdiction(state=state, municipality=config.municipality),
            query=query,
            limit=int(args.get("limit", 8) or 8),
        )
    )

    evidence: list[dict[str, Any]] = []
    out: list[dict[str, Any]] = []
    for r in results:
        ev_id = _ev_id()
        r = r.model_copy(update={"evidence_id": ev_id})
        out.append(r.model_dump(mode="json"))
        evidence_item = EvidenceItem(
            id=ev_id,
            workspace_id=context.workspace_id,
            project_id=_project_id(context),
            site_id=context.site_id,
            analysis_id=context.analysis_id,
            analysis_run_id=context.analysis_run_id,
            tool_run_id=context.tool_run_id,
            claim_key="ordinance.section",
            payload={
                "section_id": r.section_id,
                "heading": r.heading,
                "path": r.path,
                "snippet": r.snippet,
            },
            source_type=SourceType.ORDINANCE,
            tool_name="search_municode_live",
            confidence=EvidenceConfidence.MEDIUM,
            citation=r.citation,
        )
        evidence.append(evidence_item.model_dump(mode="json"))

    return {"status": "success", "results": out, "evidence": evidence}


async def _handle_discover_municode_authorities(
    args: dict[str, Any], context: ToolContext
) -> dict[str, Any]:
    from plotlot.ingestion.discovery import (
        discover_county_authorities,
        get_municode_configs,
        normalize_county_key,
    )

    county = str(args.get("county", "")).strip()
    state = str(args.get("state") or "").strip().upper()
    if not county or not state:
        return {
            "status": "error",
            "results": [],
            "evidence": [],
            "message": "county and state are required",
        }

    county_key = normalize_county_key(county)
    configs = await get_municode_configs()
    matches = [
        cfg
        for cfg in configs.values()
        if cfg.state.upper() == state and normalize_county_key(cfg.county) == county_key
    ]

    if not matches:
        live_configs = await discover_county_authorities(state, county=county)
        matches = list(live_configs.values())

    deduped: dict[tuple[str, str], Any] = {}
    for cfg in matches:
        deduped[(cfg.state.upper(), cfg.municipality.lower())] = cfg

    results = [
        {
            "municipality": cfg.municipality,
            "county": cfg.county,
            "state": cfg.state,
            "client_id": cfg.client_id,
            "product_id": cfg.product_id,
            "job_id": cfg.job_id,
            "zoning_node_id": cfg.zoning_node_id,
        }
        for cfg in sorted(deduped.values(), key=lambda item: item.municipality)
    ]

    return {
        "status": "success",
        "results": results,
        "evidence": [],
        "message": f"Found {len(results)} Municode zoning authorities for {county}, {state}",
    }


async def _handle_discover_code_authorities(
    args: dict[str, Any], context: ToolContext
) -> dict[str, Any]:
    from plotlot.land_use.code_providers import discover_code_authorities

    county = str(args.get("county", "")).strip()
    state = str(args.get("state") or "").strip().upper()
    include_web_fallback = bool(args.get("include_web_fallback", True))
    if not county or not state:
        return {
            "status": "error",
            "results": [],
            "evidence": [],
            "message": "county and state are required",
        }

    try:
        authorities = await discover_code_authorities(
            county=county,
            state=state,
            include_web_fallback=include_web_fallback,
        )
    except Exception as exc:
        return {
            "status": "error",
            "results": [],
            "evidence": [],
            "message": f"Code authority discovery failed: {type(exc).__name__}: {exc}",
        }

    return {
        "status": "success",
        "results": [authority.to_dict() for authority in authorities],
        "evidence": [],
        "message": f"Found {len(authorities)} code authority sources for {county}, {state}",
    }


async def _handle_search_code_authority_live(
    args: dict[str, Any], context: ToolContext
) -> dict[str, Any]:
    from plotlot.land_use.code_providers import search_openlegalcodes

    jurisdiction_id = str(args.get("jurisdiction_id") or "").strip()
    query = str(args.get("query") or "").strip()
    limit = int(args.get("limit", 8) or 8)
    if not jurisdiction_id or not query:
        return {
            "status": "error",
            "results": [],
            "evidence": [],
            "message": "jurisdiction_id and query are required",
        }

    try:
        result = await search_openlegalcodes(
            jurisdiction_id=jurisdiction_id,
            query=query,
            limit=limit,
        )
    except Exception as exc:
        return {
            "status": "error",
            "results": [],
            "evidence": [],
            "message": f"Code search failed: {type(exc).__name__}: {exc}",
        }

    return {**result, "evidence": []}


async def _handle_discover_open_data_layers(
    args: dict[str, Any], context: ToolContext
) -> dict[str, Any]:
    from plotlot.land_use.open_data.service import discover_layers
    from plotlot.land_use.models import LayerCandidate

    county = str(args.get("county", "")).strip()
    state = str(args.get("state") or "").strip().upper()
    if not state:
        return {
            "status": "error",
            "results": [],
            "evidence": [],
            "message": "state is required (two-letter code)",
        }
    lat_arg = args.get("lat")
    lng_arg = args.get("lng")
    if lat_arg is None or lng_arg is None:
        return {
            "status": "error",
            "results": [],
            "evidence": [],
            "message": "lat and lng are required",
        }
    lat = float(lat_arg)
    lng = float(lng_arg)

    candidates = await discover_layers(county=county, state=state, lat=lat, lng=lng)

    evidence: list[dict[str, Any]] = []
    out: list[dict[str, Any]] = []
    for c in candidates:
        ev_id = _ev_id()
        c = LayerCandidate.model_validate(c).model_copy(update={"evidence_id": ev_id})
        out.append(c.model_dump(mode="json"))
        evidence_item = EvidenceItem(
            id=ev_id,
            workspace_id=context.workspace_id,
            project_id=_project_id(context),
            site_id=context.site_id,
            analysis_id=context.analysis_id,
            analysis_run_id=context.analysis_run_id,
            tool_run_id=context.tool_run_id,
            claim_key="open_data.layer",
            payload={
                "id": c.id,
                "title": c.title,
                "service_url": str(c.service_url),
                "source_url": str(c.source_url),
                "layer_id": c.layer_id,
                "layer_type": c.layer_type,
            },
            source_type=SourceType.ARCGIS_LAYER,
            tool_name="discover_open_data_layers",
            confidence=c.field_mapping_confidence,
            citation=c.citation,
        )
        evidence.append(evidence_item.model_dump(mode="json"))

    return {"status": "success", "results": out, "evidence": evidence}


async def _handle_generate_document(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    """Generate an internal evidence-backed report artifact.

    This does not perform external writes; it returns artifact payloads for the
    REST adapter to persist into durable tables.
    """

    title = str(args.get("title") or "Evidence-backed report").strip()
    evidence_ids = list(args.get("evidence_ids") or [])
    evidence_ids = [str(e).strip() for e in evidence_ids if str(e).strip()]
    if not evidence_ids:
        return {
            "status": "error",
            "message": "generate_document requires evidence_ids",
            "artifacts": {},
        }

    section = EvidenceBackedReportSection(
        id="sec_evidence",
        title="Evidence",
        evidence_ids=evidence_ids,
        claims=[
            ReportClaim(
                key=f"evidence.{i}",
                text=f"Supported by evidence item {evidence_id}.",
                evidence_ids=[evidence_id],
            )
            for i, evidence_id in enumerate(evidence_ids, start=1)
        ],
    )

    report_json = {
        "title": title,
        "generated_by": "generate_document",
        "sections": [section.model_dump()],
        "evidence_ids": evidence_ids,
    }

    return {
        "status": "success",
        "report": report_json,
        "artifacts": {
            "report": {
                "status": "draft",
                "report_json": report_json,
                "evidence_ids": evidence_ids,
            },
            "document": {
                "document_type": "evidence_report",
                "status": "draft",
                "metadata_json": {"title": title},
            },
        },
    }


async def _handle_draft_google_doc(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    """Create an internal document draft (no external connector write)."""

    title = str(args.get("title", "")).strip() or "Untitled Draft"
    content = str(args.get("content", "") or "").strip()
    evidence_ids = args.get("evidence_ids") or []
    if not isinstance(evidence_ids, list):
        evidence_ids = []

    draft_id = f"draft_doc_{uuid.uuid4()}"
    preview = content[:240]

    return {
        "status": "drafted",
        "draft": {
            "draft_id": draft_id,
            "title": title,
            "content_preview": preview,
            "evidence_ids": evidence_ids,
        },
        "artifacts": {
            "document": {
                "document_type": "google_doc_draft",
                "status": "draft",
                "metadata_json": {
                    "draft_id": draft_id,
                    "title": title,
                    "content": content,
                    "evidence_ids": evidence_ids,
                    "workspace_id": context.workspace_id,
                    "project_id": context.project_id,
                    "site_id": context.site_id,
                },
            }
        },
    }


async def _handle_draft_email(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    """Create an internal outreach email draft (no external connector write)."""

    to_raw = args.get("to") or []
    to_list = to_raw if isinstance(to_raw, list) else [str(to_raw)]
    to_list = [str(addr).strip() for addr in to_list if str(addr).strip()]
    subject = str(args.get("subject", "") or "").strip()
    body = str(args.get("body", "") or "").strip()
    evidence_ids = args.get("evidence_ids") or []
    if not isinstance(evidence_ids, list):
        evidence_ids = []

    draft_id = f"draft_email_{uuid.uuid4()}"
    preview = body[:240]

    return {
        "status": "drafted",
        "draft": {
            "draft_id": draft_id,
            "to": to_list,
            "subject": subject,
            "body_preview": preview,
            "evidence_ids": evidence_ids,
        },
        "artifacts": {
            "document": {
                "document_type": "email_draft",
                "status": "draft",
                "metadata_json": {
                    "draft_id": draft_id,
                    "to": to_list,
                    "subject": subject,
                    "body": body,
                    "evidence_ids": evidence_ids,
                    "workspace_id": context.workspace_id,
                    "project_id": context.project_id,
                    "site_id": context.site_id,
                },
            }
        },
    }


async def _handle_web_search(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    """Search the web through the configured Jina connector."""

    import httpx

    from plotlot.config import settings

    query = str(args.get("query", "") or "").strip()
    if not query:
        return {"status": "error", "results": [], "message": "query is required"}
    if not settings.jina_api_key:
        return {
            "status": "not_configured",
            "results": [],
            "message": "Web search connector is not configured (JINA_API_KEY not set)",
        }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"https://s.jina.ai/{query}",
                headers={
                    "Authorization": f"Bearer {settings.jina_api_key}",
                    "Accept": "application/json",
                    "X-Retain-Images": "none",
                },
            )
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        return {
            "status": "error",
            "results": [],
            "message": f"Web search failed: {type(exc).__name__}: {exc}",
        }

    results = [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "description": str(item.get("description", ""))[:300],
            "content": str(item.get("content", ""))[:500],
        }
        for item in data.get("data", [])[:5]
    ]
    return {"status": "success", "results": results}


async def _handle_search_properties(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    """Search county property datasets and keep results available for this run."""

    from plotlot.retrieval.bulk_search import (
        PropertySearchParams,
        bulk_property_search,
        compute_dataset_stats,
        describe_search,
    )

    ownership_years = args.get("ownership_min_years")
    max_sale_date = None
    if ownership_years:
        cutoff_year = datetime.now(timezone.utc).year - int(ownership_years)
        max_sale_date = f"{cutoff_year}-01-01"

    try:
        params = PropertySearchParams(
            county=str(args["county"]),
            state=args.get("state"),
            lat=args.get("lat"),
            lng=args.get("lng"),
            land_use_type=args.get("land_use_type"),
            city=args.get("city"),
            max_sale_date=max_sale_date,
            min_lot_size_sqft=args.get("min_lot_size_sqft"),
            max_lot_size_sqft=args.get("max_lot_size_sqft"),
            min_sale_price=args.get("min_sale_price"),
            max_sale_price=args.get("max_sale_price"),
            min_assessed_value=args.get("min_assessed_value"),
            max_assessed_value=args.get("max_assessed_value"),
            year_built_before=args.get("year_built_before"),
            year_built_after=args.get("year_built_after"),
            owner_name_contains=args.get("owner_name_contains"),
            max_results=min(int(args.get("max_results", 500) or 500), 2000),
        )
        records = await bulk_property_search(params)
    except Exception as exc:
        return {
            "status": "error",
            "results": [],
            "message": f"Property search failed: {type(exc).__name__}: {exc}",
        }

    dataset = _RuntimeDataset(
        records=records,
        search_params=dict(args),
        query_description=describe_search(args),
        total_available=len(records),
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )
    _RUNTIME_DATASETS[context.run_id] = dataset

    return {
        "status": "success",
        "total_results": len(records),
        "sample": records[:10],
        "stats": compute_dataset_stats(records),
        "dataset_key": context.run_id,
        "message": f"Found {len(records)} properties. Use filter_dataset or export_dataset with the same run_id.",
    }


async def _handle_filter_dataset(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    """Filter/sort the in-memory dataset for this run."""

    from plotlot.retrieval.bulk_search import _safe_filter, compute_dataset_stats

    dataset = _RUNTIME_DATASETS.get(context.run_id)
    if not dataset or not dataset.records:
        return {
            "status": "empty",
            "message": "No dataset in this run. Call search_properties first with the same run_id.",
        }

    records = list(dataset.records)
    expression = str(args.get("filter_expression", "") or "").strip()
    if expression:
        records = _safe_filter(records, expression)

    sort_by = str(args.get("sort_by", "") or "").strip()
    if sort_by and records and sort_by in records[0]:
        reverse = str(args.get("sort_order", "desc")).lower() == "desc"
        records = sorted(records, key=lambda record: record.get(sort_by, 0) or 0, reverse=reverse)

    limit = args.get("limit")
    if limit:
        records = records[: int(limit)]

    _RUNTIME_DATASETS[context.run_id] = _RuntimeDataset(
        records=records,
        search_params=dataset.search_params,
        query_description=f"{dataset.query_description} (filtered)"
        if expression
        else dataset.query_description,
        total_available=dataset.total_available,
        fetched_at=dataset.fetched_at,
    )

    if args.get("summary_only"):
        return {"status": "success", "count": len(records), "stats": compute_dataset_stats(records)}

    return {
        "status": "success",
        "total_after_filter": len(records),
        "sample": records[:10],
        "stats": compute_dataset_stats(records),
        "message": f"Filtered to {len(records)} properties.",
    }


async def _handle_get_dataset_info(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    """Return metadata for the in-memory dataset for this run."""

    from plotlot.retrieval.bulk_search import compute_dataset_stats

    dataset = _RUNTIME_DATASETS.get(context.run_id)
    if not dataset or not dataset.records:
        return {
            "status": "empty",
            "message": "No dataset in this run. Call search_properties first with the same run_id.",
        }

    return {
        "status": "success",
        "count": len(dataset.records),
        "fields": list(dataset.records[0].keys()),
        "search_description": dataset.query_description,
        "fetched_at": dataset.fetched_at,
        "stats": compute_dataset_stats(dataset.records),
        "sample": dataset.records[:5],
    }


async def _handle_create_spreadsheet(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    """Create a Google Sheet after policy approval has already been validated."""

    from plotlot.retrieval.google_workspace import create_spreadsheet

    title = str(args.get("title", "") or "Untitled Spreadsheet").strip()
    headers = [str(header) for header in (args.get("headers") or [])]
    rows = [[str(cell) for cell in row] for row in (args.get("rows") or [])]

    try:
        result = await create_spreadsheet(title, headers, rows)
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Failed to create spreadsheet: {type(exc).__name__}: {exc}",
        }

    return {
        "status": "success",
        "spreadsheet_url": result.spreadsheet_url,
        "title": result.title,
        "row_count": len(rows),
    }


async def _handle_create_document(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    """Create a Google Doc after policy approval has already been validated."""

    from plotlot.retrieval.google_workspace import create_document

    title = str(args.get("title", "") or "Untitled Document").strip()
    content = str(args.get("content", "") or "")

    try:
        result = await create_document(title, content)
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Failed to create document: {type(exc).__name__}: {exc}",
        }

    return {
        "status": "success",
        "document_url": result.document_url,
        "title": result.title,
    }


async def _handle_export_dataset(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    """Export the current run's dataset to Google Sheets after approval."""

    from plotlot.retrieval.google_workspace import create_spreadsheet

    dataset = _RUNTIME_DATASETS.get(context.run_id)
    if not dataset or not dataset.records:
        return {
            "status": "empty",
            "message": "No dataset in this run. Call search_properties first with the same run_id.",
        }

    include_fields = args.get("include_fields") or list(dataset.records[0].keys())
    include_fields = [str(field) for field in include_fields]
    title = str(args.get("title") or f"PlotLot - {dataset.query_description}").strip()
    headers = [field.replace("_", " ").title() for field in include_fields]
    rows = [[str(record.get(field, "")) for field in include_fields] for record in dataset.records]

    try:
        result = await create_spreadsheet(title, headers, rows)
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Failed to export dataset: {type(exc).__name__}: {exc}",
        }

    return {
        "status": "success",
        "spreadsheet_url": result.spreadsheet_url,
        "title": result.title,
        "row_count": len(rows),
    }


async def _handle_gmail_send_draft(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    """Approval-gated seam for Gmail draft sending.

    The policy gate guarantees this handler is reached only with a DB-validated
    approval. The live Gmail send adapter is intentionally not implemented yet,
    so we fail closed without touching an external account.
    """

    draft_id = str(args.get("draft_id", "") or "").strip()
    return {
        "status": "not_configured",
        "result": {"draft_id": draft_id},
        "message": "Gmail send is connected to policy but no live Gmail connector is configured.",
    }


def build_default_runtime() -> HarnessRuntime:
    policy = HarnessPolicyEngine(
        policy=ToolPolicy(
            internal_write_tools=frozenset({"draft_email", "draft_google_doc", "generate_document"})
        )
    )
    runtime = HarnessRuntime(policy=policy)
    runtime.register("geocode_address", _handle_geocode_address)
    runtime.register("lookup_property_info", _handle_lookup_property_info)
    runtime.register("search_zoning_ordinance", _handle_search_zoning_ordinance)
    runtime.register("search_ordinances", _handle_search_ordinances)
    runtime.register("fetch_ordinance_section", _handle_fetch_ordinance_section)
    runtime.register("search_municode_live", _handle_search_municode_live)
    runtime.register("discover_municode_authorities", _handle_discover_municode_authorities)
    runtime.register("discover_code_authorities", _handle_discover_code_authorities)
    runtime.register("search_code_authority_live", _handle_search_code_authority_live)
    runtime.register("discover_open_data_layers", _handle_discover_open_data_layers)
    runtime.register("draft_google_doc", _handle_draft_google_doc)
    runtime.register("draft_email", _handle_draft_email)
    runtime.register("generate_document", _handle_generate_document)
    runtime.register("web_search", _handle_web_search)
    runtime.register("search_properties", _handle_search_properties)
    runtime.register("filter_dataset", _handle_filter_dataset)
    runtime.register("get_dataset_info", _handle_get_dataset_info)
    runtime.register("create_spreadsheet", _handle_create_spreadsheet)
    runtime.register("create_document", _handle_create_document)
    runtime.register("export_dataset", _handle_export_dataset)
    runtime.register("gmail_send_draft", _handle_gmail_send_draft)
    return runtime


_DEFAULT_RUNTIME: HarnessRuntime | None = None


def get_default_runtime() -> HarnessRuntime:
    global _DEFAULT_RUNTIME
    if _DEFAULT_RUNTIME is None:
        _DEFAULT_RUNTIME = build_default_runtime()
    return _DEFAULT_RUNTIME
