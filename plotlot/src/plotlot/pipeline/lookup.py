"""Address lookup pipeline — deterministic data gathering + agentic analysis.

Architecture:
  Phase 1 (deterministic): geocode → property lookup → zoning search
  Phase 2 (agentic): LLM interprets all collected data, can request more searches

This hybrid approach is more reliable than pure agentic — the data gathering
steps are always the same, so we don't waste LLM turns on orchestration.
The LLM focuses on what it's good at: reasoning over the data.
"""

import asyncio
import hashlib
import json
import logging
import re
import time
from dataclasses import fields as dataclass_fields

from plotlot.core.types import (
    NumericZoningParams,
    SearchResult,
    Setbacks,
    SourceRef,
    ZoningReport,
)
from plotlot.domain.dimensional_standard import DistrictDimensionalStandard
from plotlot.domain.claims import Claim, ClaimKind, ClaimOrigin
from plotlot.observability.tracing import (
    log_dict,
    log_metrics,
    log_params,
    set_tag,
    start_run,
    start_span,
    trace,
)
from plotlot.observability.prompts import get_active_prompt, log_prompt_to_run
from plotlot.pipeline.calculator import calculate_max_units, calculate_max_gla, parse_lot_dimensions
from plotlot.retrieval.geocode import geocode_address
from plotlot.retrieval.property import lookup_property
from plotlot.retrieval.search import hybrid_search
from plotlot.retrieval.zoning_crosswalk import crosswalk_zoning_code
from plotlot.storage.dimensional_standards import get_dimensional_standard
from plotlot.storage.db import get_session

logger = logging.getLogger(__name__)

MAX_ANALYSIS_TURNS = 6
PIPELINE_VERSION = "v2.2"

# Pipeline result cache — 30min TTL (Care Access: 86% cost reduction with caching)
_pipeline_cache: dict[str, tuple["ZoningReport", float]] = {}
PIPELINE_CACHE_TTL = 1800  # 30 minutes

# Generic fallback query when no zoning code is known. The municipality name
# (e.g. "San Jose") has no semantic overlap with ordinance text and returns 0
# results, so we query for generic zoning terms instead.
GENERIC_ZONING_QUERY = "zoning district residential density setbacks height limits parking"


def _format_sources(results: list[SearchResult]) -> list[str]:
    """Render retrieved chunks as citation strings for the report.

    Many municipalities (Tiburon, Oakland, Marin County, …) were ingested with
    only ``section_title`` populated and an empty ``section``. Filtering on
    ``section`` alone dropped EVERY citation for those places, so a grounded
    result (real chunks retrieved, zoning extracted) displayed with zero
    sources — looking unsourced. Include a chunk when EITHER field is present.
    """
    sources: list[str] = []
    for r in results:
        section = (r.section or "").strip()
        title = (r.section_title or "").strip()
        if section and title:
            sources.append(f"{section} — {title}")
        elif section or title:
            sources.append(section or title)
    return sources


# Auto-ingestion guard — don't re-attempt the same municipality within this window.
# Ingestion is an idempotent upsert; the guard only prevents hammering a dead source
# (e.g. a city not on Municode) on every analysis call.
_AUTOINGEST_TTL = 86400.0  # 24h
_autoingest_attempts: dict[str, float] = {}


# Geocodio accuracy levels that indicate a confident location match
ACCEPTABLE_ACCURACY = {"rooftop", "range_interpolation", "nearest_rooftop_match", "point"}


def report_to_dict(report: ZoningReport) -> dict:  # noqa: C901
    """Serialize a ZoningReport to a JSON-safe dict for artifact logging."""
    from typing import Any

    result: dict[str, Any] = {
        "address": report.address,
        "formatted_address": report.formatted_address,
        "municipality": report.municipality,
        "county": report.county,
        "lat": report.lat,
        "lng": report.lng,
        "zoning_district": report.zoning_district,
        "zoning_description": report.zoning_description,
        "allowed_uses": report.allowed_uses,
        "conditional_uses": report.conditional_uses,
        "prohibited_uses": report.prohibited_uses,
        "setbacks": {
            "front": report.setbacks.front if report.setbacks else "",
            "side": report.setbacks.side if report.setbacks else "",
            "rear": report.setbacks.rear if report.setbacks else "",
        },
        "max_height": report.max_height,
        "max_density": report.max_density,
        "floor_area_ratio": report.floor_area_ratio,
        "lot_coverage": report.lot_coverage,
        "min_lot_size": report.min_lot_size,
        "parking_requirements": report.parking_requirements,
        "summary": report.summary,
        "sources": report.sources,
        "confidence": report.confidence,
    }

    if report.numeric_params:
        params = {}
        for f in dataclass_fields(report.numeric_params):
            val = getattr(report.numeric_params, f.name)
            if val is not None:
                params[f.name] = val
        result["numeric_params"] = params
    else:
        result["numeric_params"] = {}

    if report.density_analysis:
        result["density_analysis"] = {
            "max_units": report.density_analysis.max_units,
            "governing_constraint": report.density_analysis.governing_constraint,
            "confidence": report.density_analysis.confidence,
        }
    else:
        result["density_analysis"] = None

    if report.property_record:
        result["property_record"] = {
            "folio": report.property_record.folio,
            "zoning_code": report.property_record.zoning_code,
            "lot_size_sqft": report.property_record.lot_size_sqft,
            "year_built": report.property_record.year_built,
        }
    else:
        result["property_record"] = None

    return result


async def _run_hybrid_search(
    municipality: str,
    query: str,
    limit: int = 15,
    zone_code_boost: str | None = None,
) -> list:
    """Run a single hybrid search with its own DB session."""
    session = await get_session()
    try:
        return await hybrid_search(
            session, municipality, query, limit=limit, zone_code_boost=zone_code_boost
        )
    finally:
        await session.close()


async def _gather_ordinance_sections(
    municipality: str,
    state: str,
    county: str,
    search_query: str,
    *,
    zone_code_boost: str | None = None,
) -> tuple[list, str]:
    """Search indexed ordinances; auto-ingest once on a miss, then re-search.

    This is the self-healing coverage path that makes the MCP/ACP work for any
    municipality whose code is reachable by a source adapter (Municode/PDF/HTML)
    without a manual ``plotlot-ingest`` run. When ingestion is not possible
    (no adapter, empty source) it degrades honestly — the caller still has the
    ArcGIS zoning code and reports the gap instead of fabricating data.

    Returns:
        (search_results, coverage_status) where coverage_status is one of:
          ``"indexed"``        results came from already-indexed data
          ``"auto_ingested"``  ingestion ran and produced results
          ``"ingest_empty"``   ingestion attempted but yielded no usable text
          ``"uncovered"``      no municipality/state available to ingest
    """
    results = await _run_hybrid_search(municipality, search_query, zone_code_boost=zone_code_boost)
    if results:
        return results, "indexed"

    if not municipality.strip() or not state.strip():
        return results, "uncovered"

    # Guard: don't re-ingest the same place repeatedly (esp. dead sources).
    key = f"{municipality.lower().strip()}|{state.lower().strip()}"
    now = time.monotonic()
    last_attempt = _autoingest_attempts.get(key)
    if last_attempt is not None and now - last_attempt < _AUTOINGEST_TTL:
        logger.info("Skipping auto-ingest for %s, %s (attempted recently)", municipality, state)
        return results, "ingest_empty"
    _autoingest_attempts[key] = now

    from plotlot.ingestion.acp_coordinator import IngestRequest, run_on_demand_ingestion

    logger.info("Auto-ingesting %s, %s on zoning search miss", municipality, state)
    final_stage, final_error = "", None
    try:
        async for prog in run_on_demand_ingestion(
            IngestRequest(
                municipality=municipality,
                state=state,
                county=county or None,
                trigger="pipeline_search_miss",
            )
        ):
            final_stage, final_error = prog.stage, prog.error
    except Exception:
        logger.warning("Auto-ingestion crashed for %s, %s", municipality, state, exc_info=True)
        return results, "ingest_empty"

    if final_stage != "complete":
        logger.info(
            "Auto-ingest did not complete for %s, %s (stage=%s error=%s)",
            municipality,
            state,
            final_stage,
            final_error,
        )
        return results, "ingest_empty"

    results = await _run_hybrid_search(municipality, search_query, zone_code_boost=zone_code_boost)
    return results, ("auto_ingested" if results else "ingest_empty")


@trace(name="lookup_address", span_type="CHAIN")
async def lookup_address(address: str) -> ZoningReport | None:
    """Run the full address → zoning report pipeline.

    Phase 1 — Deterministic data gathering:
      1. Geocode address → municipality, county, coordinates
      2. Property Appraiser lookup → folio, zoning code, lot, building info
      3. Hybrid search pgvector → relevant ordinance sections for that zoning code

    Phase 2 — Agentic LLM analysis:
      4. Feed all collected data to LLM with tool access for additional searches
      5. LLM interprets and produces structured ZoningReport with numeric params

    Phase 3 — Deterministic max-units calculation:
      6. Calculator applies zoning math to compute max allowable units

    Returns:
        ZoningReport or None if geocoding fails.
    """
    # Check pipeline cache first
    cache_key = hashlib.sha256(address.strip().lower().encode()).hexdigest()[:16]
    if cache_key in _pipeline_cache:
        cached_report, cached_time = _pipeline_cache[cache_key]
        if time.monotonic() - cached_time < PIPELINE_CACHE_TTL:
            logger.info("Pipeline cache hit for: %s", address[:40])
            return cached_report

    with start_run(run_name=f"lookup_{address[:30]}"):
        log_params({"address": address, "pipeline_version": PIPELINE_VERSION})
        log_prompt_to_run("analysis")

        # ── Phase 1: Deterministic data gathering ──

        # Step 1: Geocode
        geo = await geocode_address(address)
        if not geo:
            logger.error("Geocoding failed for: %s", address)
            set_tag("status", "failed")
            set_tag("failure_reason", "geocoding")
            return None

        municipality = geo["municipality"]
        county = geo["county"]
        state = geo.get("state", "")
        lat = geo.get("lat")
        lng = geo.get("lng")

        logger.info(
            "Geocoded: %s → %s, %s County (%.4f, %.4f)", address, municipality, county, lat, lng
        )

        # Geocoding accuracy check — reject low-confidence matches
        # Geocodio returns numeric `accuracy` (0-1) AND string `accuracy_type`
        accuracy_score = geo.get("accuracy")
        if isinstance(accuracy_score, (int, float)) and accuracy_score < 0.8:
            set_tag("status", "rejected")
            set_tag("failure_reason", "low_accuracy_geocode")
            raise ValueError(
                f"Could not confidently locate this address (geocoding accuracy: {accuracy_score}). "
                f"Please check the address and try again."
            )

        # Step 2: Property Appraiser lookup
        prop_record = await lookup_property(address, county, lat=lat, lng=lng, state=state)

        if prop_record:
            logger.info(
                "Property: folio=%s, zoning=%s, lot=%s sqft, %dbd/%gbth, built %d",
                prop_record.folio,
                prop_record.zoning_code or "N/A",
                prop_record.lot_size_sqft,
                prop_record.bedrooms,
                prop_record.bathrooms,
                prop_record.year_built,
            )
            # Prefer property record's municipality — more accurate than Geocodio
            # (e.g., Geocodio returns "Miami" for addresses in Miami Gardens)
            # Skip abbreviations (Broward uses "MM" for Miramar, "FTL" for Fort Lauderdale)
            if prop_record.municipality:
                pa_muni = prop_record.municipality.strip().title()
                if county.lower() == "miami-dade" and pa_muni == "Unincorporated County":
                    pa_muni = "Unincorporated Miami-Dade"
                if pa_muni and len(pa_muni) > 3 and pa_muni.lower() != municipality.lower():
                    logger.info(
                        "Municipality override: %s → %s (from property record)",
                        municipality,
                        pa_muni,
                    )
                    municipality = pa_muni
                    geo["municipality"] = municipality
        else:
            logger.warning("No property record found for %s in %s County", address, county)

        # Step 3: Hybrid search with self-healing coverage. The GIS layer's zoning
        # code (Track 1) and the ordinance code book (Track 2) often use different
        # labels for the same district — e.g. GIS "RS20" vs. Clark County Title 30
        # "R-E" — so we crosswalk the GIS code to the ordinance code BEFORE searching,
        # else the ingested text never matches. When no crosswalk exists the code is
        # used unchanged. The municipality name alone returns 0 results, so fall back
        # to generic zoning terms when no code is known. On a search miss, auto-ingest
        # the municipality's ordinance via the ACP coordinator and re-search — so the
        # MCP/ACP path works for any source-adapter-reachable place, not just pre-ingested ones.
        gis_zoning_code = prop_record.zoning_code if prop_record else ""
        crosswalk = crosswalk_zoning_code(
            gis_zoning_code, state=state, county=county, municipality=municipality
        )
        if crosswalk.matched:
            logger.info("Zoning crosswalk: %s", crosswalk.note)

        if gis_zoning_code:
            search_query: str = crosswalk.search_code
            zone_boost: str | None = crosswalk.search_code
        else:
            search_query = GENERIC_ZONING_QUERY
            zone_boost = None

        search_results, coverage_status = await _gather_ordinance_sections(
            municipality, state, county, search_query, zone_code_boost=zone_boost
        )

        logger.info(
            "Search: %d chunks for query '%s' in %s (coverage=%s)",
            len(search_results),
            search_query,
            municipality,
            coverage_status,
        )

        # Log Phase 1 results as params
        log_params(
            {
                "county": county,
                "municipality": municipality,
                "has_property_record": str(bool(prop_record)),
                "zoning_code": prop_record.zoning_code
                if prop_record and prop_record.zoning_code
                else "N/A",
                "ordinance_zoning_code": crosswalk.search_code if gis_zoning_code else "N/A",
                "zoning_crosswalk_matched": str(crosswalk.matched),
                "search_result_count": str(len(search_results)),
                "coverage_status": coverage_status,
            }
        )

        # ── Phase 2: Agentic LLM analysis ──

        report: ZoningReport = await _agentic_analysis(
            address=address,
            geo=geo,
            prop_record=prop_record,
            search_results=search_results,
            municipality=municipality,
            county=county,
            ordinance_code=crosswalk.search_code if crosswalk.matched else "",
        )

        # ── Phase 3: Deterministic max-units calculation ──

        if (
            report.numeric_params
            and report.property_record
            and report.property_record.lot_size_sqft > 0
        ):
            from plotlot.pipeline.extraction_verify import is_field_verified

            lot_width, lot_depth = parse_lot_dimensions(
                report.property_record.lot_dimensions or "",
            )
            if report.numeric_params.property_type == "commercial":
                report.density_analysis = calculate_max_gla(
                    lot_size_sqft=report.property_record.lot_size_sqft,
                    params=report.numeric_params,
                    lot_width_ft=lot_width,
                    lot_depth_ft=lot_depth,
                )
                logger.info(
                    "Max GLA: %s sqft (governing: %s, confidence: %s)",
                    report.density_analysis.max_gla_sqft,
                    report.density_analysis.governing_constraint,
                    report.density_analysis.confidence,
                )
            else:
                # San Diego Coastal Height Limit (Prop D) — a 30 ft cap generally
                # west of I-5 that limits stories and can pull units below base
                # zoning. Deterministic point-in-polygon, gated to City of San
                # Diego, CA (a no-op everywhere else). Best-effort: a failure
                # leaves the firm number intact and surfaces a verify-warning
                # rather than silently cutting units. Wiring it here (not just in
                # the SSE route) means the JSON /analyze, batch screening, and the
                # chat analyze_property tool all apply Prop D consistently.
                coastal_height_limit: float | None = None
                try:
                    from plotlot.pipeline.coastal_overlay import fetch_coastal_height_overlay

                    c_lat = report.property_record.lat or lat
                    c_lng = report.property_record.lng or lng
                    if c_lat is not None and c_lng is not None:
                        coastal = await asyncio.wait_for(
                            fetch_coastal_height_overlay(
                                c_lat,
                                c_lng,
                                city=municipality,
                                county=county,
                                state=state,
                            ),
                            timeout=12,
                        )
                        if coastal.status != "not_applicable":
                            report.coastal_overlay = coastal
                        if coastal.applies and coastal.height_limit_ft:
                            coastal_height_limit = coastal.height_limit_ft
                            report.warnings.append(coastal.note)
                        elif coastal.status == "unverified":
                            report.warnings.append(coastal.note)
                except Exception as exc:  # noqa: BLE001 — non-blocking
                    logger.warning("Coastal overlay step skipped: %s", exc)

                # ── Verified-fact path (WIRE-1.1b) ──
                # Before LLM-extracted params, try the typed dimensional
                # standard: a verified-fact row from the ordinance's Schedule
                # of District Regulations, stored at ingestion time. When
                # present, it replaces NumericZoningParams as the calculator
                # input and the result is labeled origin=local_authority
                # (verified-fact grade), not assumption-grade LLM extraction.
                # District code: prefer the crosswalked ordinance code (the
                # code book's label) so the right row is read out of a
                # multi-district dimensional table; fall back to the parcel's
                # GIS zone code, then the LLM-reported district string.
                typed_standard: DistrictDimensionalStandard | None = None
                lookup_codes: list[str] = []
                if crosswalk.matched and crosswalk.search_code:
                    lookup_codes.append(crosswalk.search_code)
                if gis_zoning_code:
                    lookup_codes.append(gis_zoning_code)
                if report.zoning_district:
                    lookup_codes.append(report.zoning_district)
                seen: set[str] = set()
                for code in lookup_codes:
                    key = code.strip().upper()
                    if not key or key in seen:
                        continue
                    seen.add(key)
                    try:
                        typed_standard = await get_dimensional_standard(municipality, code)
                    except Exception as exc:  # noqa: BLE001 — DB may be offline
                        logger.debug(
                            "Dimensional standard lookup failed for %s/%s: %s",
                            municipality,
                            code,
                            exc,
                        )
                        typed_standard = None
                    if typed_standard is not None:
                        logger.info(
                            "Typed dimensional standard found for %s/%s → "
                            "verified-fact density path (origin=local_authority)",
                            municipality,
                            code,
                        )
                        break

                if typed_standard is not None:
                    report.density_analysis = calculate_max_units(
                        lot_size_sqft=report.property_record.lot_size_sqft,
                        params=typed_standard,
                        lot_width_ft=lot_width,
                        lot_depth_ft=lot_depth,
                        height_limit_ft=coastal_height_limit,
                    )
                else:
                    # LLM-extracted fallback (origin=unknown, assumption grade).
                    report.density_analysis = calculate_max_units(
                        lot_size_sqft=report.property_record.lot_size_sqft,
                        params=report.numeric_params,
                        lot_width_ft=lot_width,
                        lot_depth_ft=lot_depth,
                        density_verified=is_field_verified(
                            report.extraction_verification, "max_density_units_per_acre"
                        ),
                        min_lot_area_verified=is_field_verified(
                            report.extraction_verification, "min_lot_area_per_unit_sqft"
                        ),
                        height_limit_ft=coastal_height_limit,
                    )
                logger.info(
                    "Max units: %d (governing: %s, confidence: %s, origin: %s)",
                    report.density_analysis.max_units,
                    report.density_analysis.governing_constraint,
                    report.density_analysis.confidence,
                    report.density_analysis.origin,
                )

        # Log analysis metrics
        confidence_map = {"high": 1.0, "medium": 0.66, "low": 0.33}
        log_metrics(
            {
                "confidence_score": confidence_map.get(report.confidence, 0.0),
                "source_count": float(len(report.sources)),
                "has_numeric_params": 1.0 if report.numeric_params else 0.0,
            }
        )
        if report.density_analysis:
            log_metrics(
                {
                    "max_units": float(report.density_analysis.max_units),
                }
            )

        # Log full report as artifact
        log_dict(report_to_dict(report), "report.json")
        set_tag("status", "success")

        # Cache the result
        _pipeline_cache[cache_key] = (report, time.monotonic())

        return report


@trace(name="agentic_analysis", span_type="AGENT")
async def _agentic_analysis(
    address: str,
    geo: dict,
    prop_record,
    search_results: list,
    municipality: str,
    county: str,
    ordinance_code: str = "",
) -> ZoningReport:
    """LLM analysis with tool access for additional searches."""
    from plotlot.retrieval.llm import call_llm

    # Build context message with all collected data
    context_msg = _build_context_message(
        address, geo, prop_record, search_results, ordinance_code=ordinance_code
    )

    # Tools available during analysis
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_zoning_ordinance",
                "description": (
                    "Search for additional zoning ordinance sections. Use this if you need "
                    "more specific information (e.g., setbacks, parking, height limits, density). "
                    "Use the zoning code or specific topics as the query."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "municipality": {"type": "string"},
                        "query": {
                            "type": "string",
                            "description": "Zoning code or topic to search for",
                        },
                    },
                    "required": ["municipality", "query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "submit_report",
                "description": "Submit the final structured zoning analysis. Call this when ready.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "zoning_district": {"type": "string"},
                        "zoning_description": {"type": "string"},
                        "allowed_uses": {"type": "array", "items": {"type": "string"}},
                        "conditional_uses": {"type": "array", "items": {"type": "string"}},
                        "prohibited_uses": {"type": "array", "items": {"type": "string"}},
                        "setbacks_front": {"type": "string"},
                        "setbacks_side": {"type": "string"},
                        "setbacks_rear": {"type": "string"},
                        "max_height": {"type": "string"},
                        "max_density": {"type": "string"},
                        "floor_area_ratio": {"type": "string"},
                        "lot_coverage": {"type": "string"},
                        "min_lot_size": {"type": "string"},
                        "parking_requirements": {"type": "string"},
                        "summary": {"type": "string"},
                        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                        "max_density_units_per_acre": {
                            "type": "number",
                            "description": "Maximum dwelling units per acre (e.g., 6.0). NUMERIC ONLY.",
                        },
                        "min_lot_area_per_unit_sqft": {
                            "type": "number",
                            "description": "Minimum lot area per dwelling unit in sqft (e.g., 7500). NUMERIC ONLY.",
                        },
                        "far_numeric": {
                            "type": "number",
                            "description": "Floor Area Ratio as decimal (e.g., 0.50). NUMERIC ONLY.",
                        },
                        "max_lot_coverage_pct": {
                            "type": "number",
                            "description": "Maximum lot coverage percentage (e.g., 40.0). NUMERIC ONLY.",
                        },
                        "max_height_ft": {
                            "type": "number",
                            "description": "Maximum building height in feet (e.g., 35.0). NUMERIC ONLY.",
                        },
                        "max_stories": {
                            "type": "integer",
                            "description": "Maximum number of stories (e.g., 2). NUMERIC ONLY.",
                        },
                        "setback_front_ft": {
                            "type": "number",
                            "description": "Front setback in feet (e.g., 25.0). NUMERIC ONLY.",
                        },
                        "setback_side_ft": {
                            "type": "number",
                            "description": "Side setback in feet (e.g., 7.5). NUMERIC ONLY.",
                        },
                        "setback_rear_ft": {
                            "type": "number",
                            "description": "Rear setback in feet (e.g., 25.0). NUMERIC ONLY.",
                        },
                        "min_unit_size_sqft": {
                            "type": "number",
                            "description": "Minimum dwelling unit size in sqft (e.g., 750). NUMERIC ONLY.",
                        },
                        "min_lot_width_ft": {
                            "type": "number",
                            "description": "Minimum lot width/frontage in feet (e.g., 75). NUMERIC ONLY.",
                        },
                        "parking_spaces_per_unit": {
                            "type": "number",
                            "description": "Required parking spaces per dwelling unit (e.g., 2.0). NUMERIC ONLY.",
                        },
                        "parking_per_1000_gla_sqft": {
                            "type": "number",
                            "description": "Parking spaces per 1,000 sqft of GLA for commercial zones. NUMERIC ONLY.",
                        },
                        "max_gla_sqft": {
                            "type": "number",
                            "description": "Maximum gross leasable area in sqft. NUMERIC ONLY.",
                        },
                        "min_tenant_size_sqft": {
                            "type": "number",
                            "description": "Minimum individual tenant space in sqft. NUMERIC ONLY.",
                        },
                        "loading_spaces": {
                            "type": "integer",
                            "description": "Required loading docks/spaces. NUMERIC ONLY.",
                        },
                        "property_type": {
                            "type": "string",
                            "enum": [
                                "land",
                                "single_family",
                                "multifamily",
                                "commercial_mf",
                                "commercial",
                            ],
                            "description": (
                                "Property type based on zoning: "
                                "R-*/RS-*/RE-* → single_family, "
                                "RD-*/RM-*/MF-* with ≤4 units → multifamily, "
                                "RD-*/RM-*/MF-* with 5+ units → commercial_mf, "
                                "C-*/B-*/CI-*/CC-*/BU-*/GC-* → commercial, "
                                "MU-* → commercial_mf, "
                                "vacant/unzoned → land"
                            ),
                        },
                    },
                    "required": ["summary", "confidence"],
                },
            },
        },
    ]

    messages = [
        {"role": "system", "content": _analysis_system_prompt()},
        {"role": "user", "content": context_msg},
    ]

    all_sources = _format_sources(search_results)

    for turn in range(MAX_ANALYSIS_TURNS):
        logger.info("Analysis turn %d/%d", turn + 1, MAX_ANALYSIS_TURNS)

        with start_span(name=f"llm_turn_{turn + 1}", span_type="CHAT_MODEL") as span:
            span.set_inputs({"turn": turn + 1, "message_count": len(messages)})
            response = await call_llm(messages, tools=tools)
            if not response:
                span.set_outputs({"error": "empty_response"})
                logger.error("LLM returned empty on turn %d", turn + 1)
                break
            tool_calls = response.get("tool_calls", [])
            content = response.get("content", "")
            tool_names = [tc.get("function", {}).get("name", "") for tc in tool_calls]
            span.set_outputs(
                {
                    "tool_calls": len(tool_calls),
                    "tool_names": tool_names,
                    "has_content": bool(content),
                    "content_preview": content[:200] if content else "",
                }
            )

        if not tool_calls:
            # Try to parse content as JSON report (some models return JSON directly)
            try:
                parsed = json.loads(content.strip().strip("`").lstrip("json\n"))
                return _build_report(parsed, address, geo, prop_record, all_sources, search_results)
            except (json.JSONDecodeError, ValueError):
                pass

            # Re-prompt to use submit_report tool
            messages.append({"role": "assistant", "content": content})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "You have gathered enough data. Call submit_report NOW with your findings. "
                        "For any field where you did not find explicit text in the retrieved chunks, "
                        "set the value to null (numeric) or empty string (text). "
                        "Do NOT fill in values from general knowledge — null is correct when the "
                        "ordinance text does not state a value. Set confidence based on how many "
                        "fields are supported by retrieved text: high = all key fields found, "
                        "medium = most found, low = critical fields missing. "
                        "You MUST call submit_report immediately."
                    ),
                }
            )
            continue

        messages.append(
            {
                "role": "assistant",
                "content": content,
                "tool_calls": tool_calls,
            }
        )

        for tc in tool_calls:
            fn_name = tc.get("function", {}).get("name", "")
            fn_args_str = tc.get("function", {}).get("arguments", "{}")
            tc_id = tc.get("id", "")

            try:
                fn_args = json.loads(fn_args_str)
            except json.JSONDecodeError:
                fn_args = {}

            if fn_name == "search_zoning_ordinance":
                logger.info("Agent requesting additional search: %s", fn_args.get("query", ""))
                with start_span(name="agent_search", span_type="TOOL") as tool_span:
                    tool_span.set_inputs(fn_args)
                    session = await get_session()
                    try:
                        extra_results = await hybrid_search(
                            session,
                            municipality=fn_args.get("municipality", municipality),
                            zone_code=fn_args.get("query", ""),
                            limit=10,
                        )
                    finally:
                        await session.close()

                    all_sources.extend(_format_sources(extra_results))

                    if extra_results:
                        chunks = [
                            {
                                "section": r.section,
                                "title": r.section_title,
                                "zone_codes": r.zone_codes,
                                "text": r.chunk_text[:800],
                            }
                            for r in extra_results
                        ]
                        tool_result = json.dumps({"status": "success", "chunks": chunks})
                    else:
                        tool_result = json.dumps({"status": "no_results"})

                    tool_span.set_outputs({"result_count": len(extra_results)})
                messages.append({"role": "tool", "tool_call_id": tc_id, "content": tool_result})

            elif fn_name == "submit_report":
                logger.info("Agent submitted report")
                # Deduplicate sources
                all_sources = list(dict.fromkeys(all_sources))
                return _build_report(
                    fn_args, address, geo, prop_record, all_sources, search_results
                )

            else:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": json.dumps({"error": f"Unknown tool: {fn_name}"}),
                    }
                )

    # Fallback
    logger.warning("Agent did not submit report, building fallback")
    return _build_fallback_report(address, geo, prop_record, list(dict.fromkeys(all_sources)))


def _build_context_message(
    address: str,
    geo: dict,
    prop_record,
    search_results: list,
    ordinance_code: str = "",
) -> str:
    """Build the data context for the LLM analysis."""
    parts = [
        f"# Property Analysis: {address}\n",
        "## Geocoding Result",
        f"- Address: {geo['formatted_address']}",
        f"- Municipality: {geo['municipality']}",
        f"- County: {geo['county']}",
        f"- Coordinates: {geo.get('lat')}, {geo.get('lng')}\n",
    ]

    if prop_record:
        parts.append("## Property Record (County Property Appraiser)")
        if prop_record.folio:
            parts.append(f"- Folio: {prop_record.folio}")
        if prop_record.owner:
            parts.append(f"- Owner: {prop_record.owner}")
        if prop_record.zoning_code:
            parts.append(f"- Zoning Code (GIS map label): {prop_record.zoning_code}")
        if ordinance_code and ordinance_code != prop_record.zoning_code:
            parts.append(
                f"- Ordinance District Code: {ordinance_code} — the adopted code book uses "
                f"this label for the same district that the GIS layer labels "
                f"'{prop_record.zoning_code}'. Search the ordinance and report standards "
                f"under '{ordinance_code}'."
            )
        if prop_record.zoning_description:
            parts.append(f"- Zoning Description: {prop_record.zoning_description}")
        if prop_record.land_use_description:
            parts.append(f"- Land Use: {prop_record.land_use_description}")
        if prop_record.lot_size_sqft:
            parts.append(f"- Lot Size: {prop_record.lot_size_sqft:,.0f} sq ft")
        if prop_record.lot_dimensions:
            parts.append(f"- Lot Dimensions: {prop_record.lot_dimensions}")
        if prop_record.bedrooms:
            parts.append(f"- Bedrooms: {prop_record.bedrooms}")
        if prop_record.bathrooms:
            parts.append(f"- Bathrooms: {prop_record.bathrooms:g}")
        if prop_record.floors:
            parts.append(f"- Floors: {prop_record.floors}")
        if prop_record.living_area_sqft:
            parts.append(f"- Living Area: {prop_record.living_area_sqft:,.0f} sq ft")
        if prop_record.building_area_sqft:
            parts.append(f"- Building Area: {prop_record.building_area_sqft:,.0f} sq ft")
        if prop_record.year_built:
            parts.append(f"- Year Built: {prop_record.year_built}")
        if prop_record.assessed_value:
            parts.append(f"- Assessed Value: ${prop_record.assessed_value:,.0f}")
        if prop_record.last_sale_price:
            parts.append(
                f"- Last Sale: ${prop_record.last_sale_price:,.0f} ({prop_record.last_sale_date})"
            )
        parts.append("")
    else:
        parts.append("## Property Record: Not found in county records\n")

    if search_results:
        parts.append(f"## Zoning Ordinance Sections ({len(search_results)} chunks)\n")
        for i, r in enumerate(search_results, 1):
            parts.append(f"### Chunk {i}: {r.section} — {r.section_title}")
            if r.zone_codes:
                parts.append(f"Zone codes: {', '.join(r.zone_codes)}")
            parts.append(f"{r.chunk_text}\n")
    else:
        parts.append("## Zoning Ordinance: No matching sections found\n")

    parts.append(
        "\nAnalyze all the data above. If you need more specific ordinance sections "
        "(e.g., setbacks, parking, height limits), use the search_zoning_ordinance tool. "
        "When ready, call submit_report with your complete analysis."
    )

    return "\n".join(parts)


def _analysis_system_prompt() -> str:
    return get_active_prompt("analysis")


def _coerce_list(val) -> list[str]:
    """Coerce a value to list[str] — handles LLM returning JSON-encoded strings."""
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        val = val.strip()
        if val.startswith("["):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, list):
                    return [str(x) for x in parsed]
            except (json.JSONDecodeError, ValueError):
                pass
        return [val] if val else []
    return []


def _build_source_refs(search_results: list | None) -> list[SourceRef]:
    source_refs: list[SourceRef] = []
    if not search_results:
        return source_refs

    for r in search_results[:5]:
        source_refs.append(
            SourceRef(
                section=r.section or "",
                section_title=r.section_title or "",
                chunk_text_preview=(r.chunk_text or "")[:200],
                score=r.score,
            )
        )
    return source_refs


def _extract_fallback_insights(
    search_results: list | None,
) -> tuple[dict[str, str], NumericZoningParams | None]:
    if not search_results:
        return ({}, None)

    combined = " ".join(r.chunk_text for r in search_results if getattr(r, "chunk_text", ""))
    if not combined:
        return ({}, None)

    text = re.sub(r"\s+", " ", combined)

    def _search_float(*patterns: str) -> float | None:
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1).replace(",", ""))
                except (ValueError, TypeError):
                    continue
        return None

    def _search_int(*patterns: str) -> int | None:
        value = _search_float(*patterns)
        if value is None:
            return None
        return int(value)

    def _search_sentence(*patterns: str) -> str:
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0).strip(" .;")
        return ""

    def _fmt_ft(value: float | None) -> str:
        return f"{value:g} ft" if value is not None else ""

    max_height_ft = _search_float(
        r"(?:maximum|max)\s+height[^.]{0,80}?(\d+(?:\.\d+)?)\s*(?:feet|foot|ft)\b",
        r"height[^.]{0,40}?(\d+(?:\.\d+)?)\s*(?:feet|foot|ft)\b",
    )
    max_density_units = _search_float(
        r"(?:maximum|max)\s+density[^.]{0,80}?(\d+(?:\.\d+)?)\s*(?:dwelling\s+units|units|du)\s*(?:per acre|/acre|du/ac)",
        r"(\d+(?:\.\d+)?)\s*(?:dwelling\s+units|units|du)\s*(?:per acre|/acre|du/ac)",
    )
    far = _search_float(
        r"(?:floor area ratio|\bFAR\b)[^.]{0,40}?(\d+(?:\.\d+)?)",
    )
    lot_coverage_pct = _search_float(
        r"(?:lot coverage|coverage)[^.]{0,60}?(\d+(?:\.\d+)?)\s*%",
    )
    min_lot_area_sqft = _search_float(
        r"(?:minimum|min)\s+lot\s+(?:size|area)[^.]{0,80}?(\d[\d,]*(?:\.\d+)?)\s*(?:square feet|sq\.?\s*ft|sqft)",
        r"lot\s+area\s+per\s+unit[^.]{0,80}?(\d[\d,]*(?:\.\d+)?)\s*(?:square feet|sq\.?\s*ft|sqft)",
    )
    setback_front_ft = _search_float(
        r"front(?:\s+yard)?(?:\s+setback)?[^.]{0,40}?(\d+(?:\.\d+)?)\s*(?:feet|foot|ft)\b"
    )
    setback_side_ft = _search_float(
        r"side(?:\s+yard)?(?:\s+setback)?[^.]{0,40}?(\d+(?:\.\d+)?)\s*(?:feet|foot|ft)\b"
    )
    setback_rear_ft = _search_float(
        r"rear(?:\s+yard)?(?:\s+setback)?[^.]{0,40}?(\d+(?:\.\d+)?)\s*(?:feet|foot|ft)\b"
    )
    parking_spaces_per_unit = _search_float(
        r"(\d+(?:\.\d+)?)\s+spaces?\s+per\s+(?:dwelling\s+)?unit",
    )
    max_stories = _search_int(r"(\d+)\s+stories?\b")
    parking_requirements = _search_sentence(r"[^.]{0,80}parking[^.]{0,120}[.]?")

    extracted: dict[str, str] = {
        "max_height": _fmt_ft(max_height_ft),
        "max_density": f"{max_density_units:g} units/acre" if max_density_units is not None else "",
        "floor_area_ratio": f"{far:g}" if far is not None else "",
        "lot_coverage": f"{lot_coverage_pct:g}%" if lot_coverage_pct is not None else "",
        "min_lot_size": f"{min_lot_area_sqft:,.0f} sqft" if min_lot_area_sqft is not None else "",
        "parking_requirements": parking_requirements,
        "setbacks_front": _fmt_ft(setback_front_ft),
        "setbacks_side": _fmt_ft(setback_side_ft),
        "setbacks_rear": _fmt_ft(setback_rear_ft),
    }

    params = NumericZoningParams(
        max_density_units_per_acre=max_density_units,
        min_lot_area_per_unit_sqft=min_lot_area_sqft,
        far=far,
        max_lot_coverage_pct=lot_coverage_pct,
        max_height_ft=max_height_ft,
        max_stories=max_stories,
        setback_front_ft=setback_front_ft,
        setback_side_ft=setback_side_ft,
        setback_rear_ft=setback_rear_ft,
        parking_spaces_per_unit=parking_spaces_per_unit,
    )
    has_any = any(getattr(params, f.name) is not None for f in params.__dataclass_fields__.values())
    return (extracted, params if has_any else None)


def _extract_claims_from_report(
    args: dict,
    search_results: list | None,
    prop_record,
) -> list[Claim]:
    """Emit typed, provenanced Claims for the zoning facts _agentic_analysis
    extracted (WIRE-2.1b).

    Grounding rule (criterion 2): a fact is ``verified_fact`` / ``origin=
    local_authority`` when sourced from indexed ordinance text
    (``search_results`` non-empty) OR the county GIS zone code
    (``prop_record.zoning_code`` — a local-authority ArcGIS record). Otherwise
    it is LLM-fallback: ``assumption`` / ``origin=unknown``.

    Namespace/boundary rule: ``zoning.*`` is a local-authority namespace, so
    the Claim invariant forbids ``zoning.*`` with ``origin=unknown``. An
    ungrounded LLM district assertion therefore lives under the distinct
    ``assumed_zoning.district`` namespace (``origin=unknown``, ``kind=
    assumption``) — ``zoning.*`` is reserved for local-authority-grounded
    facts. ``standards.*`` is unconstrained and carries whichever origin the
    grounding warrants. ``cost.*`` / ``financing.*`` are never emitted here
    (they come from the pro-forma, not the zoning LLM) and the Claim
    constructor forbids ``cost.*`` as ``verified_fact`` regardless (criterion 3
    holds at the emission point by construction).
    """
    claims: list[Claim] = []

    ordinance_grounded = bool(search_results)
    gis_code = (getattr(prop_record, "zoning_code", "") or "").strip()
    district = (args.get("zoning_district", "") or "").strip() or gis_code
    grounded = ordinance_grounded or bool(gis_code)

    # Source URL for grounded claims (first ordinance source or empty).
    source_url = ""
    if search_results:
        first = search_results[0]
        source_url = getattr(first, "source_url", "") or getattr(first, "url", "") or ""

    # zoning.district (grounded) vs assumed_zoning.district (LLM fallback).
    if district:
        if grounded:
            claims.append(
                Claim(
                    field_key="zoning.district",
                    value=district,
                    kind=ClaimKind.VERIFIED_FACT,
                    origin=ClaimOrigin.LOCAL_AUTHORITY,
                    source_url=source_url,
                    metadata={"grounded_by": "gis_code" if gis_code else "ordinance_text"},
                )
            )
        else:
            # Ungrounded LLM assertion — zoning.* forbids origin=unknown, so it
            # lives under assumed_zoning.* (assumption grade, confidence-capped).
            claims.append(
                Claim(
                    field_key="assumed_zoning.district",
                    value=district,
                    kind=ClaimKind.ASSUMPTION,
                    origin=ClaimOrigin.UNKNOWN,
                    confidence=0.4,
                    metadata={"grounded_by": "llm_fallback"},
                )
            )

    # standards.* — numeric zoning standards. Namespace is unconstrained, so the
    # origin tracks grounding directly (verified_fact/local_authority when
    # grounded, assumption/unknown when LLM fallback).
    std_specs = [
        ("standards.setback_front_ft", "setback_front_ft"),
        ("standards.setback_side_ft", "setback_side_ft"),
        ("standards.setback_rear_ft", "setback_rear_ft"),
        ("standards.max_height_ft", "max_height_ft"),
        ("standards.max_density_units_per_acre", "max_density_units_per_acre"),
        ("standards.min_lot_area_per_unit_sqft", "min_lot_area_per_unit_sqft"),
        ("standards.far", "far_numeric"),
        ("standards.max_lot_coverage_pct", "max_lot_coverage_pct"),
        ("standards.min_lot_width_ft", "min_lot_width_ft"),
        ("standards.parking_spaces_per_unit", "parking_spaces_per_unit"),
    ]
    for field_key, arg_key in std_specs:
        val = args.get(arg_key)
        if val is None:
            continue
        try:
            num = float(val)
            if num <= 0:
                continue
        except (ValueError, TypeError):
            continue
        if grounded:
            claims.append(
                Claim(
                    field_key=field_key,
                    value=num,
                    kind=ClaimKind.VERIFIED_FACT,
                    origin=ClaimOrigin.LOCAL_AUTHORITY,
                    source_url=source_url,
                    metadata={"grounded_by": "gis_code" if gis_code else "ordinance_text"},
                )
            )
        else:
            claims.append(
                Claim(
                    field_key=field_key,
                    value=num,
                    kind=ClaimKind.ASSUMPTION,
                    origin=ClaimOrigin.UNKNOWN,
                    confidence=0.4,
                    metadata={"grounded_by": "llm_fallback"},
                )
            )

    return claims


def _build_report(
    args: dict,
    address: str,
    geo: dict,
    prop_record,
    sources: list[str],
    search_results: list | None = None,
) -> ZoningReport:
    """Build ZoningReport from agent submit_report args."""
    # Build numeric params from LLM-extracted values
    numeric_params = _extract_numeric_params(args)

    # Build source_refs from top search results (for inline citations)
    source_refs = _build_source_refs(search_results)

    # Deterministically verify the LLM's value-drivers against the source text.
    from plotlot.pipeline.extraction_verify import verify_numeric_params

    # Prefer the parcel's authoritative ArcGIS zone code (e.g. "RM-3-7") over the
    # LLM-supplied district string — zone-aware grounding needs the exact code to
    # read the right row out of a multi-zone density table (San Diego lists every
    # RM zone in one chunk, so the wrong code grounds a neighbor's density).
    zone_code = (getattr(prop_record, "zoning_code", "") or "").strip() or args.get(
        "zoning_district", ""
    )
    verification = verify_numeric_params(numeric_params, search_results, zone_code)

    return ZoningReport(
        address=address,
        formatted_address=geo.get("formatted_address", address),
        municipality=geo.get("municipality", ""),
        county=geo.get("county", ""),
        state=geo.get("state", ""),
        lat=geo.get("lat"),
        lng=geo.get("lng"),
        zoning_district=args.get("zoning_district", ""),
        zoning_description=args.get("zoning_description", ""),
        allowed_uses=_coerce_list(args.get("allowed_uses", [])),
        conditional_uses=_coerce_list(args.get("conditional_uses", [])),
        prohibited_uses=_coerce_list(args.get("prohibited_uses", [])),
        setbacks=Setbacks(
            front=args.get("setbacks_front", ""),
            side=args.get("setbacks_side", ""),
            rear=args.get("setbacks_rear", ""),
        ),
        max_height=args.get("max_height", ""),
        max_density=args.get("max_density", ""),
        floor_area_ratio=args.get("floor_area_ratio", ""),
        lot_coverage=args.get("lot_coverage", ""),
        min_lot_size=args.get("min_lot_size", ""),
        parking_requirements=args.get("parking_requirements", ""),
        numeric_params=numeric_params,
        property_record=prop_record,
        summary=args.get("summary", ""),
        sources=sources,
        confidence=args.get("confidence", "low"),
        source_refs=source_refs,
        extraction_verification=verification,
        warnings=list(verification.warnings),
        claims=_extract_claims_from_report(args, search_results, prop_record),
    )


def _extract_numeric_params(args: dict) -> NumericZoningParams | None:
    """Extract NumericZoningParams from submit_report args. Returns None if all empty."""

    def _num(key: str) -> float | None:
        val = args.get(key)
        if val is None:
            return None
        try:
            f = float(val)
            return f if f > 0 else None
        except (ValueError, TypeError):
            return None

    def _int(key: str) -> int | None:
        val = args.get(key)
        if val is None:
            return None
        try:
            i = int(val)
            return i if i > 0 else None
        except (ValueError, TypeError):
            return None

    # Extract property_type — auto-detect from zoning district if not provided
    prop_type = args.get("property_type")
    if not prop_type:
        district = (args.get("zoning_district") or "").upper()
        if any(district.startswith(p) for p in ("R-", "RS-", "RE-")):
            prop_type = "single_family"
        elif any(district.startswith(p) for p in ("RD-", "RM-", "MF-")):
            max_d = _num("max_density_units_per_acre")
            prop_type = "commercial_mf" if max_d and max_d > 12 else "multifamily"
        elif any(district.startswith(p) for p in ("C-", "B-", "MU-", "CI-", "CC-", "BU-", "GC-")):
            # Pure commercial vs mixed-use
            if any(district.startswith(p) for p in ("MU-",)):
                prop_type = "commercial_mf"
            else:
                prop_type = "commercial"

    params = NumericZoningParams(
        max_density_units_per_acre=_num("max_density_units_per_acre"),
        min_lot_area_per_unit_sqft=_num("min_lot_area_per_unit_sqft"),
        far=_num("far_numeric"),
        max_lot_coverage_pct=_num("max_lot_coverage_pct"),
        max_height_ft=_num("max_height_ft"),
        max_stories=_int("max_stories"),
        setback_front_ft=_num("setback_front_ft"),
        setback_side_ft=_num("setback_side_ft"),
        setback_rear_ft=_num("setback_rear_ft"),
        min_unit_size_sqft=_num("min_unit_size_sqft"),
        min_lot_width_ft=_num("min_lot_width_ft"),
        parking_spaces_per_unit=_num("parking_spaces_per_unit"),
        parking_per_1000_gla_sqft=_num("parking_per_1000_gla_sqft"),
        max_gla_sqft=_num("max_gla_sqft"),
        min_tenant_size_sqft=_num("min_tenant_size_sqft"),
        loading_spaces=_int("loading_spaces"),
        property_type=prop_type,
    )

    # Return None if no values were extracted
    has_any = any(getattr(params, f.name) is not None for f in params.__dataclass_fields__.values())
    return params if has_any else None


def _fallback_claims(
    zoning_district: str,
    prop_record,
    search_results: list | None,
) -> list[Claim]:
    """Emit claims for the LLM-didn't-submit fallback path.

    The fallback is grounded in ordinance text (``search_results``) and/or the
    county GIS zone code — both local-authority sources — so the district claim
    is ``verified_fact`` / ``local_authority``. Numeric standards from the
    fallback are string-form (recovered prose), so only the district claim is
    emitted here; numeric standard claims come through ``_build_report``.
    """
    gis_code = (getattr(prop_record, "zoning_code", "") or "").strip()
    grounded = bool(search_results) or bool(gis_code)
    if not zoning_district or not grounded:
        return []
    source_url = ""
    if search_results:
        first = search_results[0]
        source_url = getattr(first, "source_url", "") or getattr(first, "url", "") or ""
    return [
        Claim(
            field_key="zoning.district",
            value=zoning_district,
            kind=ClaimKind.VERIFIED_FACT,
            origin=ClaimOrigin.LOCAL_AUTHORITY,
            source_url=source_url,
            metadata={"grounded_by": "gis_code" if gis_code else "ordinance_text"},
        )
    ]


def _build_fallback_report(
    address: str,
    geo: dict,
    prop_record,
    sources: list[str],
    search_results: list | None = None,
) -> ZoningReport:
    """Build report from collected data when LLM doesn't submit."""
    deduped_sources = list(dict.fromkeys(sources))
    zone_codes = list(
        dict.fromkeys(
            code
            for result in (search_results or [])
            for code in getattr(result, "zone_codes", [])
            if code
        )
    )
    extracted, numeric_params = _extract_fallback_insights(search_results)
    zoning_district = (prop_record.zoning_code if prop_record else "") or (
        zone_codes[0] if zone_codes else ""
    )
    zoning_description = prop_record.zoning_description if prop_record else ""
    summary_bits = []
    if zoning_district:
        summary_bits.append(f"Fallback preserved zoning district {zoning_district}")
    if numeric_params:
        summary_bits.append("Recovered partial dimensional standards from retrieved ordinance text")

    return ZoningReport(
        address=address,
        formatted_address=geo.get("formatted_address", address),
        municipality=geo.get("municipality", ""),
        county=geo.get("county", ""),
        lat=geo.get("lat"),
        lng=geo.get("lng"),
        zoning_district=zoning_district,
        zoning_description=zoning_description,
        setbacks=Setbacks(
            front=extracted.get("setbacks_front", ""),
            side=extracted.get("setbacks_side", ""),
            rear=extracted.get("setbacks_rear", ""),
        ),
        max_height=extracted.get("max_height", ""),
        max_density=extracted.get("max_density", ""),
        floor_area_ratio=extracted.get("floor_area_ratio", ""),
        lot_coverage=extracted.get("lot_coverage", ""),
        min_lot_size=extracted.get("min_lot_size", ""),
        parking_requirements=extracted.get("parking_requirements", ""),
        numeric_params=numeric_params,
        property_record=prop_record,
        summary=("; ".join(summary_bits) + ". " if summary_bits else "")
        + "Automated analysis incomplete. Property data and ordinance sections were retrieved — "
        "see sources below for relevant zoning regulations.",
        sources=deduped_sources,
        confidence="low",
        source_refs=_build_source_refs(search_results),
        claims=_fallback_claims(zoning_district, prop_record, search_results),
    )
