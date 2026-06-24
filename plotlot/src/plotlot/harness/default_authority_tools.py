from __future__ import annotations

from typing import Any

from plotlot.harness.default_runtime_support import ev_id, project_id
from plotlot.land_use.models import EvidenceItem, SourceType, ToolContext


async def handle_discover_municode_authorities(
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
        matches = list((await discover_county_authorities(state, county=county)).values())

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


async def handle_discover_code_authorities(
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


async def handle_search_code_authority_live(
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
            jurisdiction_id=jurisdiction_id, query=query, limit=limit
        )
    except Exception as exc:
        return {
            "status": "error",
            "results": [],
            "evidence": [],
            "message": f"Code search failed: {type(exc).__name__}: {exc}",
        }
    return {**result, "evidence": []}


async def handle_discover_open_data_layers(
    args: dict[str, Any], context: ToolContext
) -> dict[str, Any]:
    from plotlot.land_use.models import LayerCandidate
    from plotlot.land_use.open_data.service import discover_layers

    county = str(args.get("county", "")).strip()
    state = str(args.get("state") or "").strip().upper()
    if not state:
        return {"status": "error", "results": [], "evidence": [], "message": "state is required"}
    lat_arg = args.get("lat")
    lng_arg = args.get("lng")
    if lat_arg is None or lng_arg is None:
        return {
            "status": "error",
            "results": [],
            "evidence": [],
            "message": "lat and lng are required",
        }

    candidates = await discover_layers(
        county=county, state=state, lat=float(lat_arg), lng=float(lng_arg)
    )
    evidence: list[dict[str, Any]] = []
    out: list[dict[str, Any]] = []
    for candidate in candidates:
        evidence_id = ev_id()
        layer = LayerCandidate.model_validate(candidate).model_copy(
            update={"evidence_id": evidence_id}
        )
        out.append(layer.model_dump(mode="json"))
        evidence.append(
            EvidenceItem(
                id=evidence_id,
                workspace_id=context.workspace_id,
                project_id=project_id(context),
                site_id=context.site_id,
                analysis_id=context.analysis_id,
                analysis_run_id=context.analysis_run_id,
                tool_run_id=context.tool_run_id,
                claim_key="open_data.layer",
                payload={
                    "id": layer.id,
                    "title": layer.title,
                    "service_url": str(layer.service_url),
                    "source_url": str(layer.source_url),
                    "layer_id": layer.layer_id,
                    "layer_type": layer.layer_type,
                },
                source_type=SourceType.ARCGIS_LAYER,
                tool_name="discover_open_data_layers",
                confidence=layer.field_mapping_confidence,
                citation=layer.citation,
            ).model_dump(mode="json")
        )
    return {"status": "success", "results": out, "evidence": evidence}
