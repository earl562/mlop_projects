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
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Request
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
from plotlot.retrieval.zoning_crosswalk import crosswalk_zoning_code
from plotlot.observability.prompts import get_active_prompt
from plotlot.observability.tracing import start_span
from plotlot.oauth.openai_auth import has_saved_tokens
from plotlot.storage.db import get_session
from plotlot.storage.models import ApprovalRequest, ToolRun, Workspace
from plotlot.land_use import ToolContext
from plotlot.land_use.policy import ToolPolicy
from plotlot.harness.policy import HarnessPolicyEngine
from plotlot.harness.tool_registry import get_tool_contract
from plotlot.harness.default_runtime import get_default_runtime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["chat"])


def _actor_user_id(http_request: Request | None) -> str:
    user = getattr(http_request.state, "user", None) if http_request is not None else None
    if isinstance(user, dict) and user.get("user_id"):
        return str(user["user_id"])
    return "anonymous"


def _expected_approval_id(*, tool_name: str, run_id: str) -> str:
    """Match ToolPolicy's deterministic approval ID format."""

    safe_tool = tool_name.replace(".", "_")
    return f"apr_{run_id}_{safe_tool}"


async def _persist_pending_approval(
    *,
    approval_id: str,
    context: ToolContext,
    tool_name: str,
    risk_class: str,
    args: dict,
    reason: str,
) -> None:
    """Best-effort persistence for approvals and tool-run audit.

    If persistence fails, we still fail closed (no external write happens).
    """

    session = await get_session()
    try:
        workspace = await session.get(Workspace, context.workspace_id)
        if workspace is None:
            session.add(
                Workspace(
                    id=context.workspace_id,
                    name="Default Workspace",
                    owner_user_id=context.actor_user_id
                    if context.actor_user_id != "anonymous"
                    else None,
                )
            )
            await session.flush()
        tool_run = ToolRun(
            workspace_id=context.workspace_id,
            project_id=context.project_id,
            site_id=context.site_id,
            analysis_id=context.analysis_id,
            analysis_run_id=None,
            tool_name=tool_name,
            risk_class=risk_class,
            status="pending_approval",
            input_json=args,
            output_json={},
        )
        session.add(tool_run)
        await session.flush()
        approval = ApprovalRequest(
            id=approval_id,
            workspace_id=context.workspace_id,
            project_id=context.project_id,
            analysis_run_id=None,
            tool_run_id=tool_run.id,
            status="pending",
            risk_class=risk_class,
            action_name=tool_name,
            reason=reason,
            request_json={"tool": tool_name, "args": args, "run_id": context.run_id},
            response_json={},
            requested_by=context.actor_user_id,
        )
        session.add(approval)
        await session.commit()
    except Exception:
        try:
            await session.rollback()
        except Exception:
            logger.warning("Approval persistence rollback failed", exc_info=True)
        logger.warning("Approval persistence failed", exc_info=True)
    finally:
        await session.close()


async def _validated_approved_ids(
    *,
    approval_ids: set[str],
    workspace_id: str,
) -> set[str]:
    """Return the subset of approval IDs that are actually approved in the DB.

    Fail-closed: if the database is unavailable, return an empty set.
    """

    if not approval_ids:
        return set()

    session = await get_session()
    try:
        now = datetime.now(timezone.utc)
        approved: set[str] = set()
        for approval_id in approval_ids:
            row = await session.get(ApprovalRequest, approval_id)
            if (
                row
                and row.workspace_id == workspace_id
                and row.status == "approved"
                and (row.expires_at is None or row.expires_at > now)
            ):
                approved.add(approval_id)
        return approved
    except Exception:
        logger.warning("Approval validation failed; failing closed", exc_info=True)
        return set()
    finally:
        await session.close()


# ---------------------------------------------------------------------------
# Session management — bounded memory store with LRU eviction
# ---------------------------------------------------------------------------

MAX_MEMORY_MESSAGES = 50  # Keep last 50 messages per session
MAX_AGENT_TURNS = 8  # Max tool-use loops per chat message
MAX_TOKENS_PER_SESSION = 50_000  # Cost cap — prevent runaway token spend
MAX_SESSIONS = 100  # Max concurrent sessions in memory (Render 512MB)
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
        self._property_context: dict[str, dict] = {}
        self._evidence_ids: dict[str, list[str]] = {}
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
        expired = [sid for sid, ts in self._last_access.items() if now - ts > self._ttl]
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
        self._property_context.pop(session_id, None)
        self._evidence_ids.pop(session_id, None)
        self._tokens.pop(session_id, None)
        self._last_access.pop(session_id, None)

    def get(self, session_id: str) -> Any:
        """Get session object (compatibility method — always returns None)."""
        return None

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

    def get_property_context(self, session_id: str) -> dict | None:
        return self._property_context.get(session_id)

    def set_property_context(self, session_id: str, data: dict) -> None:
        self._property_context[session_id] = data

    def get_evidence_ids(self, session_id: str) -> list[str]:
        return self._evidence_ids.get(session_id, [])

    def add_evidence_ids(self, session_id: str, ids: list[str]) -> None:
        existing = self._evidence_ids.setdefault(session_id, [])
        for ev_id in ids:
            if ev_id and ev_id not in existing:
                existing.append(ev_id)

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
                    if self._conversations.get(sid)
                    else ""
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


def _llm_unavailable_detail() -> str:
    using_nvidia = bool(settings.nvidia_api_key)
    if not (
        settings.openai_access_token
        or settings.openai_api_key
        or settings.nvidia_api_key
        or settings.groq_api_key
        or (
            settings.use_codex_oauth
            and has_saved_tokens(Path(settings.codex_auth_file).expanduser())
        )
    ):
        return (
            "Chat is temporarily unavailable because no LLM credentials are configured. "
            "Set NVIDIA_API_KEY, GROQ_API_KEY, OPENAI_API_KEY, OPENAI_ACCESS_TOKEN, or enable PLOTLOT_USE_CODEX_OAUTH to enable agent responses."
        )
    if using_nvidia:
        return (
            "Chat is temporarily unavailable because the configured NVIDIA NIM model "
            "returned no usable response. Verify the model slug or try the fallback model."
        )
    return "Chat is temporarily unavailable because the LLM returned an empty response."


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
        parts.append(
            f"- Setbacks: Front={report.setbacks.front}, Side={report.setbacks.side}, Rear={report.setbacks.rear}"
        )
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
        parts.append(
            f"- Max Units: {da.max_units} (governing: {da.governing_constraint}, confidence: {da.confidence})"
        )
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

CHAT_TOOLS: list[dict[str, Any]] = [
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
                        "description": "County from geocode result",
                    },
                    "state": {
                        "type": "string",
                        "description": "Two-letter state code from geocode result",
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
            "name": "search_municode_live",
            "description": (
                "Live Municode fallback for ordinance lookups when local indexed ordinance "
                "search returns weak, stale, or irrelevant results. Resolves the municipality's "
                "Municode authority, searches likely section headings, and returns live section snippets."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "municipality": {
                        "type": "string",
                        "description": "Municipality or jurisdiction name (e.g., 'Fort Lauderdale', 'Miramar')",
                    },
                    "query": {
                        "type": "string",
                        "description": "What regulation to look up live (e.g., 'RS-8 setbacks density height')",
                    },
                },
                "required": ["municipality", "query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "discover_open_data_layers",
            "description": (
                "Live ArcGIS/Open Data dataset discovery. Use this when you need to inspect which "
                "parcel or zoning layers are available for a county at a given location before making "
                "a zoning/owner-data claim."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "county": {
                        "type": "string",
                        "description": "County name (e.g., 'Miami-Dade', 'Broward', 'Palm Beach')",
                    },
                    "state": {
                        "type": "string",
                        "description": "Two-letter state code (e.g., 'FL', 'NC')",
                    },
                    "lat": {
                        "type": "number",
                        "description": "Latitude for coverage validation",
                    },
                    "lng": {
                        "type": "number",
                        "description": "Longitude for coverage validation",
                    },
                },
                "required": ["county", "state", "lat", "lng"],
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
                "Returns a shareable link to the new spreadsheet. "
                "External writes require explicit approval."
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
                    "approval_id": {
                        "type": "string",
                        "description": "Approval token for external write (returned as pending_approval)",
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
                "Returns a shareable link to the new document. "
                "External writes require explicit approval."
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
                    "approval_id": {
                        "type": "string",
                        "description": "Approval token for external write (returned as pending_approval)",
                    },
                },
                "required": ["title", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_document",
            "description": (
                "Generate a deal document (LOI, PSA, Deal Summary, or Pro Forma spreadsheet) "
                "from the analysis context. Use this when the user asks to create, generate, "
                "draft, or download a letter of intent, purchase agreement, deal summary, "
                "or pro forma for a property they've analyzed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "document_type": {
                        "type": "string",
                        "enum": ["loi", "psa", "deal_summary", "proforma_spreadsheet"],
                        "description": "Type of document to generate",
                    },
                    "deal_type": {
                        "type": "string",
                        "enum": [
                            "land_deal",
                            "subject_to",
                            "wrap",
                            "hybrid",
                            "seller_finance",
                            "wholesale",
                        ],
                        "description": "Type of deal structure",
                    },
                    "buyer_name": {
                        "type": "string",
                        "description": "Buyer name or entity (for LOI/PSA)",
                    },
                    "seller_name": {
                        "type": "string",
                        "description": "Seller name (for LOI/PSA)",
                    },
                    "purchase_price": {
                        "type": "number",
                        "description": "Purchase price in dollars (optional — uses pro forma max land price if omitted)",
                    },
                    "buyer_entity": {
                        "type": "string",
                        "description": "Buyer entity type (e.g. LLC, Corporation, Individual)",
                    },
                    "buyer_email": {
                        "type": "string",
                        "description": "Buyer email address",
                    },
                    "buyer_phone": {
                        "type": "string",
                        "description": "Buyer phone number",
                    },
                    "seller_entity": {
                        "type": "string",
                        "description": "Seller entity type (e.g. LLC, Corporation, Individual)",
                    },
                    "seller_email": {
                        "type": "string",
                        "description": "Seller email address",
                    },
                    "seller_phone": {
                        "type": "string",
                        "description": "Seller phone number",
                    },
                    "down_payment": {
                        "type": "number",
                        "description": "Down payment amount in dollars",
                    },
                    "earnest_money": {
                        "type": "number",
                        "description": "Earnest money deposit amount in dollars",
                    },
                    "financing_type": {
                        "type": "string",
                        "description": "Type of financing (cash, conventional, seller_carryback, subject_to)",
                    },
                    "closing_days": {
                        "type": "number",
                        "description": "Number of days until closing",
                    },
                    "due_diligence_days": {
                        "type": "number",
                        "description": "Number of days for due diligence period",
                    },
                    "inspection_days": {
                        "type": "number",
                        "description": "Number of days for inspection period",
                    },
                    "financing_contingency": {
                        "type": "boolean",
                        "description": "Whether financing contingency applies",
                    },
                    "appraisal_contingency": {
                        "type": "boolean",
                        "description": "Whether appraisal contingency applies",
                    },
                    "inspection_contingency": {
                        "type": "boolean",
                        "description": "Whether inspection contingency applies",
                    },
                    "state_code": {
                        "type": "string",
                        "description": "Two-letter state code (e.g. CA, FL, TX)",
                    },
                },
                "required": ["document_type", "deal_type"],
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
                        "description": "County to search in (required)",
                    },
                    "state": {
                        "type": "string",
                        "description": "Two-letter state code. Required for counties outside the built-in South Florida providers.",
                    },
                    "lat": {
                        "type": "number",
                        "description": "Optional latitude to validate discovered county datasets by coverage.",
                    },
                    "lng": {
                        "type": "number",
                        "description": "Optional longitude to validate discovered county datasets by coverage.",
                    },
                    "land_use_type": {
                        "type": "string",
                        "enum": [
                            "vacant_residential",
                            "vacant_commercial",
                            "single_family",
                            "multifamily",
                            "commercial",
                            "industrial",
                            "agricultural",
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
                    "min_lot_size_sqft": {
                        "type": "number",
                        "description": "Minimum lot size in square feet",
                    },
                    "max_lot_size_sqft": {
                        "type": "number",
                        "description": "Maximum lot size in square feet",
                    },
                    "min_sale_price": {
                        "type": "number",
                        "description": "Minimum last deed transfer price (what current owner paid)",
                    },
                    "max_sale_price": {
                        "type": "number",
                        "description": "Maximum last deed transfer price (what current owner paid)",
                    },
                    "min_assessed_value": {
                        "type": "number",
                        "description": "Minimum county tax assessed value in dollars",
                    },
                    "max_assessed_value": {
                        "type": "number",
                        "description": "Maximum county tax assessed value in dollars",
                    },
                    "year_built_before": {
                        "type": "integer",
                        "description": "Year built before (0 for vacant land)",
                    },
                    "year_built_after": {"type": "integer", "description": "Year built after"},
                    "owner_name_contains": {
                        "type": "string",
                        "description": "Owner name contains this text",
                    },
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
                "Use after search_properties or filter_dataset. "
                "External writes require explicit approval."
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
                    "approval_id": {
                        "type": "string",
                        "description": "Approval token for external write (returned as pending_approval)",
                    },
                },
            },
        },
    },
]


# Tool groups for dynamic masking (Notion/CloudQuery pattern:
# reduce context bloat by only showing relevant tools per turn)
CORE_TOOLS = [
    t
    for t in CHAT_TOOLS
    if t["function"]["name"]
    in {
        "geocode_address",
        "lookup_property_info",
        "search_zoning_ordinance",
        "search_municode_live",
        "discover_open_data_layers",
        "web_search",
        "search_properties",
    }
]
DATASET_TOOLS = [
    t
    for t in CHAT_TOOLS
    if t["function"]["name"]
    in {
        "filter_dataset",
        "get_dataset_info",
        "export_dataset",
    }
]
CREATION_TOOLS = [
    t
    for t in CHAT_TOOLS
    if t["function"]["name"]
    in {
        "create_spreadsheet",
        "create_document",
        "generate_document",
    }
]


class IntentClassification:
    """Lightweight intent classification for incoming chat messages.

    Uses keyword matching (not LLM) to avoid extra API calls.
    Guides tool selection and system prompt framing.
    """

    __slots__ = ("intent", "deal_type", "confidence")

    def __init__(
        self,
        intent: str = "general_question",
        deal_type: str | None = None,
        confidence: float = 0.5,
    ):
        self.intent = intent
        self.deal_type = deal_type
        self.confidence = confidence


# Keyword sets for intent detection
_ZONING_KEYWORDS = {
    "zoning",
    "zone",
    "setback",
    "density",
    "height limit",
    "far ",
    "floor area ratio",
    "lot coverage",
    "permitted use",
    "conditional use",
    "variance",
    "overlay",
    "land use",
}
_DEAL_KEYWORDS = {
    "deal",
    "offer",
    "purchase",
    "buy",
    "invest",
    "acquisition",
    "pro forma",
    "proforma",
    "comps",
    "comparable",
    "arv",
    "mao",
    "wholesale",
    "flip",
    "subject to",
    "sub-to",
    "subto",
    "wrap",
    "seller finance",
    "creative finance",
    "hybrid",
    "cash flow",
    "equity",
    "roi",
    "cap rate",
}
_DOC_KEYWORDS = {
    "loi",
    "letter of intent",
    "psa",
    "purchase agreement",
    "contract",
    "document",
    "generate",
    "draft",
    "deal summary",
    "report",
    "export",
    "spreadsheet",
    "download",
}
_GREETING_KEYWORDS = {
    "hey",
    "hello",
    "hi",
    "yo",
    "good morning",
    "good afternoon",
    "good evening",
    "what's up",
    "whats up",
}
_LAND_SOURCING_KEYWORDS = {
    "source",
    "sourcing",
    "vacant lot",
    "vacant lots",
    "infill",
    "land leads",
    "off-market",
    "off market",
    "owner list",
    "parcel list",
    "target market",
    "criteria",
    "assemblage",
    "subdivide",
    "entitlement",
    "rezone",
}
_DEAL_TYPE_PATTERNS: dict[str, set[str]] = {
    "wholesale": {"wholesale", "assign", "assignment", "mao", "arv", "flip"},
    "creative_finance": {
        "creative",
        "subject to",
        "sub-to",
        "subto",
        "seller finance",
        "wrap",
        "owner finance",
        "cash flow",
        "monthly payment",
    },
    "hybrid": {"hybrid", "combination", "blended"},
    "land_deal": {"land deal", "development", "build", "max units", "density"},
}


def _classify_intent(message: str) -> IntentClassification:
    """Classify user message intent and deal type from keywords."""
    msg_lower = message.lower()
    msg_clean = msg_lower.strip().rstrip("!?.")

    if msg_clean in _GREETING_KEYWORDS or any(
        msg_clean.startswith(greet) for greet in _GREETING_KEYWORDS
    ):
        return IntentClassification(intent="greeting", confidence=0.9)

    # Score each intent category
    zoning_score = sum(1 for kw in _ZONING_KEYWORDS if kw in msg_lower)
    deal_score = sum(1 for kw in _DEAL_KEYWORDS if kw in msg_lower)
    doc_score = sum(1 for kw in _DOC_KEYWORDS if kw in msg_lower)
    land_score = sum(1 for kw in _LAND_SOURCING_KEYWORDS if kw in msg_lower)

    # Determine primary intent
    if doc_score >= 2 or (doc_score >= 1 and deal_score >= 1):
        intent = "document_generation"
        confidence = min(0.9, 0.5 + doc_score * 0.15)
    elif land_score >= 1 and deal_score < 2:
        intent = "land_sourcing"
        confidence = min(0.9, 0.55 + land_score * 0.12)
    elif deal_score >= 2:
        intent = "deal_analysis"
        confidence = min(0.9, 0.5 + deal_score * 0.1)
    elif zoning_score >= 1:
        intent = "zoning_lookup"
        confidence = min(0.9, 0.5 + zoning_score * 0.15)
    else:
        intent = "general_question"
        confidence = 0.5

    # Detect deal type
    deal_type = None
    best_type_score = 0
    for dtype, keywords in _DEAL_TYPE_PATTERNS.items():
        score = sum(1 for kw in keywords if kw in msg_lower)
        if score > best_type_score:
            best_type_score = score
            deal_type = dtype

    return IntentClassification(intent=intent, deal_type=deal_type, confidence=confidence)


def _build_intent_context(classification: IntentClassification) -> str:
    """Build system prompt addition based on intent classification."""
    parts = [f"\n\n## Detected Intent: {classification.intent}"]

    if classification.deal_type:
        label = classification.deal_type.replace("_", " ").title()
        parts.append(f"Deal Type: {label}")

    guidance = {
        "zoning_lookup": (
            "The user is asking about zoning rules. Prioritize geocode → property lookup → "
            "zoning search. Focus on dimensional standards, setbacks, and permitted uses."
        ),
        "deal_analysis": (
            "The user wants deal-level analysis. After zoning lookup, focus on comparable "
            "sales, pro forma calculations, and investment metrics."
        ),
        "document_generation": (
            "The user wants to generate a document. If you have report context, "
            "use generate_document. Otherwise, gather the needed data first."
        ),
        "land_sourcing": (
            "The user is trying to source land or build a prospect list. Help them narrow market, "
            "lot type, zoning target, and acquisition criteria. Use property search tools when the "
            "request is concrete enough to run a search."
        ),
        "greeting": (
            "The user is greeting you or opening loosely. Respond naturally and briefly, then ask one "
            "specific question about their land-sourcing or property-analysis goal. Do not force tools yet."
        ),
        "general_question": (
            "Answer the user's question helpfully. If it sounds like an early-stage land-sourcing goal, "
            "help them clarify market, criteria, or next steps before using tools. Use tools when concrete data is needed."
        ),
    }
    parts.append(guidance.get(classification.intent, ""))
    return "\n".join(parts)


def _get_tools_for_turn(
    session_id: str,
    message: str,
    classification: IntentClassification | None = None,
) -> list[dict]:
    """Dynamic tool selection — only show tools relevant to the conversation state.

    Reduces context bloat and improves tool-use compliance. Inspired by
    Notion's context engineering pattern (context rot at 50-150k tokens).
    """
    if classification and classification.intent == "greeting":
        return []

    tools = list(CORE_TOOLS)

    # Show dataset tools only when there's an active dataset in session
    if _sessions.has_dataset(session_id):
        tools.extend(DATASET_TOOLS)

    # Show creation tools when the user mentions export/document keywords
    creation_keywords = {
        "spreadsheet",
        "document",
        "export",
        "report",
        "download",
        "sheet",
        "doc",
        "loi",
        "psa",
        "letter of intent",
        "purchase agreement",
        "pro forma",
        "proforma",
        "generate",
        "draft",
    }
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
            return json.dumps(
                {
                    "status": "success",
                    "municipality": result["municipality"],
                    "county": result["county"],
                    "state": result.get("state"),
                    "formatted_address": result["formatted_address"],
                    "lat": result.get("lat"),
                    "lng": result.get("lng"),
                    "next_step": "Now call lookup_property_info with this address, county, state, lat, lng to get the zoning code",
                }
            )
        return json.dumps({"status": "not_found", "message": f"Could not geocode: {address}"})
    except Exception as e:
        return json.dumps({"status": "error", "message": f"Geocoding failed: {str(e)}"})


async def _execute_lookup_property(
    address: str,
    county: str,
    lat: float,
    lng: float,
    session_id: str = "",
    state: str = "",
) -> str:
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
        if not state:
            state = str(geo.get("state") or "")

    try:
        record = await lookup_property(address, county, lat=lat, lng=lng, state=state)
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
            muni = record.municipality or address
            # The GIS layer's code (Track 1) and the ordinance code book (Track 2)
            # can label the same district differently (e.g. GIS "RS20" vs. Clark
            # County "R-E"). Crosswalk before steering the agent's ordinance search,
            # else it searches the GIS code and matches nothing in the indexed text.
            crosswalk = crosswalk_zoning_code(
                record.zoning_code,
                state=state,
                county=record.county,
                municipality=record.municipality,
            )
            if crosswalk.matched:
                result["ordinance_district_code"] = crosswalk.search_code
            zoning_query = (
                f"{crosswalk.search_code} setbacks density height"
                if record.zoning_code
                else f"{muni} zoning setbacks density height allowed uses"
            )
            if crosswalk.matched:
                result["next_step"] = (
                    f"The GIS layer labels this parcel '{record.zoning_code}', but the adopted "
                    f"ordinance uses '{crosswalk.search_code}' for that district. Now call "
                    f"search_zoning_ordinance with municipality='{muni}' and query='{zoning_query}' "
                    f"— search under '{crosswalk.search_code}', not '{record.zoning_code}'."
                )
            else:
                result["next_step"] = (
                    f"Now call search_zoning_ordinance with municipality='{muni}' "
                    f"and query='{zoning_query}' to get the zoning regulations for this property"
                )
            return json.dumps(result)
        return json.dumps(
            {
                "status": "not_found",
                "message": f"No property record found for {address} in {county}",
            }
        )
    except Exception as e:
        return json.dumps({"status": "error", "message": f"Property lookup failed: {str(e)}"})


async def _execute_zoning_search(municipality: str, query: str, session_id: str = "") -> str:
    """Search the local zoning ordinance database via hybrid RAG.

    Uses the same hybrid_search (vector + full-text + RRF fusion) and
    retrieval depth as the pipeline endpoint for consistent quality.
    """
    with start_span(name="chat_zoning_search", span_type="RETRIEVER") as span:
        span.set_inputs({"municipality": municipality, "query": query, "limit": 15})

        # Boost chunks tagged with this parcel's exact ordinance district code.
        # Prefer the crosswalked ordinance code (e.g. "R-E") established by
        # lookup_property_info; fall back to the raw GIS code.
        boost = ""
        if session_id:
            ctx = _sessions.get_property_context(session_id)
            if ctx:
                boost = str(ctx.get("ordinance_district_code") or ctx.get("zoning_code") or "")

        session = await get_session()
        try:
            results = await hybrid_search(
                session, municipality, query, limit=15, zone_code_boost=boost or None
            )
        finally:
            await session.close()

        if not results:
            span.set_outputs({"result_count": 0, "status": "no_results"})
            # Anti-hallucination contract: echo the zoning code already established
            # this session and tell the agent exactly how to present a coverage gap
            # without fabricating contacts, URLs, or "could not be retrieved" wording.
            known_zoning_code = ""
            if session_id:
                ctx = _sessions.get_property_context(session_id)
                if ctx:
                    known_zoning_code = str(ctx.get("zoning_code") or "")
            if known_zoning_code:
                guidance = (
                    f"The zoning code ({known_zoning_code}) is already confirmed for this parcel "
                    "from lookup_property_info — STATE IT PLAINLY. Its dimensional standards are "
                    f"simply not yet indexed in the PlotLot database for {municipality}. Tell the "
                    "user that and offer to ingest the ordinance. Do NOT say the zoning could not "
                    "be retrieved, and NEVER fabricate phone numbers, office names, URLs, or "
                    "numeric zoning values."
                )
            else:
                guidance = (
                    f"No indexed ordinance text for {municipality}. Report this honestly and offer "
                    "to ingest the municipality's ordinance or run a web_search. NEVER fabricate "
                    "phone numbers, office names, URLs, or numeric zoning values."
                )
            return json.dumps(
                {
                    "status": "no_results",
                    "message": f"No ordinance sections found for '{query}' in {municipality}",
                    "known_zoning_code": known_zoning_code,
                    "presentation_guidance": guidance,
                }
            )

        chunks = []
        for r in results:
            chunks.append(
                {
                    "section": r.section,
                    "title": r.section_title,
                    "zone_codes": r.zone_codes,
                    "text": r.chunk_text,
                }
            )

        span.set_outputs(
            {
                "result_count": len(results),
                "status": "success",
                "top_sections": [c["section"] for c in chunks[:5]],
            }
        )
        return json.dumps({"status": "success", "results": chunks})


async def _execute_municode_live_search(municipality: str, query: str, session_id: str = "") -> str:
    """Search live Municode sections for a municipality using heading-based matching.

    When the municipality is not on Municode (e.g. San Diego, served from a local
    PDF index), fall back to the indexed ordinance search so the agent gets real
    ordinance text instead of a dead end.
    """
    from plotlot.ingestion.discovery import get_municode_configs
    from plotlot.ingestion.scraper import MunicodeScraper

    try:
        configs = await get_municode_configs()
        config = configs.get(municipality.lower().replace("-", "_").replace(" ", "_"))
        if not config:
            candidates = [
                cfg for cfg in configs.values() if cfg.municipality.lower() == municipality.lower()
            ]
            config = candidates[0] if candidates else None
        if not config:
            # Not on Municode — serve indexed ordinance text (and the anti-hallucination
            # contract) rather than returning nothing.
            return await _execute_zoning_search(municipality, query, session_id)

        scraper = MunicodeScraper(max_concurrent=3)
        raw_terms = [term.lower() for term in re.findall(r"[a-z0-9-]+", query) if len(term) >= 3]
        query_terms: list[str] = []
        for term in raw_terms:
            query_terms.append(term)
            if term.endswith("s") and len(term) > 3:
                query_terms.append(term[:-1])

        async with httpx.AsyncClient(timeout=20.0) as client:
            leaves = await scraper.walk_toc(client, config, config.zoning_node_id, max_depth=3)
            ranked = []
            for leaf in leaves:
                haystack = f"{leaf.heading} {leaf.parent_heading or ''}".lower()
                score = sum(1 for term in query_terms if term in haystack)
                if score > 0:
                    ranked.append((score, leaf))
            ranked.sort(key=lambda item: item[0], reverse=True)
            top = ranked[:3]
            if not top:
                return json.dumps(
                    {
                        "status": "no_results",
                        "message": f"No live Municode sections matched '{query}' for {municipality}",
                    }
                )

            results = []
            for score, leaf in top:
                html = await scraper.get_section_content(client, config, leaf.node_id)
                snippet = re.sub(r"<[^>]+>", " ", html)
                snippet = re.sub(r"\s+", " ", snippet).strip()[:800]
                results.append(
                    {
                        "heading": leaf.heading,
                        "parent_heading": leaf.parent_heading,
                        "node_id": leaf.node_id,
                        "score": score,
                        "snippet": snippet,
                    }
                )

        return json.dumps(
            {
                "status": "success",
                "municipality": config.municipality,
                "source_type": "municode_live",
                "results": results,
            }
        )
    except Exception as e:
        logger.warning("Live Municode search failed for %s: %s", municipality, e)
        return json.dumps({"status": "error", "message": f"Live Municode search failed: {str(e)}"})


async def _execute_open_data_discovery(county: str, state: str, lat: float, lng: float) -> str:
    """Discover live parcel/zoning datasets via ArcGIS Hub for a county/location."""
    from plotlot.property.hub_discovery import discover_datasets

    try:
        state = (state or "").strip().upper()
        if not state:
            return json.dumps(
                {
                    "status": "error",
                    "message": "Open data discovery requires state (two-letter code).",
                }
            )

        parcels_ds, zoning_ds = await discover_datasets(lat, lng, county, state)

        def _serialize(ds):
            if not ds:
                return None
            return {
                "dataset_id": ds.dataset_id,
                "name": ds.name,
                "url": ds.url,
                "layer_id": ds.layer_id,
                "dataset_type": ds.dataset_type,
                "county": ds.county,
                "state": ds.state,
                "field_count": len(ds.fields),
                "fields_preview": ds.fields[:15],
            }

        return json.dumps(
            {
                "status": "success",
                "county": county,
                "state": state,
                "parcels_dataset": _serialize(parcels_ds),
                "zoning_dataset": _serialize(zoning_ds),
            }
        )
    except Exception as e:
        logger.warning("Open data discovery failed for %s, %s: %s", county, state, e)
        return json.dumps({"status": "error", "message": f"Open data discovery failed: {str(e)}"})


async def _execute_web_search(query: str) -> str:
    """Search the web via Jina.ai Search API."""
    if not settings.jina_api_key:
        return json.dumps(
            {
                "status": "not_configured",
                "message": "Web search is not available (JINA_API_KEY not set). Use search_zoning_ordinance for zoning questions.",
            }
        )

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
            if resp.status_code in (402, 429):
                return json.dumps(
                    {
                        "status": "quota_exceeded",
                        "message": "Web search quota exhausted. Use search_zoning_ordinance for zoning questions.",
                    }
                )
            if resp.status_code in (401, 403):
                return json.dumps(
                    {
                        "status": "auth_error",
                        "message": "Web search authentication failed (invalid JINA_API_KEY). Use search_zoning_ordinance for zoning questions.",
                    }
                )
            resp.raise_for_status()
            data = resp.json()

            # Extract relevant results
            results = []
            for item in data.get("data", [])[:5]:
                results.append(
                    {
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "description": item.get("description", "")[:300],
                        "content": item.get("content", "")[:500],
                    }
                )

            return json.dumps({"status": "success", "results": results})

    except Exception as e:
        logger.warning("Jina search failed: %s", e)
        return json.dumps({"status": "error", "message": f"Web search failed: {str(e)}"})


async def _execute_create_spreadsheet(
    title: str,
    headers: list[str],
    rows: list[list[str]],
    *,
    approval_id: str | None = None,
) -> str:
    """Create a Google Sheets spreadsheet with data."""
    if not approval_id:
        return json.dumps(
            {
                "status": "pending_approval",
                "message": "External write requires approval",
            }
        )
    try:
        result = await create_spreadsheet(title, headers, rows)
        return json.dumps(
            {
                "status": "success",
                "spreadsheet_url": result.spreadsheet_url,
                "title": result.title,
                "row_count": len(rows),
                "message": f"Created spreadsheet '{result.title}' with {len(rows)} rows",
            }
        )
    except Exception as e:
        logger.warning("Spreadsheet creation failed: %s", e)
        return json.dumps({"status": "error", "message": f"Failed to create spreadsheet: {str(e)}"})


async def _execute_create_document(
    title: str,
    content: str,
    *,
    approval_id: str | None = None,
) -> str:
    """Create a Google Docs document with content."""
    if not approval_id:
        return json.dumps(
            {
                "status": "pending_approval",
                "message": "External write requires approval",
            }
        )
    try:
        result = await create_document(title, content)
        return json.dumps(
            {
                "status": "success",
                "document_url": result.document_url,
                "title": result.title,
                "message": f"Created document '{result.title}'",
            }
        )
    except Exception as e:
        logger.warning("Document creation failed: %s", e)
        return json.dumps({"status": "error", "message": f"Failed to create document: {str(e)}"})


# Explicit generate_document args that map directly onto DealContext fields.
_DOC_ARG_FIELDS = (
    "buyer_name",
    "buyer_entity",
    "buyer_email",
    "buyer_phone",
    "seller_name",
    "seller_entity",
    "seller_email",
    "seller_phone",
    "purchase_price",
    "down_payment",
    "earnest_money",
    "financing_type",
    "state_code",
    "closing_days",
    "due_diligence_days",
    "inspection_days",
    "financing_contingency",
    "appraisal_contingency",
    "inspection_contingency",
)


def _build_deal_context_data(session_id: str, args: dict) -> dict:
    """Assemble DealContext field data from session state + explicit args.

    The chat tool-loop stores property context and geocode (not a full
    ZoningReport), so we populate what is available and take ``state_code`` from
    the geocode — never a hardcoded state. Explicit args override session values;
    financial terms (price, financing, parties) come from args.
    """
    ctx_data: dict = {}
    prop_ctx = _sessions.get_property_context(session_id) or {}
    geo = _sessions.get_geocode(session_id) or {}

    if prop_ctx.get("address"):
        ctx_data["property_address"] = prop_ctx["address"]
        ctx_data["formatted_address"] = prop_ctx["address"]
    if prop_ctx.get("municipality"):
        ctx_data["municipality"] = prop_ctx["municipality"]
    if prop_ctx.get("county"):
        ctx_data["county"] = prop_ctx["county"]
    if prop_ctx.get("zoning_code"):
        ctx_data["zoning_district"] = prop_ctx["zoning_code"]
    if prop_ctx.get("zoning_description"):
        ctx_data["zoning_description"] = prop_ctx["zoning_description"]
    if prop_ctx.get("lot_size_sqft"):
        ctx_data["lot_size_sqft"] = prop_ctx["lot_size_sqft"]
    if geo.get("state"):
        ctx_data["state_code"] = geo["state"]

    # Explicit args override session-derived values.
    for key in _DOC_ARG_FIELDS:
        if args.get(key) is not None:
            ctx_data[key] = args[key]

    return ctx_data


async def _execute_generate_document(session_id: str, args: dict) -> str:
    """Generate a deal document via the clause builder engine."""
    from plotlot.clauses.engine import assemble_document
    from plotlot.clauses.loader import ClauseRegistry
    from plotlot.clauses.schema import AssemblyConfig, DealContext, DealType, DocumentType

    doc_type_str = args.get("document_type", "deal_summary")
    deal_type_str = args.get("deal_type", "land_deal")

    try:
        doc_type = DocumentType(doc_type_str)
        deal_type = DealType(deal_type_str)
    except ValueError as e:
        return json.dumps({"status": "error", "message": str(e)})

    # Build context from the chat session's stored property + geocode data.
    ctx_data = _build_deal_context_data(session_id, args)

    output_format = "xlsx" if doc_type == DocumentType.proforma_spreadsheet else "docx"
    config = AssemblyConfig(
        document_type=doc_type,
        deal_type=deal_type,
        state_code=ctx_data.get("state_code", "FL"),
        output_format=output_format,
    )
    context = DealContext(**{k: v for k, v in ctx_data.items() if v})

    try:
        from plotlot.clauses.renderers.sheets_renderer import SheetsProFormaResult

        registry = ClauseRegistry.from_directory()
        doc = await assemble_document(config, context, registry)

        if isinstance(doc, SheetsProFormaResult):
            return json.dumps(
                {
                    "status": "success",
                    "document_type": doc_type_str,
                    "deal_type": deal_type_str,
                    "spreadsheet_url": doc.spreadsheet_url,
                    "title": doc.title,
                    "message": (
                        f"Created Google Sheets pro forma: {doc.title}. "
                        f"View it here: {doc.spreadsheet_url}"
                    ),
                }
            )

        return json.dumps(
            {
                "status": "success",
                "document_type": doc_type_str,
                "deal_type": deal_type_str,
                "filename": doc.filename,
                "content_type": doc.content_type,
                "size_bytes": len(doc.data),
                "message": (
                    f"Generated {doc.filename} ({len(doc.data):,} bytes). "
                    f"The user can download it from the Documents panel in the report."
                ),
            }
        )
    except Exception as e:
        logger.warning("Document generation failed: %s", e)
        return json.dumps({"status": "error", "message": f"Failed to generate document: {str(e)}"})


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
            max_results=min(args.get("max_results", 500), 2000),
        )

        records = await bulk_property_search(params)

        # Store in session
        _sessions.set_dataset(
            session_id,
            DatasetInfo(
                records=records,
                search_params=args,
                query_description=describe_search(args),
                total_available=len(records),
                fetched_at=datetime.now(timezone.utc).isoformat(),
            ),
        )

        # Return summary + sample (not all records — avoids token blowout)
        sample = records[:10]
        stats = compute_dataset_stats(records)
        return json.dumps(
            {
                "status": "success",
                "total_results": len(records),
                "sample": sample,
                "stats": stats,
                "message": f"Found {len(records)} properties. Use filter_dataset to narrow down or export_dataset to create a spreadsheet.",
            }
        )
    except Exception as e:
        logger.warning("Property search failed: %s", e)
        return json.dumps({"status": "error", "message": f"Property search failed: {str(e)}"})


async def _execute_filter_dataset(session_id: str, args: dict) -> str:
    """Filter/sort the in-session dataset."""
    dataset = _sessions.get_dataset(session_id)
    if not dataset or not dataset.records:
        return json.dumps(
            {"status": "error", "message": "No dataset in session. Use search_properties first."}
        )

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
        records = records[: int(limit)]

    # Summary only mode
    if args.get("summary_only"):
        return json.dumps(
            {
                "status": "success",
                "count": len(records),
                "stats": compute_dataset_stats(records),
            }
        )

    # Update dataset with filtered results
    desc_suffix = f" (filtered: {expression})" if expression else " (sorted)"
    _sessions.set_dataset(
        session_id,
        DatasetInfo(
            records=records,
            search_params=dataset.search_params,
            query_description=dataset.query_description + desc_suffix,
            total_available=dataset.total_available,
            fetched_at=dataset.fetched_at,
        ),
    )

    sample = records[:10]
    return json.dumps(
        {
            "status": "success",
            "total_after_filter": len(records),
            "sample": sample,
            "message": f"Filtered to {len(records)} properties.",
        }
    )


async def _execute_get_dataset_info(session_id: str) -> str:
    """Get info about the current in-session dataset."""
    dataset = _sessions.get_dataset(session_id)
    if not dataset or not dataset.records:
        return json.dumps(
            {"status": "empty", "message": "No dataset in session. Use search_properties first."}
        )

    stats = compute_dataset_stats(dataset.records)
    sample = dataset.records[:5]
    fields = list(dataset.records[0].keys()) if dataset.records else []

    return json.dumps(
        {
            "status": "success",
            "count": len(dataset.records),
            "fields": fields,
            "search_description": dataset.query_description,
            "fetched_at": dataset.fetched_at,
            "stats": stats,
            "sample": sample,
        }
    )


async def _execute_export_dataset(session_id: str, args: dict) -> str:
    """Export the in-session dataset to a Google Spreadsheet."""
    if not args.get("approval_id"):
        return json.dumps(
            {
                "status": "pending_approval",
                "message": "External write requires approval",
            }
        )
    dataset = _sessions.get_dataset(session_id)
    if not dataset or not dataset.records:
        return json.dumps(
            {"status": "error", "message": "No dataset to export. Use search_properties first."}
        )

    title = args.get("title") or f"PlotLot — {dataset.query_description}"
    include_fields = args.get("include_fields") or list(dataset.records[0].keys())

    headers = [f.replace("_", " ").title() for f in include_fields]
    rows = [[str(record.get(f, "")) for f in include_fields] for record in dataset.records]

    try:
        result = await create_spreadsheet(title, headers, rows)
        return json.dumps(
            {
                "status": "success",
                "spreadsheet_url": result.spreadsheet_url,
                "title": result.title,
                "row_count": len(rows),
                "message": f"Exported {len(rows)} properties to '{result.title}'",
            }
        )
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
            state=args.get("state", ""),
        )
    elif name == "search_zoning_ordinance":
        return await _execute_zoning_search(
            args.get("municipality", ""),
            args.get("query", ""),
            session_id=session_id,
        )
    elif name == "search_municode_live":
        return await _execute_municode_live_search(
            args.get("municipality", ""),
            args.get("query", ""),
            session_id=session_id,
        )
    elif name == "discover_open_data_layers":
        return await _execute_open_data_discovery(
            args.get("county", ""),
            args.get("state", ""),
            args.get("lat", 0.0),
            args.get("lng", 0.0),
        )
    elif name == "web_search":
        return await _execute_web_search(args.get("query", ""))
    elif name == "create_spreadsheet":
        return await _execute_create_spreadsheet(
            args.get("title", "Untitled"),
            args.get("headers", []),
            args.get("rows", []),
            approval_id=args.get("approval_id"),
        )
    elif name == "create_document":
        return await _execute_create_document(
            args.get("title", "Untitled"),
            args.get("content", ""),
            approval_id=args.get("approval_id"),
        )
    elif name == "generate_document":
        return await _execute_generate_document(session_id, args)
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
async def chat(request: ChatRequest, http_request: Request):
    """Agentic chat with tool use, streaming, and conversation memory."""

    # Get or create session for memory
    session_id = request.session_id or str(uuid.uuid4())[:12]

    async def event_generator():
        try:
            # Send session ID back to client for memory persistence
            yield _sse_event("session", {"session_id": session_id})

            # Classify intent before building prompt
            intent = _classify_intent(request.message)
            logger.info(
                "Intent: %s (deal_type=%s, confidence=%.2f) for: %s",
                intent.intent,
                intent.deal_type,
                intent.confidence,
                request.message[:80],
            )

            # Build system prompt with report context + intent guidance
            system_content = AGENT_SYSTEM_PROMPT
            if request.report_context:
                system_content += _build_report_context(request.report_context)
            else:
                # Inject lightweight property context from session even when no full
                # ZoningReport exists (e.g. chat-only flow after lookup_property_info).
                prop_ctx = _sessions.get_property_context(session_id)
                if prop_ctx and prop_ctx.get("address"):
                    ctx_lines = [
                        "\n\n## Active Property Context",
                        f"- Address: {prop_ctx['address']}",
                    ]
                    if prop_ctx.get("municipality"):
                        ctx_lines.append(f"- Municipality: {prop_ctx['municipality']}")
                    if prop_ctx.get("county"):
                        ctx_lines.append(f"- County: {prop_ctx['county']}")
                    if prop_ctx.get("zoning_code"):
                        ctx_lines.append(f"- Zoning Code: {prop_ctx['zoning_code']}")
                    if prop_ctx.get("zoning_description"):
                        ctx_lines.append(f"- Zoning Description: {prop_ctx['zoning_description']}")
                    if prop_ctx.get("lot_size_sqft"):
                        ctx_lines.append(f"- Lot Size: {prop_ctx['lot_size_sqft']:,.0f} sqft")
                    system_content += "\n".join(ctx_lines)
            system_content += _build_intent_context(intent)

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
                chat_span.set_inputs(
                    {
                        "session_id": session_id,
                        "message": request.message[:200],
                        "has_report_context": bool(request.report_context),
                    }
                )
            except AttributeError:
                pass  # No-op span in test env

            # Emit intent classification as a thinking event
            intent_thoughts = [f"Detected intent: {intent.intent.replace('_', ' ')}"]
            if intent.deal_type:
                intent_thoughts.append(f"Deal type: {intent.deal_type.replace('_', ' ').title()}")
            yield _sse_event(
                "thinking",
                {"step": "intent", "thoughts": intent_thoughts},
            )

            # Token budget check — prevent runaway cost
            if _sessions.get_tokens(session_id) >= MAX_TOKENS_PER_SESSION:
                yield _sse_event(
                    "token",
                    {
                        "content": "I've reached the token limit for this session. "
                        "Please start a new conversation to continue."
                    },
                )
                yield _sse_event("done", {})
                return

            # Agent loop — may use tools before responding
            for turn in range(MAX_AGENT_TURNS):
                turn_tools = _get_tools_for_turn(session_id, request.message, intent)
                response = await call_llm(messages, tools=turn_tools)

                if not response:
                    yield _sse_event("error", {"detail": _llm_unavailable_detail()})
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
                        contract = get_tool_contract(fn_name)
                    except KeyError:
                        contract = None

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
                        "generate_document": "Generating document...",
                        "search_properties": "Searching property records...",
                        "filter_dataset": "Filtering results...",
                        "get_dataset_info": "Checking dataset...",
                        "export_dataset": "Exporting to Google Sheets...",
                    }
                    yield _sse_event(
                        "tool_use",
                        {
                            "tool": fn_name,
                            "args": fn_args,
                            "message": tool_messages.get(fn_name, f"Using {fn_name}..."),
                        },
                    )

                    # Governance: authorize tool call through harness policy
                    actor_user_id = _actor_user_id(http_request)
                    claimed_approvals = set(request.approved_approval_ids or [])
                    validated_approvals = claimed_approvals
                    if contract and contract.risk_class in {
                        "write_external",
                        "execution",
                        "write_internal",
                        "expensive_read",
                    }:
                        validated_approvals = await _validated_approved_ids(
                            approval_ids=claimed_approvals,
                            workspace_id=request.workspace_id,
                        )

                    context = ToolContext(
                        workspace_id=request.workspace_id,
                        actor_user_id=actor_user_id,
                        run_id=session_id,
                        risk_budget_cents=request.risk_budget_cents,
                        live_network_allowed=request.live_network_allowed,
                        approved_approval_ids=validated_approvals,
                    )
                    policy_engine = HarnessPolicyEngine(
                        policy=ToolPolicy(internal_write_tools=frozenset({"generate_document"}))
                    )
                    if contract is None:
                        decision = policy_engine.authorize(
                            tool_name="gateway.execute", context=context
                        )
                    else:
                        decision = policy_engine.authorize(tool_name=fn_name, context=context)

                    if decision.approval_required:
                        approval_id = decision.approval_id
                        risk_class = contract.risk_class if contract else "execution"
                        await _persist_pending_approval(
                            approval_id=approval_id or "",
                            context=context,
                            tool_name=fn_name,
                            risk_class=risk_class,
                            args=fn_args,
                            reason=decision.reason,
                        )
                        tool_payload = {
                            "status": "pending_approval",
                            "approval_id": approval_id,
                            "risk_class": risk_class,
                            "message": decision.reason,
                        }
                        result = json.dumps(tool_payload)
                        yield _sse_event(
                            "tool_result",
                            {
                                "tool": fn_name,
                                "status": "pending_approval",
                                "approval_id": approval_id,
                                "risk_class": risk_class,
                                "message": decision.reason,
                            },
                        )
                    elif not decision.allowed:
                        result = json.dumps(
                            {
                                "status": "blocked",
                                "message": decision.reason,
                            }
                        )
                        yield _sse_event(
                            "tool_result",
                            {
                                "tool": fn_name,
                                "status": "blocked",
                                "message": decision.reason,
                            },
                        )
                    else:
                        # Execute tool (allowed)
                        if contract and contract.risk_class in {
                            "write_external",
                            "expensive_read",
                            "write_internal",
                        }:
                            expected = _expected_approval_id(tool_name=fn_name, run_id=session_id)
                            if expected in context.approved_approval_ids:
                                fn_args["approval_id"] = expected

                        # Route core tools through the shared harness runtime.
                        if fn_name in {
                            "geocode_address",
                            "lookup_property_info",
                            "search_zoning_ordinance",
                            "search_municode_live",
                            "discover_open_data_layers",
                            "generate_document",
                        }:
                            # For generate_document: inject accumulated session evidence IDs
                            # when the agent didn't pass any (common case in chat-only flow).
                            if fn_name == "generate_document" and not fn_args.get("evidence_ids"):
                                accumulated = _sessions.get_evidence_ids(session_id)
                                if accumulated:
                                    fn_args = {**fn_args, "evidence_ids": accumulated}

                            runtime = get_default_runtime()
                            tool_result = await runtime.call_tool(
                                tool_name=fn_name,
                                tool_args=fn_args,
                                context=context,
                                approval_id=fn_args.get("approval_id"),
                            )
                            # Preserve chat session behaviors.
                            if fn_name == "geocode_address" and tool_result.result:
                                geocode = tool_result.result.get("result")
                                if isinstance(geocode, dict) and session_id:
                                    _sessions.set_geocode(session_id, geocode)
                            if fn_name == "lookup_property_info" and tool_result.result:
                                prop = tool_result.result.get("result")
                                if isinstance(prop, dict) and session_id:
                                    _sessions.set_property_context(
                                        session_id,
                                        {
                                            "address": prop.get("address", ""),
                                            "municipality": prop.get("municipality", ""),
                                            "county": prop.get("county", ""),
                                            "zoning_code": prop.get("zoning_code", ""),
                                            "ordinance_district_code": prop.get(
                                                "ordinance_district_code", ""
                                            ),
                                            "zoning_description": prop.get(
                                                "zoning_description", ""
                                            ),
                                            "lot_size_sqft": prop.get("lot_size_sqft"),
                                        },
                                    )
                            # Accumulate evidence IDs from every tool that returns them,
                            # so generate_document can reference the full research chain.
                            if tool_result.result and session_id:
                                evidence_list = tool_result.result.get("evidence") or []
                                if isinstance(evidence_list, list):
                                    new_ids = [
                                        ev["id"]
                                        for ev in evidence_list
                                        if isinstance(ev, dict) and ev.get("id")
                                    ]
                                    if new_ids:
                                        _sessions.add_evidence_ids(session_id, new_ids)
                            result = json.dumps(tool_result.result or {})
                        else:
                            result = await _execute_tool(fn_name, fn_args, session_id=session_id)
                        yield _sse_event(
                            "tool_result",
                            {
                                "tool": fn_name,
                                "status": "complete",
                            },
                        )

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": result,
                        }
                    )

            # Exhausted tool-use turns — force a final text response (no tools)
            logger.info("Agent exhausted %d tool turns, forcing final response", MAX_AGENT_TURNS)
            final = await call_llm(messages)  # No tools → must respond with text
            final_content = final.get("content", "") if final else ""
            if not final_content:
                final_content = (
                    content
                    or "I gathered some information but couldn't fully answer. Could you rephrase your question?"
                )
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
