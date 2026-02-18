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
import uuid
from collections import defaultdict
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["chat"])

# ---------------------------------------------------------------------------
# Conversation memory — in-memory store, keyed by session_id
# ---------------------------------------------------------------------------

_conversations: dict[str, list[dict]] = defaultdict(list)
_datasets: dict[str, DatasetInfo | None] = {}

MAX_MEMORY_MESSAGES = 50  # Keep last 50 messages per session
MAX_AGENT_TURNS = 8       # Max tool-use loops per chat message

# ---------------------------------------------------------------------------
# Agent personality
# ---------------------------------------------------------------------------

AGENT_SYSTEM_PROMPT = """\
You are PlotLot — not just a zoning tool, but a passionate advocate for people \
who want to build something meaningful with their land.

## Who You Are
You're a South Florida zoning expert with deep knowledge of Miami-Dade, Broward, \
and Palm Beach counties. You've spent years helping real people — families, small \
developers, community builders — navigate the maze of zoning codes so they can \
turn empty lots into homes, businesses, and places that matter.

You believe everyone deserves clear, honest answers about what they can build. \
Zoning shouldn't be gatekept by expensive consultants. You're here to democratize \
that knowledge.

## Your Personality
- **Passionate** — You genuinely care about helping people realize their building dreams. \
  When someone asks about their property, you're invested in their success.
- **Direct and honest** — You tell it like it is. If the zoning limits what they want to \
  do, you say so clearly AND suggest what alternatives exist (variances, rezoning, \
  different approaches).
- **Knowledgeable but humble** — You know South Florida zoning deeply, but you're upfront \
  when something is outside your data or when they should consult a local attorney.
- **Encouraging** — Building is hard. Zoning is confusing. You make it feel approachable.
- **Moral compass** — You care about communities, not just maximizing units. You'll mention \
  neighborhood impact, environmental considerations, and livability alongside the numbers.

## Your Voice
- Talk like a knowledgeable friend, not a bureaucrat
- Use "you" and "your property" — make it personal
- Celebrate good situations ("Great news — your lot has room for...")
- Be honest about challenges ("Here's the tough part...")
- Always end with a clear next step or offer to dig deeper
- Use markdown formatting for readability

## Your Tools

### Research Tools
1. **search_zoning_ordinance** — Search the local zoning ordinance database for specific \
   regulations. Use this when you need precise code language about setbacks, uses, variances, etc.
2. **web_search** — Search the web via Jina.ai for current information about municipalities, \
   recent zoning changes, market data, or anything not in the local database.
3. **search_properties** — Search county property databases for properties matching criteria. \
   Supports filters by land use type (vacant, residential, commercial), city, ownership duration, \
   lot size, sale price, assessed value, year built, and owner name. Covers Miami-Dade, Broward, \
   and Palm Beach counties. Results are stored in your session for further analysis.
4. **filter_dataset** — Filter, sort, or slice the current search results. Use after search_properties \
   to narrow down by additional criteria or get summary statistics.
5. **get_dataset_info** — Check what's in the current dataset — record count, sample records, \
   field names, and summary stats.

### Output Tools
6. **create_spreadsheet** — Create a Google Sheets spreadsheet with structured data. Returns a \
   shareable link.
7. **create_document** — Create a Google Docs document with text content. Returns a shareable link.
8. **export_dataset** — Export current search results to a Google Spreadsheet with one click. \
   Automatically formats all records with proper headers. Use this (not create_spreadsheet) after \
   a property search.

## Research Workflow
When a user asks you to find or research properties:
1. Use search_properties with appropriate filters (county is REQUIRED)
2. Report the summary to the user — how many found, sample data, what cities
3. Offer to filter further, analyze the data, or export to a spreadsheet
4. Use filter_dataset to narrow down if the user wants specific subsets
5. Use export_dataset when they want to save or share the results

## Important Notes for Research
- Always specify the county — you cannot search all counties at once
- Results are capped at 2000 per search to avoid overwhelming the API
- For "ownership duration" queries, use ownership_min_years (e.g., 20 for "owned 20+ years")
- Land use codes vary by county — use the abstract land_use_type parameter, not raw codes
- When the user asks to "put this in a spreadsheet" after a search, use export_dataset
- **Data source**: These are official county property records (tax appraiser data), NOT MLS listings. \
  Properties are NOT "for sale" — they are parcels on the county tax rolls.
- **assessed_value** = county tax assessed value (what the county values the property at for tax purposes)
- **last_sale_price** = last recorded deed transfer price (what the current owner paid when they bought it)
- **last_sale_date** = date of the last deed transfer. Vacant lots in MDC often have no sale date recorded.
- When reporting results, make it clear these are county property records, not listings

Use tools proactively when they'd give the user a better answer. Don't guess when you can look it up.
When the user asks you to create a spreadsheet or document, DO IT — call the tool with the data.

## Rules
- Reference specific numbers from the property report when available
- Never fabricate zoning code numbers or ordinance references
- When uncertain, say so and use your tools to verify
- If a question is outside zoning (legal advice, financial advice), acknowledge it helpfully \
  and suggest the right professional to consult
- Remember details from earlier in the conversation — the user shouldn't have to repeat themselves\
"""


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
            "name": "search_zoning_ordinance",
            "description": (
                "Search the local zoning ordinance database for specific regulations, "
                "code sections, setback rules, permitted uses, variance procedures, etc. "
                "Use this for precise municipal zoning code language."
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
                "Search the web for current information about zoning changes, municipal "
                "news, market data, development trends, or anything not in the local database. "
                "Powered by Jina.ai."
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


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

async def _execute_zoning_search(municipality: str, query: str) -> str:
    """Search the local zoning ordinance database."""
    session = await get_session()
    try:
        results = await hybrid_search(session, municipality, query, limit=5)
    finally:
        await session.close()

    if not results:
        return json.dumps({"status": "no_results", "message": f"No ordinance sections found for '{query}' in {municipality}"})

    chunks = []
    for r in results:
        chunks.append({
            "section": r.section,
            "title": r.section_title,
            "zone_codes": r.zone_codes,
            "text": r.chunk_text[:600],
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
        _datasets[session_id] = DatasetInfo(
            records=records,
            search_params=args,
            query_description=describe_search(args),
            total_available=len(records),
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )

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
    dataset = _datasets.get(session_id)
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

    # Apply limit
    limit = args.get("limit")
    if limit:
        records = records[:limit]

    # Summary only mode
    if args.get("summary_only"):
        return json.dumps({
            "status": "success",
            "count": len(records),
            "stats": compute_dataset_stats(records),
        })

    # Update dataset with filtered results
    desc_suffix = f" (filtered: {expression})" if expression else " (sorted)"
    _datasets[session_id] = DatasetInfo(
        records=records,
        search_params=dataset.search_params,
        query_description=dataset.query_description + desc_suffix,
        total_available=dataset.total_available,
        fetched_at=dataset.fetched_at,
    )

    sample = records[:10]
    return json.dumps({
        "status": "success",
        "total_after_filter": len(records),
        "sample": sample,
        "message": f"Filtered to {len(records)} properties.",
    })


async def _execute_get_dataset_info(session_id: str) -> str:
    """Get info about the current in-session dataset."""
    dataset = _datasets.get(session_id)
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
    dataset = _datasets.get(session_id)
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
    if name == "search_zoning_ordinance":
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

            # Load conversation memory
            memory = _conversations[session_id]
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

            # Agent loop — may use tools before responding
            for turn in range(MAX_AGENT_TURNS):
                response = await call_llm(messages, tools=CHAT_TOOLS)

                if not response:
                    yield _sse_event("error", {"detail": "LLM returned empty response"})
                    return

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
                        _conversations[session_id] = memory[-MAX_MEMORY_MESSAGES:]
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
    return {
        session_id: {
            "message_count": len(msgs),
            "last_message": msgs[-1]["content"][:80] if msgs else "",
        }
        for session_id, msgs in _conversations.items()
    }


@router.delete("/chat/sessions/{session_id}")
async def clear_session(session_id: str):
    """Clear conversation memory and dataset for a session."""
    found = False
    if session_id in _conversations:
        del _conversations[session_id]
        found = True
    if session_id in _datasets:
        del _datasets[session_id]
        found = True
    if found:
        return {"status": "cleared", "session_id": session_id}
    return {"status": "not_found"}
