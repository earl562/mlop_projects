"""PlotLot MCP Server — 5 tools for zoning analysis and data ingestion.

Run via:
    uv run plotlot-mcp          # stdio transport (Claude Code / Claude Desktop)

Tools
-----
ingest_municipality     Ingest zoning ordinances for any US municipality.
run_full_analysis       Full pipeline: geocode → property → zoning → density → pro forma.
search_zoning           Hybrid search over indexed zoning ordinance text.
get_coverage            Show which municipalities have indexed data and how many chunks.
get_comparable_sales    Find comparable land sales near a lat/lng coordinate.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from sqlalchemy import func, select

import fastmcp

from plotlot.core.types import PropertyRecord
from plotlot.ingestion.acp_coordinator import IngestRequest, run_on_demand_ingestion
from plotlot.pipeline.comps import find_comparables
from plotlot.pipeline.lookup import lookup_address
from plotlot.retrieval.search import hybrid_search
from plotlot.storage.db import get_session
from plotlot.storage.models import OrdinanceChunk

logger = logging.getLogger(__name__)

mcp = fastmcp.FastMCP(
    name="plotlot",
    instructions=(
        "PlotLot: AI-powered land deal intelligence. "
        "Use ingest_municipality when a municipality has no zoning data. "
        "Use run_full_analysis to evaluate any US property address. "
        "Use search_zoning to look up specific zoning provisions. "
        "Use get_coverage to see what municipalities are already indexed. "
        "Use get_comparable_sales to find recent land transactions near a location.\n\n"
        "GROUNDING RULES (strict — never violate):\n"
        "1. Report ONLY values present in tool responses. Never invent zoning codes, "
        "dimensional standards, phone numbers, office names, or URLs.\n"
        "2. run_full_analysis returns a 'data_status' object and 'presentation_guidance' "
        "string — follow that guidance exactly when wording your answer.\n"
        "3. If data_status.zoning_district_found is true, state the zoning district plainly; "
        "do NOT claim the zoning 'could not be retrieved'.\n"
        "4. If data_status.dimensional_standards_found is false, say the standards are not yet "
        "in the database and offer to run ingest_municipality — do NOT fill the gap from general "
        "knowledge.\n"
        "5. When a tool returns an 'error' field, report the error honestly; do not fabricate a "
        "successful-looking answer."
    ),
    version="2.1.0",
)


# ── Tool 1: ingest_municipality ───────────────────────────────────────────────


@mcp.tool
async def ingest_municipality(
    municipality: str,
    state: str,
    county: str | None = None,
) -> dict:
    """Ingest zoning ordinances for a municipality into the PlotLot database.

    Resolves the best data source (Municode API, PDF files, or HTML pages),
    downloads and chunks the zoning text, embeds it, and stores it so future
    search_zoning and run_full_analysis calls can use it.

    Args:
        municipality: City or unincorporated area name (e.g. "Fremont", "San Jose").
        state:        Two-letter state code (e.g. "CA", "FL").
        county:       Optional county name hint to speed up Municode discovery.

    Returns:
        Summary with success flag, chunks_stored, and per-stage progress log.
    """
    request = IngestRequest(
        municipality=municipality,
        state=state,
        county=county,
        trigger="mcp",
    )

    events: list[dict] = []
    async for prog in run_on_demand_ingestion(request):
        events.append(prog.model_dump())
        logger.info("ingest_progress stage=%s message=%s", prog.stage, prog.message)

    final = events[-1] if events else {}
    success = final.get("stage") == "complete"
    chunks_stored = final.get("chunks_done", 0) if success else 0

    return {
        "municipality": municipality,
        "state": state.upper(),
        "county": county,
        "success": success,
        "chunks_stored": chunks_stored,
        "error": final.get("error") if not success else None,
        "progress": events,
    }


# ── Tool 2: run_full_analysis ─────────────────────────────────────────────────


@mcp.tool
async def run_full_analysis(address: str) -> dict:
    """Run the full PlotLot analysis pipeline for a US property address.

    Steps: geocode → ArcGIS property lookup → zoning ordinance search →
    LLM extraction of dimensional standards → density calculator →
    comparable sales → land pro forma.

    Args:
        address: Full US property address (e.g. "1233 Hueneme St, San Diego CA 92110").

    Returns:
        Zoning report with district, numeric parameters, max units, comparable
        sales, and pro forma land value.  Returns {"error": ...} on failure.
    """
    try:
        report = await lookup_address(address)
    except Exception as exc:
        logger.error("run_full_analysis failed address=%s error=%s", address, exc)
        return {"error": str(exc), "address": address}

    if report is None:
        return {
            "error": f"Could not geocode or analyse address: {address}",
            "address": address,
        }

    raw = asdict(report)

    np = raw.get("numeric_params") or {}
    da = raw.get("density_analysis") or {}
    pf = raw.get("pro_forma") or {}

    # ── Data status (anti-hallucination contract) ────────────────────────────
    # Tell the agent EXACTLY what was retrieved vs. what is missing, so it never
    # papers over a partial result with fabricated values, phone numbers, or URLs.
    zoning_found = bool(raw.get("zoning_district"))
    _numeric_fields = (
        "max_density_units_per_acre",
        "min_lot_area_per_unit_sqft",
        "far",
        "max_lot_coverage_pct",
        "max_height_ft",
        "setback_front_ft",
        "setback_side_ft",
        "setback_rear_ft",
    )
    standards_found = any(np.get(f) is not None for f in _numeric_fields)
    ordinance_indexed = bool(raw.get("sources"))
    max_units = da.get("max_units")

    if standards_found:
        coverage = "full"
    elif zoning_found:
        coverage = "zoning_only"
    else:
        coverage = "none"

    if coverage == "full":
        guidance = (
            "Full data available. Present the zoning district, dimensional standards, "
            "and max-units analysis as computed. Cite the retrieved ordinance sections."
        )
    elif coverage == "zoning_only":
        guidance = (
            f"The zoning district ({raw.get('zoning_district')}) and property data below were "
            "retrieved from the county's official GIS and ARE accurate — state them plainly. "
            "Do NOT say the zoning 'could not be retrieved'. The dimensional standards "
            "(setbacks, density, height, FAR) for this district are NOT yet in the PlotLot "
            "database, so max units cannot be computed. Say so honestly and offer to ingest the "
            "ordinance with the ingest_municipality tool. NEVER fabricate phone numbers, office "
            "names, URLs, or numeric zoning values that are not present in this response."
        )
    else:
        guidance = (
            "No zoning district was resolved for this address. State that the official zoning "
            "lookup returned no record and suggest verifying the address. Do NOT invent a zoning "
            "code, phone number, URL, or any dimensional values."
        )

    return {
        "address": address,
        "municipality": raw.get("municipality"),
        "county": raw.get("county"),
        "zoning_district": raw.get("zoning_district"),
        "zoning_description": raw.get("zoning_description"),
        "confidence": raw.get("confidence"),
        "max_density_units_per_acre": np.get("max_density_units_per_acre"),
        "max_height_ft": np.get("max_height_ft"),
        "max_far": np.get("far"),
        "setback_front_ft": np.get("setback_front_ft"),
        "setback_side_ft": np.get("setback_side_ft"),
        "setback_rear_ft": np.get("setback_rear_ft"),
        "min_lot_area_sqft": np.get("min_lot_area_per_unit_sqft"),
        "max_units": max_units,
        "governing_constraint": da.get("governing_constraint"),
        "max_land_price": pf.get("max_land_price"),
        "cost_per_door": pf.get("cost_per_door"),
        "data_status": {
            "coverage": coverage,
            "zoning_district_found": zoning_found,
            "dimensional_standards_found": standards_found,
            "ordinance_text_indexed": ordinance_indexed,
            "max_units_computed": bool(max_units),
        },
        "presentation_guidance": guidance,
        "full_report": raw,
    }


# ── Tool 3: search_zoning ─────────────────────────────────────────────────────


@mcp.tool
async def search_zoning(
    municipality: str,
    query: str,
    limit: int = 10,
) -> dict:
    """Search the indexed zoning ordinance text for a municipality.

    Uses hybrid search (vector similarity + BM25 full-text with RRF fusion) to
    find the most relevant zoning sections for a given query.

    Args:
        municipality: Name of the municipality to search (e.g. "San Diego").
        query:        Search query — can be a zone code, question, or keyword
                      (e.g. "RM-3 density", "maximum building height", "setback requirements").
        limit:        Number of results to return (1–25, default 10).

    Returns:
        List of matching ordinance chunks with section titles, zone codes, and scores.
        Returns empty results list when the municipality has no indexed data.
    """
    limit = max(1, min(25, limit))

    session = await get_session()
    try:
        results = await hybrid_search(session, municipality, query, limit=limit)
    except Exception as exc:
        logger.error("search_zoning failed municipality=%s error=%s", municipality, exc)
        return {
            "municipality": municipality,
            "query": query,
            "error": str(exc),
            "results": [],
        }
    finally:
        await session.close()

    return {
        "municipality": municipality,
        "query": query,
        "result_count": len(results),
        "results": [
            {
                "section": r.section,
                "section_title": r.section_title,
                "chapter": r.chapter,
                "zone_codes": r.zone_codes,
                "score": round(r.score, 4),
                "chunk_text": r.chunk_text,
                "source_url": r.source_url,
            }
            for r in results
        ],
    }


# ── Tool 4: get_coverage ──────────────────────────────────────────────────────


@mcp.tool
async def get_coverage() -> dict:
    """Return zoning ordinance coverage statistics for all indexed municipalities.

    Shows which municipalities have indexed data, how many chunks they have,
    and the state/county breakdown. Use this to decide whether to call
    ingest_municipality before run_full_analysis.

    Returns:
        Coverage summary with total municipalities, total chunks, and per-municipality
        breakdown sorted by chunk count descending.
    """
    session = await get_session()
    try:
        result = await session.execute(
            select(
                OrdinanceChunk.municipality,
                OrdinanceChunk.county,
                OrdinanceChunk.state,
                func.count().label("chunks"),
            )
            .group_by(
                OrdinanceChunk.municipality,
                OrdinanceChunk.county,
                OrdinanceChunk.state,
            )
            .order_by(func.count().desc())
        )
        rows = result.fetchall()
    except Exception as exc:
        logger.error("get_coverage failed error=%s", exc)
        return {"error": str(exc), "municipalities": [], "total_chunks": 0}
    finally:
        await session.close()

    total_chunks = sum(r.chunks for r in rows)
    return {
        "total_municipalities": len(rows),
        "total_chunks": total_chunks,
        "municipalities": [
            {
                "municipality": r.municipality,
                "county": r.county,
                "state": r.state,
                "chunks": r.chunks,
            }
            for r in rows
        ],
    }


# ── Tool 5: get_comparable_sales ──────────────────────────────────────────────


@mcp.tool
async def get_comparable_sales(
    lat: float,
    lng: float,
    county: str,
    state: str = "FL",
    radius_miles: float = 3.0,
) -> dict:
    """Find comparable land sales near a location.

    Resolves a sales dataset for the county (curated source → ArcGIS Hub) and
    computes price-per-acre, ADV per unit, and estimated land value.

    Args:
        lat:          Latitude of the subject property.
        lng:          Longitude of the subject property.
        county:       County name (REQUIRED — the sales dataset is keyed by county;
                      an empty county is why this previously always returned nothing).
        state:        Two-letter state code (e.g. "CA", "FL").
        radius_miles: Search radius in miles (default 3.0).

    Returns:
        List of comparable sales with prices, dates, and per-acre/per-unit metrics.
        Returns empty comparables list when no sales data is available.
    """
    if not county or not county.strip():
        return {
            "lat": lat,
            "lng": lng,
            "state": state,
            "error": "county is required to locate a comparable-sales dataset",
            "comparables": [],
        }
    prop = PropertyRecord(county=county.strip())
    prop.lat = lat
    prop.lng = lng

    try:
        result = await find_comparables(prop, state=state)
    except Exception as exc:
        logger.error("get_comparable_sales failed lat=%s lng=%s error=%s", lat, lng, exc)
        return {
            "lat": lat,
            "lng": lng,
            "state": state,
            "error": str(exc),
            "comparables": [],
        }

    comp_data = asdict(result)
    return {
        "lat": lat,
        "lng": lng,
        "county": county.strip(),
        "state": state,
        "comparable_count": len(result.comparables),
        "median_price_per_acre": comp_data.get("median_price_per_acre"),
        "price_per_acre_low": comp_data.get("price_per_acre_low"),
        "price_per_acre_high": comp_data.get("price_per_acre_high"),
        "estimated_land_value": comp_data.get("estimated_land_value"),
        "estimated_land_value_low": comp_data.get("estimated_land_value_low"),
        "estimated_land_value_high": comp_data.get("estimated_land_value_high"),
        "adv_per_unit": comp_data.get("adv_per_unit"),
        "adv_per_unit_low": comp_data.get("adv_per_unit_low"),
        "adv_per_unit_high": comp_data.get("adv_per_unit_high"),
        "adv_source": comp_data.get("adv_source"),
        "confidence": comp_data.get("confidence"),
        "comparables": comp_data.get("comparables", []),
        "unit_comparables": comp_data.get("unit_comparables", []),
    }


# ── Server entry point ────────────────────────────────────────────────────────


def run() -> None:
    """Start the MCP server (stdio transport for Claude Code / Claude Desktop)."""
    mcp.run()
