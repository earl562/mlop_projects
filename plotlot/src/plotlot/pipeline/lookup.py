"""Address lookup pipeline — deterministic data gathering + agentic analysis.

Architecture:
  Phase 1 (deterministic): geocode → property lookup → zoning search
  Phase 2 (agentic): LLM interprets all collected data, can request more searches

This hybrid approach is more reliable than pure agentic — the data gathering
steps are always the same, so we don't waste LLM turns on orchestration.
The LLM focuses on what it's good at: reasoning over the data.
"""

import hashlib
import json
import logging
import time
from dataclasses import fields as dataclass_fields

from plotlot.core.types import NumericZoningParams, Setbacks, ZoningReport
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
from plotlot.pipeline.calculator import calculate_max_units, parse_lot_dimensions
from plotlot.retrieval.geocode import geocode_address
from plotlot.retrieval.property import lookup_property
from plotlot.retrieval.search import hybrid_search
from plotlot.storage.db import get_session

logger = logging.getLogger(__name__)

MAX_ANALYSIS_TURNS = 3
PIPELINE_VERSION = "v2.2"

# Pipeline result cache — 30min TTL (Care Access: 86% cost reduction with caching)
_pipeline_cache: dict[str, tuple["ZoningReport", float]] = {}
PIPELINE_CACHE_TTL = 1800  # 30 minutes

# Geographic boundary — PlotLot covers South Florida tri-county area only
VALID_COUNTIES = {"miami-dade", "broward", "palm beach"}

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
        lat = geo.get("lat")
        lng = geo.get("lng")

        logger.info("Geocoded: %s → %s, %s County (%.4f, %.4f)", address, municipality, county, lat, lng)

        # Boundary enforcement — reject addresses outside our coverage area
        county_lower = county.lower() if county else ""
        if county_lower not in VALID_COUNTIES:
            set_tag("status", "rejected")
            set_tag("failure_reason", "outside_coverage")
            raise ValueError(
                f"Address is in {county} County. "
                f"PlotLot covers Miami-Dade, Broward, and Palm Beach counties only."
            )

        # Geocoding accuracy check — reject low-confidence matches
        # Geocodio returns numeric `accuracy` (0-1) AND string `accuracy_type`
        accuracy_score = geo.get("accuracy")
        accuracy_type = str(geo.get("accuracy_type", "")).lower()
        if isinstance(accuracy_score, (int, float)) and accuracy_score < 0.8:
            set_tag("status", "rejected")
            set_tag("failure_reason", "low_accuracy_geocode")
            raise ValueError(
                f"Could not confidently locate this address (geocoding accuracy: {accuracy_score}). "
                f"Please check the address and try again."
            )

        # Step 2: Property Appraiser lookup
        prop_record = await lookup_property(address, county, lat=lat, lng=lng)

        if prop_record:
            logger.info(
                "Property: folio=%s, zoning=%s, lot=%s sqft, %dbd/%gbth, built %d",
                prop_record.folio, prop_record.zoning_code or "N/A",
                prop_record.lot_size_sqft, prop_record.bedrooms,
                prop_record.bathrooms, prop_record.year_built,
            )
            # Prefer property record's municipality — more accurate than Geocodio
            # (e.g., Geocodio returns "Miami" for addresses in Miami Gardens)
            # Skip abbreviations (Broward uses "MM" for Miramar, "FTL" for Fort Lauderdale)
            if prop_record.municipality:
                pa_muni = prop_record.municipality.strip().title()
                if pa_muni and len(pa_muni) > 3 and pa_muni.lower() != municipality.lower():
                    logger.info("Municipality override: %s → %s (from property record)", municipality, pa_muni)
                    municipality = pa_muni
                    geo["municipality"] = municipality
        else:
            logger.warning("No property record found for %s in %s County", address, county)

        # Step 3: Hybrid search — use actual zoning code if we have it, else municipality
        search_query = prop_record.zoning_code if prop_record and prop_record.zoning_code else municipality
        session = await get_session()
        try:
            search_results = await hybrid_search(session, municipality, search_query, limit=15)
        finally:
            await session.close()

        logger.info("Search: %d chunks for query '%s' in %s", len(search_results), search_query, municipality)

        # Log Phase 1 results as params
        log_params({
            "county": county,
            "municipality": municipality,
            "has_property_record": str(bool(prop_record)),
            "zoning_code": prop_record.zoning_code if prop_record and prop_record.zoning_code else "N/A",
            "search_result_count": str(len(search_results)),
        })

        # ── Phase 2: Agentic LLM analysis ──

        report: ZoningReport = await _agentic_analysis(
            address=address,
            geo=geo,
            prop_record=prop_record,
            search_results=search_results,
            municipality=municipality,
            county=county,
        )

        # ── Phase 3: Deterministic max-units calculation ──

        if report.numeric_params and report.property_record and report.property_record.lot_size_sqft > 0:
            lot_width, lot_depth = parse_lot_dimensions(
                report.property_record.lot_dimensions or "",
            )
            report.density_analysis = calculate_max_units(
                lot_size_sqft=report.property_record.lot_size_sqft,
                params=report.numeric_params,
                lot_width_ft=lot_width,
                lot_depth_ft=lot_depth,
            )
            logger.info(
                "Max units: %d (governing: %s, confidence: %s)",
                report.density_analysis.max_units,
                report.density_analysis.governing_constraint,
                report.density_analysis.confidence,
            )

        # Log analysis metrics
        confidence_map = {"high": 1.0, "medium": 0.66, "low": 0.33}
        log_metrics({
            "confidence_score": confidence_map.get(report.confidence, 0.0),
            "source_count": float(len(report.sources)),
            "has_numeric_params": 1.0 if report.numeric_params else 0.0,
        })
        if report.density_analysis:
            log_metrics({
                "max_units": float(report.density_analysis.max_units),
            })

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
) -> ZoningReport:
    """LLM analysis with tool access for additional searches."""
    from plotlot.retrieval.llm import call_llm

    # Build context message with all collected data
    context_msg = _build_context_message(address, geo, prop_record, search_results)

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
                        "query": {"type": "string", "description": "Zoning code or topic to search for"},
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

    all_sources = [
        f"{r.section} — {r.section_title}" for r in search_results if r.section
    ]

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
            tool_names = [
                tc.get("function", {}).get("name", "")
                for tc in tool_calls
            ]
            span.set_outputs({
                "tool_calls": len(tool_calls),
                "tool_names": tool_names,
                "has_content": bool(content),
                "content_preview": content[:200] if content else "",
            })

        if not tool_calls:
            # Try to parse content as JSON report (some models return JSON directly)
            try:
                parsed = json.loads(content.strip().strip("`").lstrip("json\n"))
                return _build_report(parsed, address, geo, prop_record, all_sources)
            except (json.JSONDecodeError, ValueError):
                pass

            # Re-prompt to use submit_report tool
            messages.append({"role": "assistant", "content": content})
            messages.append({
                "role": "user",
                "content": (
                    "STOP searching. Call the submit_report tool NOW with your analysis. "
                    "Fill in all fields using the data you have. If some data is missing, "
                    "use your expert knowledge and set confidence accordingly. "
                    "You MUST call submit_report immediately."
                ),
            })
            continue

        messages.append({
            "role": "assistant",
            "content": content,
            "tool_calls": tool_calls,
        })

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

                    all_sources.extend([
                        f"{r.section} — {r.section_title}" for r in extra_results if r.section
                    ])

                    if extra_results:
                        chunks = [{
                            "section": r.section,
                            "title": r.section_title,
                            "zone_codes": r.zone_codes,
                            "text": r.chunk_text[:800],
                        } for r in extra_results]
                        tool_result = json.dumps({"status": "success", "chunks": chunks})
                    else:
                        tool_result = json.dumps({"status": "no_results"})

                    tool_span.set_outputs({"result_count": len(extra_results)})
                messages.append({"role": "tool", "tool_call_id": tc_id, "content": tool_result})

            elif fn_name == "submit_report":
                logger.info("Agent submitted report")
                # Deduplicate sources
                all_sources = list(dict.fromkeys(all_sources))
                return _build_report(fn_args, address, geo, prop_record, all_sources)

            else:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": json.dumps({"error": f"Unknown tool: {fn_name}"}),
                })

    # Fallback
    logger.warning("Agent did not submit report, building fallback")
    return _build_fallback_report(address, geo, prop_record, list(dict.fromkeys(all_sources)))


def _build_context_message(address: str, geo: dict, prop_record, search_results: list) -> str:
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
            parts.append(f"- Zoning Code: {prop_record.zoning_code}")
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
            parts.append(f"- Last Sale: ${prop_record.last_sale_price:,.0f} ({prop_record.last_sale_date})")
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


def _build_report(args: dict, address: str, geo: dict, prop_record, sources: list[str]) -> ZoningReport:
    """Build ZoningReport from agent submit_report args."""
    # Build numeric params from LLM-extracted values
    numeric_params = _extract_numeric_params(args)

    return ZoningReport(
        address=address,
        formatted_address=geo.get("formatted_address", address),
        municipality=geo.get("municipality", ""),
        county=geo.get("county", ""),
        lat=geo.get("lat"),
        lng=geo.get("lng"),
        zoning_district=args.get("zoning_district", ""),
        zoning_description=args.get("zoning_description", ""),
        allowed_uses=args.get("allowed_uses", []),
        conditional_uses=args.get("conditional_uses", []),
        prohibited_uses=args.get("prohibited_uses", []),
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
    )

    # Return None if no values were extracted
    has_any = any(
        getattr(params, f.name) is not None
        for f in params.__dataclass_fields__.values()
    )
    return params if has_any else None


def _build_fallback_report(
    address: str, geo: dict, prop_record, sources: list[str],
) -> ZoningReport:
    """Build report from collected data when LLM doesn't submit."""
    return ZoningReport(
        address=address,
        formatted_address=geo.get("formatted_address", address),
        municipality=geo.get("municipality", ""),
        county=geo.get("county", ""),
        lat=geo.get("lat"),
        lng=geo.get("lng"),
        zoning_district=prop_record.zoning_code if prop_record else "",
        zoning_description=prop_record.zoning_description if prop_record else "",
        property_record=prop_record,
        summary="Automated analysis incomplete. Property data and ordinance sections were retrieved — "
                "see sources below for relevant zoning regulations.",
        sources=sources,
        confidence="low",
    )
