"""Conversational agent endpoint — PlotLot's agentic chat with tools and memory.

The agent has:
- Rich personality with passion for helping people build their communities
- Tools: search_zoning_ordinance (local DB), web_search (Jina.ai),
         create_spreadsheet (Google Sheets), create_document (Google Docs)
- Conversation memory persisted in-memory (upgradeable to DB)
- Full context from any active ZoningReport

Uses SSE streaming for real-time token delivery + tool status events.
"""

import json
import logging
import time
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from plotlot.api.schemas import ChatRequest
from plotlot.config import settings
from plotlot.retrieval.bulk_search import (
    DatasetInfo,
    PropertySearchParams,
    bulk_property_search,
    compute_dataset_stats,
    describe_search,
    _safe_filter,
)
from plotlot.retrieval.google_workspace import create_document, create_spreadsheet
from plotlot.retrieval.llm import call_llm
from plotlot.retrieval.search import hybrid_search
from plotlot.storage.db import get_session
from plotlot.observability.prompts import get_active_prompt
from plotlot.observability.tracing import start_span

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["chat"])

# ---------------------------------------------------------------------------
# Session management — bounded memory store with LRU eviction
# ---------------------------------------------------------------------------

MAX_MEMORY_MESSAGES = 50   # Keep last 50 messages per session
MAX_AGENT_TURNS = 8        # Max tool-use loops per chat message
MAX_TOKENS_PER_SESSION = 50_000  # Cost cap — prevent runaway token spend
MAX_SESSIONS = 100         # Max concurrent sessions in memory (Render 512MB)
SESSION_TTL_SECONDS = 3600  # Evict sessions idle for 1 hour


class SessionStore:
    """Bounded in-memory session store with LRU eviction and TTL.

    Prevents unbounded memory growth on Render's 512MB free tier.
    When max_sessions is reached, the least-recently-accessed session
    is evicted. Sessions idle for >TTL are garbage-collected on access.
    """

    def __init__(self, max_sessions: int = MAX_SESSIONS, ttl: int = SESSION_TTL_SECONDS):
        self._max = max_sessions
        self._ttl = ttl
        self._conversations: dict[str, list[dict]] = {}
        self._datasets: dict[str, DatasetInfo | None] = {}
        self._geocode: dict[str, dict] = {}
        self._tokens: dict[str, int] = {}
        self._last_access: dict[str, float] = {}

    def touch(self, session_id: str) -> None:
        """Update last-access time and evict stale sessions if at capacity."""
        self._last_access[session_id] = time.monotonic()
        self._gc()

    def _gc(self) -> None:
        """Evict expired sessions, then LRU if still over capacity."""
        now = time.monotonic()
        # TTL eviction
        expired = [
            sid for sid, ts in self._last_access.items()
            if now - ts > self._ttl
        ]
        for sid in expired:
            self._evict(sid)

        # LRU eviction if still over capacity
        while len(self._last_access) > self._max:
            oldest = min(self._last_access, key=self._last_access.get)  # type: ignore[arg-type]
            self._evict(oldest)

    def _evict(self, session_id: str) -> None:
        self._conversations.pop(session_id, None)
        self._datasets.pop(session_id, None)
        self._geocode.pop(session_id, None)
        self._tokens.pop(session_id, None)
        self._last_access.pop(session_id, None)

    def get_messages(self, session_id: str) -> list[dict]:
        self.touch(session_id)
        return self._conversations.setdefault(session_id, [])

    def get_dataset(self, session_id: str) -> DatasetInfo | None:
        return self._datasets.get(session_id)

    def set_dataset(self, session_id: str, data: DatasetInfo | None) -> None:
        self._datasets[session_id] = data

    def get_geocode(self, session_id: str) -> dict | None:
        return self._geocode.get(session_id)

    def set_geocode(self, session_id: str, data: dict) -> None:
        self._geocode[session_id] = data

    def get_tokens(self, session_id: str) -> int:
        return self._tokens.get(session_id, 0)

    def add_tokens(self, session_id: str, count: int) -> None:
        self._tokens[session_id] = self._tokens.get(session_id, 0) + count

    def has_dataset(self, session_id: str) -> bool:
        return bool(self._datasets.get(session_id))

    def delete_session(self, session_id: str) -> bool:
        found = session_id in self._last_access
        self._evict(session_id)
        return found

    def list_sessions(self) -> dict:
        return {
            sid: {
                "message_count": len(self._conversations.get(sid, [])),
                "last_message": (
                    self._conversations[sid][-1]["content"][:80]
                    if self._conversations.get(sid) else ""
                ),
                "tokens_used": self._tokens.get(sid, 0),
            }
            for sid in self._last_access
        }


_sessions = SessionStore()

# ---------------------------------------------------------------------------
# Agent personality
# ---------------------------------------------------------------------------

AGENT_SYSTEM_PROMPT = get_active_prompt("chat_agent")


def _build_report_context(report) -> str:
    """Summarize the ZoningReport for the agent's context."""
    if not report:
        return ""

    parts = [
        "\n\n## Active Property Analysis",
        f"- Address: {report.formatted_address}",
        f"- Municipality: {report.municipality}, {report.county} County",
        f"- Zoning: {report.zoning_district} — {report.zoning_description}",
    ]

    if report.setbacks:
        parts.append(f"- Setbacks: Front={report.setbacks.front}, Side={report.setbacks.side}, Rear={report.setbacks.rear}")
    if report.max_height:
        parts.append(f"- Max Height: {report.max_height}")
    if report.max_density:
        parts.append(f"- Max Density: {report.max_density}")
    if report.floor_area_ratio:
        parts.append(f"- FAR: {report.floor_area_ratio}")
    if report.lot_coverage:
        parts.append(f"- Lot Coverage: {report.lot_coverage}")
    if report.parking_requirements:
        parts.append(f"- Parking: {report.parking_requirements}")

    if report.density_analysis:
        da = report.density_analysis
        parts.append(f"- Max Units: {da.max_units} (governing: {da.governing_constraint}, confidence: {da.confidence})")
        for c in da.constraints:
            gov = " [GOVERNING]" if c.is_governing else ""
            parts.append(f"  - {c.name}: {c.max_units} units — {c.formula}{gov}")

    if report.property_record:
        pr = report.property_record
        parts.append(f"- Lot Size: {pr.lot_size_sqft:,.0f} sqft")
        if pr.lot_dimensions:
            parts.append(f"- Lot Dimensions: {pr.lot_dimensions}")
        if pr.year_built:
            parts.append(f"- Year Built: {pr.year_built}")
        if pr.assessed_value:
            parts.append(f"- Assessed Value: ${pr.assessed_value:,.0f}")

    if report.numeric_params:
        np_ = report.numeric_params
        params = []
        if np_.max_density_units_per_acre is not None:
            params.append(f"density={np_.max_density_units_per_acre} units/acre")
        if np_.min_lot_area_per_unit_sqft is not None:
            params.append(f"min_lot={np_.min_lot_area_per_unit_sqft} sqft/unit")
        if np_.far is not None:
            params.append(f"FAR={np_.far}")
        if np_.max_lot_coverage_pct is not None:
            params.append(f"coverage={np_.max_lot_coverage_pct}%")
        if np_.max_height_ft is not None:
            params.append(f"height={np_.max_height_ft}ft")
        if np_.max_stories is not None:
            params.append(f"stories={np_.max_stories}")
        if params:
            parts.append(f"- Numeric Params: {', '.join(params)}")

    if report.allowed_uses:
        parts.append(f"- Allowed Uses: {', '.join(report.allowed_uses[:10])}")
    if report.summary:
        parts.append(f"- Summary: {report.summary}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Tool definitions for the LLM
# ---------------------------------------------------------------------------

CHAT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "geocode_address",
            "description": (
                "MANDATORY Step 1 of 3 for ANY address. Returns municipality, "
                "county, lat, lng. ALWAYS follow with lookup_property_info (Step 2) "
                "to get the zoning code, then search_zoning_ordinance (Step 3)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {
                        "type": "string",
                        "description": "Full street address (e.g., '117 NE 171st St, Miami, FL')",
                    },
                },
                "required": ["address"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_property_info",
            "description": (
                "MANDATORY second step after geocode_address. Looks up a specific property's "
                "record from the county Property Appraiser (ArcGIS). Returns the EXACT zoning "
                "code (e.g. RS-1, T4-L, B-2), lot size, owner, assessed value, and building "
                "info. You MUST call this to get the zoning code before searching ordinances."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {
                        "type": "string",
                        "description": "Full street address from geocode result",
                    },
                    "county": {
                        "type": "string",
                        "enum": ["Miami-Dade", "Broward", "Palm Beach"],
                        "description": "County from geocode result",
                    },
                    "lat": {
                        "type": "number",
                        "description": "Latitude from geocode result (needed for spatial zoning query)",
                    },
                    "lng": {
                        "type": "number",
                        "description": "Longitude from geocode result (needed for spatial zoning query)",
                    },
                },
                "required": ["address", "county", "lat", "lng"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_zoning_ordinance",
            "description": (
                "Search zoning ordinance text for SPECIFIC regulations. Use AFTER "
                "lookup_property_info — search for the EXACT zoning code returned by the "
                "property lookup (e.g. 'RS-1 setbacks' or 'T4-L density'). "
                "Searches 3,000+ ordinance chunks across 104 municipalities."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "municipality": {
                        "type": "string",
                        "description": "Municipality name (e.g., 'Miami Gardens', 'Fort Lauderdale')",
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query — zoning code, topic, or regulation to look up",
                    },
                },
                "required": ["municipality", "query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "LAST RESORT — ONLY use when search_zoning_ordinance returns nothing "
                "relevant. For current events, market data, or municipal news not in "
                "the local database."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Web search query",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_spreadsheet",
            "description": (
                "Create a Google Sheets spreadsheet with structured data. "
                "Use this when the user asks to put data into a spreadsheet, "
                "export results, or create a table they can share or download. "
                "Returns a shareable link to the new spreadsheet."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Title for the spreadsheet (e.g., 'Vacant Lots in Miami-Dade')",
                    },
                    "headers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Column headers (e.g., ['Address', 'Zoning', 'Lot Size', 'Max Units'])",
                    },
                    "rows": {
                        "type": "array",
                        "items": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "description": "Data rows — each row is an array of string values matching the headers",
                    },
                },
                "required": ["title", "headers", "rows"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_document",
            "description": (
                "Create a Google Docs document with text content. "
                "Use this when the user asks for a written report, summary document, "
                "analysis writeup, or any formatted text output they can share or download. "
                "Returns a shareable link to the new document."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Title for the document (e.g., 'Zoning Analysis: 171 NE 209th Ter')",
                    },
                    "content": {
                        "type": "string",
                        "description": "Text content for the document. Use newlines for paragraphs.",
                    },
                },
                "required": ["title", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_properties",
            "description": (
                "Search county property databases for properties matching criteria. "
                "Use this when users ask to find, discover, or search for properties — "
                "vacant lots, properties owned for a long time, properties in a price range, etc. "
                "Results are stored in session for further filtering, analysis, or export."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "county": {
                        "type": "string",
                        "enum": ["Miami-Dade", "Broward", "Palm Beach"],
                        "description": "County to search in (required)",
                    },
                    "land_use_type": {
                        "type": "string",
                        "enum": [
                            "vacant_residential", "vacant_commercial",
                            "single_family", "multifamily", "commercial",
                            "industrial", "agricultural",
                        ],
                        "description": "Type of land use to filter by",
                    },
                    "city": {
                        "type": "string",
                        "description": "Municipality/city name to filter by (e.g., 'MIAMI GARDENS', 'MIRAMAR')",
                    },
                    "ownership_min_years": {
                        "type": "number",
                        "description": "Minimum years of current ownership (e.g., 20 means last sold before 2006)",
                    },
                    "min_lot_size_sqft": {"type": "number", "description": "Minimum lot size in square feet"},
                    "max_lot_size_sqft": {"type": "number", "description": "Maximum lot size in square feet"},
                    "min_sale_price": {"type": "number", "description": "Minimum last deed transfer price (what current owner paid)"},
                    "max_sale_price": {"type": "number", "description": "Maximum last deed transfer price (what current owner paid)"},
                    "min_assessed_value": {"type": "number", "description": "Minimum county tax assessed value in dollars"},
                    "max_assessed_value": {"type": "number", "description": "Maximum county tax assessed value in dollars"},
                    "year_built_before": {"type": "integer", "description": "Year built before (0 for vacant land)"},
                    "year_built_after": {"type": "integer", "description": "Year built after"},
                    "owner_name_contains": {"type": "string", "description": "Owner name contains this text"},
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default 500, max 2000)",
                    },
                },
                "required": ["county"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "filter_dataset",
            "description": (
                "Filter the current search results in memory. Use after search_properties "
                "to narrow down results by additional criteria, sort them, or get summary "
                "statistics. Can also slice results (top N, by city, etc.)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filter_expression": {
                        "type": "string",
                        "description": (
                            "Filter expression using record fields: "
                            "lot_size_sqft > 10000, city == 'MIAMI GARDENS', "
                            "assessed_value < 200000. Combine with 'and'."
                        ),
                    },
                    "sort_by": {
                        "type": "string",
                        "description": "Field to sort by (e.g., 'lot_size_sqft', 'assessed_value', 'last_sale_price')",
                    },
                    "sort_order": {
                        "type": "string",
                        "enum": ["asc", "desc"],
                        "description": "Sort direction (default: desc)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Return only top N results after filtering/sorting",
                    },
                    "summary_only": {
                        "type": "boolean",
                        "description": "Return only summary statistics (count, avg, min, max), not individual records",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_dataset_info",
            "description": (
                "Get information about the current search results in session. "
                "Returns record count, field names, summary stats, and a sample. "
                "Use to check what data is available before filtering or exporting."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "export_dataset",
            "description": (
                "Export the current search results to a Google Spreadsheet. "
                "Automatically formats all records with appropriate headers. "
                "Use after search_properties or filter_dataset."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Spreadsheet title (auto-generated from search if omitted)",
                    },
                    "include_fields": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Fields to include (default: all). Options: folio, address, city, county, "
                            "owner, land_use_code, lot_size_sqft, year_built, assessed_value, "
                            "last_sale_price, last_sale_date, lat, lng"
                        ),
                    },
                },
            },
        },
    },
]


# Tool groups for dynamic masking (Notion/CloudQuery pattern:
# reduce context bloat by only showing relevant tools per turn)
CORE_TOOLS = [t for t in CHAT_TOOLS if t["function"]["name"] in {  # type: ignore[index]
    "geocode_address", "lookup_property_info", "search_zoning_ordinance", "web_search", "search_properties",
}]
DATASET_TOOLS = [t for t in CHAT_TOOLS if t["function"]["name"] in {  # type: ignore[index]
    "filter_dataset", "get_dataset_info", "export_dataset",
}]
CREATION_TOOLS = [t for t in CHAT_TOOLS if t["function"]["name"] in {  # type: ignore[index]
    "create_spreadsheet", "create_document",
}]


def _get_tools_for_turn(session_id: str, message: str) -> list[dict]:
    """Dynamic tool selection — only show tools relevant to the conversation state.

    Reduces context bloat and improves tool-use compliance. Inspired by
    Notion's context engineering pattern (context rot at 50-150k tokens).
    """
    tools = list(CORE_TOOLS)

    # Show dataset tools only when there's an active dataset in session
    if _sessions.has_dataset(session_id):
        tools.extend(DATASET_TOOLS)

    # Show creation tools when the user mentions export/document keywords
    creation_keywords = {"spreadsheet", "document", "export", "report", "download", "sheet", "doc"}
    if any(kw in message.lower() for kw in creation_keywords):
        tools.extend(CREATION_TOOLS)

    return tools


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

async def _execute_geocode(address: str, session_id: str = "") -> str:
    """Geocode an address to get municipality, county, and coordinates."""
    from plotlot.retrieval.geocode import geocode_address
    try:
        result = await geocode_address(address)
        if result:
            # Store full-precision coords in session so lookup_property_info
            # can use them even if the LLM truncates the values
            if session_id:
                _sessions.set_geocode(session_id, result)
            return json.dumps({
                "status": "success",
                "municipality": result["municipality"],
                "county": result["county"],
                "formatted_address": result["formatted_address"],
                "lat": result.get("lat"),
                "lng": result.get("lng"),
                "next_step": "Now call lookup_property_info with this address, county, lat, lng to get the zoning code",
            })
        return json.dumps({"status": "not_found", "message": f"Could not geocode: {address}"})
    except Exception as e:
        return json.dumps({"status": "error", "message": f"Geocoding failed: {str(e)}"})


async def _execute_lookup_property(address: str, county: str, lat: float, lng: float, session_id: str = "") -> str:
    """Look up property info from county Property Appraiser ArcGIS APIs."""
    from plotlot.retrieval.property import lookup_property

    # Use full-precision coords from session geocode if the LLM truncated them
    geo = _sessions.get_geocode(session_id) if session_id else None
    if geo:
        precise_lat = geo.get("lat")
        precise_lng = geo.get("lng")
        if precise_lat and precise_lng:
            lat = precise_lat
            lng = precise_lng

    try:
        record = await lookup_property(address, county, lat=lat, lng=lng)
        if record:
            result = {
                "status": "success",
                "folio": record.folio,
                "address": record.address,
                "municipality": record.municipality,
                "county": record.county,
                "owner": record.owner,
                "zoning_code": record.zoning_code,
                "zoning_description": record.zoning_description,
                "lot_size_sqft": record.lot_size_sqft,
                "lot_dimensions": record.lot_dimensions,
                "bedrooms": record.bedrooms,
                "year_built": record.year_built,
                "assessed_value": record.assessed_value,
                "living_area_sqft": record.living_area_sqft,
                "living_units": record.living_units,
            }
            if record.zoning_code:
                result["next_step"] = (
                    f"Now call search_zoning_ordinance with municipality='{record.municipality}' "
                    f"and query='{record.zoning_code} setbacks density height' to get the "
                    f"specific regulations for this zoning district"
                )
            return json.dumps(result)
        return json.dumps({"status": "not_found", "message": f"No property record found for {address} in {county}"})
    except Exception as e:
        return json.dumps({"status": "error", "message": f"Property lookup failed: {str(e)}"})


async def _execute_zoning_search(municipality: str, query: str) -> str:
    """Search the local zoning ordinance database via hybrid RAG.

    Uses the same hybrid_search (vector + full-text + RRF fusion) and
    retrieval depth as the pipeline endpoint for consistent quality.
    """
    with start_span(name="chat_zoning_search", span_type="RETRIEVER") as span:
        span.set_inputs({"municipality": municipality, "query": query, "limit": 15})

        session = await get_session()
        try:
            results = await hybrid_search(session, municipality, query, limit=15)
        finally:
            await session.close()

        if not results:
            span.set_outputs({"result_count": 0, "status": "no_results"})
            return json.dumps({"status": "no_results", "message": f"No ordinance sections found for '{query}' in {municipality}"})

        chunks = []
        for r in results:
            chunks.append({
                "section": r.section,
                "title": r.section_title,
                "zone_codes": r.zone_codes,
                "text": r.chunk_text,
            })

        span.set_outputs({
            "result_count": len(results),
            "status": "success",
            "top_sections": [c["section"] for c in chunks[:5]],
        })
        return json.dumps({"status": "success", "results": chunks})


async def _execute_web_search(query: str) -> str:
    """Search the web via Jina.ai Search API."""
    if not settings.jina_api_key:
        return json.dumps({"status": "error", "message": "Web search not configured (JINA_API_KEY not set)"})

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"https://s.jina.ai/{query}",
                headers={
                    "Authorization": f"Bearer {settings.jina_api_key}",
                    "Accept": "application/json",
                    "X-Retain-Images": "none",
                },
            )
            resp.raise_for_status()
            data = resp.json()

            # Extract relevant results
            results = []
            for item in data.get("data", [])[:5]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "description": item.get("description", "")[:300],
                    "content": item.get("content", "")[:500],
                })

            return json.dumps({"status": "success", "results": results})

    except Exception as e:
        logger.warning("Jina search failed: %s", e)
        return json.dumps({"status": "error", "message": f"Web search failed: {str(e)}"})


async def _execute_create_spreadsheet(title: str, headers: list[str], rows: list[list[str]]) -> str:
    """Create a Google Sheets spreadsheet with data."""
    try:
        result = await create_spreadsheet(title, headers, rows)
        return json.dumps({
            "status": "success",
            "spreadsheet_url": result.spreadsheet_url,
            "title": result.title,
            "row_count": len(rows),
            "message": f"Created spreadsheet '{result.title}' with {len(rows)} rows",
        })
    except Exception as e:
        logger.warning("Spreadsheet creation failed: %s", e)
        return json.dumps({"status": "error", "message": f"Failed to create spreadsheet: {str(e)}"})


async def _execute_create_document(title: str, content: str) -> str:
    """Create a Google Docs document with content."""
    try:
        result = await create_document(title, content)
        return json.dumps({
            "status": "success",
            "document_url": result.document_url,
            "title": result.title,
            "message": f"Created document '{result.title}'",
        })
    except Exception as e:
        logger.warning("Document creation failed: %s", e)
        return json.dumps({"status": "error", "message": f"Failed to create document: {str(e)}"})


async def _execute_search_properties(session_id: str, args: dict) -> str:
    """Search county property databases and store results in session."""
    try:
        # Convert ownership_min_years to max_sale_date
        max_sale_date = None
        ownership_years = args.get("ownership_min_years")
        if ownership_years:
            cutoff_year = datetime.now().year - int(ownership_years)
            max_sale_date = f"{cutoff_year}-01-01"

        params = PropertySearchParams(
            county=args["county"],
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
            max_results=min(args.get("max_results", 500), 2000),
        )

        records = await bulk_property_search(params)

        # Store in session
        _sessions.set_dataset(session_id, DatasetInfo(
            records=records,
            search_params=args,
            query_description=describe_search(args),
            total_available=len(records),
            fetched_at=datetime.now(timezone.utc).isoformat(),
        ))

        # Return summary + sample (not all records — avoids token blowout)
        sample = records[:10]
        stats = compute_dataset_stats(records)
        return json.dumps({
            "status": "success",
            "total_results": len(records),
            "sample": sample,
            "stats": stats,
            "message": f"Found {len(records)} properties. Use filter_dataset to narrow down or export_dataset to create a spreadsheet.",
        })
    except Exception as e:
        logger.warning("Property search failed: %s", e)
        return json.dumps({"status": "error", "message": f"Property search failed: {str(e)}"})


async def _execute_filter_dataset(session_id: str, args: dict) -> str:
    """Filter/sort the in-session dataset."""
    dataset = _sessions.get_dataset(session_id)
    if not dataset or not dataset.records:
        return json.dumps({"status": "error", "message": "No dataset in session. Use search_properties first."})

    records = dataset.records

    # Apply filter
    expression = args.get("filter_expression")
    if expression:
        records = _safe_filter(records, expression)

    # Apply sort
    sort_by = args.get("sort_by")
    if sort_by and records and sort_by in records[0]:
        reverse = args.get("sort_order", "desc") == "desc"
        records = sorted(records, key=lambda r: r.get(sort_by, 0) or 0, reverse=reverse)

    # Apply limit (cast to int — LLM may pass as string)
    limit = args.get("limit")
    if limit:
        records = records[:int(limit)]

    # Summary only mode
    if args.get("summary_only"):
        return json.dumps({
            "status": "success",
            "count": len(records),
            "stats": compute_dataset_stats(records),
        })

    # Update dataset with filtered results
    desc_suffix = f" (filtered: {expression})" if expression else " (sorted)"
    _sessions.set_dataset(session_id, DatasetInfo(
        records=records,
        search_params=dataset.search_params,
        query_description=dataset.query_description + desc_suffix,
        total_available=dataset.total_available,
        fetched_at=dataset.fetched_at,
    ))

    sample = records[:10]
    return json.dumps({
        "status": "success",
        "total_after_filter": len(records),
        "sample": sample,
        "message": f"Filtered to {len(records)} properties.",
    })


async def _execute_get_dataset_info(session_id: str) -> str:
    """Get info about the current in-session dataset."""
    dataset = _sessions.get_dataset(session_id)
    if not dataset or not dataset.records:
        return json.dumps({"status": "empty", "message": "No dataset in session. Use search_properties first."})

    stats = compute_dataset_stats(dataset.records)
    sample = dataset.records[:5]
    fields = list(dataset.records[0].keys()) if dataset.records else []

    return json.dumps({
        "status": "success",
        "count": len(dataset.records),
        "fields": fields,
        "search_description": dataset.query_description,
        "fetched_at": dataset.fetched_at,
        "stats": stats,
        "sample": sample,
    })


async def _execute_export_dataset(session_id: str, args: dict) -> str:
    """Export the in-session dataset to a Google Spreadsheet."""
    dataset = _sessions.get_dataset(session_id)
    if not dataset or not dataset.records:
        return json.dumps({"status": "error", "message": "No dataset to export. Use search_properties first."})

    title = args.get("title") or f"PlotLot — {dataset.query_description}"
    include_fields = args.get("include_fields") or list(dataset.records[0].keys())

    headers = [f.replace("_", " ").title() for f in include_fields]
    rows = [
        [str(record.get(f, "")) for f in include_fields]
        for record in dataset.records
    ]

    try:
        result = await create_spreadsheet(title, headers, rows)
        return json.dumps({
            "status": "success",
            "spreadsheet_url": result.spreadsheet_url,
            "title": result.title,
            "row_count": len(rows),
            "message": f"Exported {len(rows)} properties to '{result.title}'",
        })
    except Exception as e:
        logger.warning("Dataset export failed: %s", e)
        return json.dumps({"status": "error", "message": f"Failed to export dataset: {str(e)}"})


async def _execute_tool(name: str, args: dict, session_id: str = "") -> str:
    """Route a tool call to the appropriate handler."""
    if name == "geocode_address":
        return await _execute_geocode(args.get("address", ""), session_id=session_id)
    elif name == "lookup_property_info":
        return await _execute_lookup_property(
            args.get("address", ""),
            args.get("county", ""),
            args.get("lat", 0.0),
            args.get("lng", 0.0),
            session_id=session_id,
        )
    elif name == "search_zoning_ordinance":
        return await _execute_zoning_search(
            args.get("municipality", ""),
            args.get("query", ""),
        )
    elif name == "web_search":
        return await _execute_web_search(args.get("query", ""))
    elif name == "create_spreadsheet":
        return await _execute_create_spreadsheet(
            args.get("title", "Untitled"),
            args.get("headers", []),
            args.get("rows", []),
        )
    elif name == "create_document":
        return await _execute_create_document(
            args.get("title", "Untitled"),
            args.get("content", ""),
        )
    elif name == "search_properties":
        return await _execute_search_properties(session_id, args)
    elif name == "filter_dataset":
        return await _execute_filter_dataset(session_id, args)
    elif name == "get_dataset_info":
        return await _execute_get_dataset_info(session_id)
    elif name == "export_dataset":
        return await _execute_export_dataset(session_id, args)
    else:
        return json.dumps({"status": "error", "message": f"Unknown tool: {name}"})


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------

def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# ---------------------------------------------------------------------------
# Chat endpoint
# ---------------------------------------------------------------------------

@router.post("/chat")
async def chat(request: ChatRequest):
    """Agentic chat with tool use, streaming, and conversation memory."""

    # Get or create session for memory
    session_id = request.session_id or str(uuid.uuid4())[:12]

    async def event_generator():
        try:
            # Send session ID back to client for memory persistence
            yield _sse_event("session", {"session_id": session_id})

            # Build system prompt with report context
            system_content = AGENT_SYSTEM_PROMPT
            if request.report_context:
                system_content += _build_report_context(request.report_context)

            messages = [{"role": "system", "content": system_content}]

            # Load conversation memory (bounded by SessionStore)
            memory = _sessions.get_messages(session_id)
            if memory:
                # Include last N messages from memory for context
                messages.extend(memory[-20:])

            # Add conversation history from this page session
            for msg in request.history:
                messages.append({"role": msg.role, "content": msg.content})

            # Add current user message
            messages.append({"role": "user", "content": request.message})

            # Save user message to memory
            memory.append({"role": "user", "content": request.message})

            # MLflow span for the entire chat request (Notion replay pattern)
            _span_ctx = start_span(name="chat_request", span_type="CHAIN")
            chat_span = _span_ctx.__enter__()
            try:
                chat_span.set_inputs({
                    "session_id": session_id,
                    "message": request.message[:200],
                    "has_report_context": bool(request.report_context),
                })
            except AttributeError:
                pass  # No-op span in test env

            # Token budget check — prevent runaway cost
            if _sessions.get_tokens(session_id) >= MAX_TOKENS_PER_SESSION:
                yield _sse_event("token", {
                    "content": "I've reached the token limit for this session. "
                    "Please start a new conversation to continue."
                })
                yield _sse_event("done", {})
                return

            # Agent loop — may use tools before responding
            for turn in range(MAX_AGENT_TURNS):
                turn_tools = _get_tools_for_turn(session_id, request.message)
                response = await call_llm(messages, tools=turn_tools)

                if not response:
                    yield _sse_event("error", {"detail": "LLM returned empty response"})
                    return

                # Track token usage from response (estimated from content length)
                content_len = len(response.get("content", ""))
                _sessions.add_tokens(session_id, content_len // 4 + len(request.message) // 4)

                content = response.get("content", "")
                tool_calls = response.get("tool_calls", [])

                if not tool_calls:
                    # No tools — stream the text response
                    if content:
                        yield _sse_event("token", {"content": content})
                        memory.append({"role": "assistant", "content": content})
                    yield _sse_event("done", {"full_content": content})

                    # Trim memory if too long
                    if len(memory) > MAX_MEMORY_MESSAGES:
                        del memory[:-MAX_MEMORY_MESSAGES]
                    return

                # Tool calls — execute them and loop
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

                    # Tell the frontend a tool is being used
                    tool_messages = {
                        "geocode_address": "Resolving address...",
                        "lookup_property_info": "Looking up property record...",
                        "search_zoning_ordinance": "Searching zoning ordinances...",
                        "web_search": "Searching the web...",
                        "create_spreadsheet": "Creating spreadsheet...",
                        "create_document": "Creating document...",
                        "search_properties": "Searching property records...",
                        "filter_dataset": "Filtering results...",
                        "get_dataset_info": "Checking dataset...",
                        "export_dataset": "Exporting to Google Sheets...",
                    }
                    yield _sse_event("tool_use", {
                        "tool": fn_name,
                        "args": fn_args,
                        "message": tool_messages.get(fn_name, f"Using {fn_name}..."),
                    })

                    # Execute tool
                    result = await _execute_tool(fn_name, fn_args, session_id=session_id)

                    yield _sse_event("tool_result", {
                        "tool": fn_name,
                        "status": "complete",
                    })

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": result,
                    })

            # Exhausted tool-use turns — force a final text response (no tools)
            logger.info("Agent exhausted %d tool turns, forcing final response", MAX_AGENT_TURNS)
            final = await call_llm(messages)  # No tools → must respond with text
            final_content = final.get("content", "") if final else ""
            if not final_content:
                final_content = content or "I gathered some information but couldn't fully answer. Could you rephrase your question?"
            yield _sse_event("token", {"content": final_content})
            memory.append({"role": "assistant", "content": final_content})
            yield _sse_event("done", {"full_content": final_content})

        except Exception as e:
            logger.exception("Chat error")
            yield _sse_event("error", {"detail": str(e)})
        finally:
            try:
                chat_span.set_outputs({"session_tokens": _sessions.get_tokens(session_id)})
            except (AttributeError, Exception):
                pass
            try:
                _span_ctx.__exit__(None, None, None)
            except Exception:
                pass  # Don't let tracing errors break chat

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/chat/sessions")
async def list_sessions():
    """List active conversation sessions (for debugging/admin)."""
    return _sessions.list_sessions()


@router.delete("/chat/sessions/{session_id}")
async def clear_session(session_id: str):
    """Clear conversation memory and dataset for a session."""
    if _sessions.delete_session(session_id):
        return {"status": "cleared", "session_id": session_id}
    return {"status": "not_found"}
