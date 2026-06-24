from __future__ import annotations

import sys
from typing import Any

from plotlot.harness.default_ordinance_tools import handle_search_ordinances
from plotlot.harness.default_runtime_support import ev_id, project_id
from plotlot.land_use.models import (
    EvidenceConfidence,
    EvidenceItem,
    OrdinanceJurisdiction,
    OrdinanceSearchArgs,
    SourceType,
    ToolContext,
)


def is_pdf_scraped(municipality: str) -> bool:
    from plotlot.ingestion.adapters.registry import pdf_registered_municipalities

    return municipality.strip().lower() in pdf_registered_municipalities()


async def indexed_ordinance_fallback(
    args: dict[str, Any], context: ToolContext, municipality: str
) -> dict[str, Any]:
    default_runtime = sys.modules.get("plotlot.harness.default_runtime")
    search_ordinances = getattr(
        default_runtime, "_handle_search_ordinances", handle_search_ordinances
    )
    indexed = await search_ordinances({**args, "municipality": municipality}, context)
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


async def handle_search_municode_live(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    from plotlot.ingestion.discovery import (
        discover_municode_authority_for_name,
        get_municode_configs,
        resolve_municode_config,
    )
    from plotlot.land_use.ordinances.service import search_municode_live

    municipality = str(args.get("municipality", "")).strip()
    query = str(args.get("query", "")).strip()
    if is_pdf_scraped(municipality):
        return await indexed_ordinance_fallback(args, context, municipality)

    state = str(args.get("state") or "").strip().upper()
    configs = await get_municode_configs()
    config = resolve_municode_config(configs, municipality, state=state)
    if config is None and state:
        config = await discover_municode_authority_for_name(municipality, state)
    if config is None:
        return await indexed_ordinance_fallback(args, context, municipality)

    state = str(state or config.state or "").strip().upper()
    if not state:
        return {"status": "error", "results": [], "evidence": [], "message": "state is required"}

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
        evidence_id = ev_id()
        r = r.model_copy(update={"evidence_id": evidence_id})
        out.append(r.model_dump(mode="json"))
        evidence.append(
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
                    "section_id": r.section_id,
                    "heading": r.heading,
                    "path": r.path,
                    "snippet": r.snippet,
                },
                source_type=SourceType.ORDINANCE,
                tool_name="search_municode_live",
                confidence=EvidenceConfidence.MEDIUM,
                citation=r.citation,
            ).model_dump(mode="json")
        )
    return {"status": "success", "results": out, "evidence": evidence}
