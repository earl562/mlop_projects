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
        self._analysis: dict[str, dict] = {}
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
        self._analysis.pop(session_id, None)
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

    def get_analysis(self, session_id: str) -> dict | None:
        """The most recent grounded analyze_property payload for this session."""
        return self._analysis.get(session_id)

    def set_analysis(self, session_id: str, data: dict) -> None:
        self._analysis[session_id] = data

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

# Hard anti-hallucination gate, appended to every chat system prompt. PlotLot's
# whole value is being trustworthy on numbers; the deterministic pipeline (units,
# comps, residual, fees, flood/coastal/wetlands, entitlement) is the source of
# truth. Without this gate the agent free-forms those numbers from the model's
# own knowledge and hallucinates — wrong zone density, fake comps, invented fees,
# "assumed" flood zones. The rule: the model may only restate what a tool returned.
GROUNDING_POLICY = """

## GROUNDING POLICY — NON-NEGOTIABLE (read before answering)
PlotLot is trusted because its numbers are source-verified, not guessed. You are
a narrator of grounded results, not a calculator.

For ANY question about a specific property that touches:
- buildable units, density, or what can be built by-right
- land value, comparable sales, "what's it worth", or "what can I pay"
- pro forma, residual, margin, exit value, or whether a deal "pencils"
- impact / development / school / utility fees
- flood zone, coastal, wetlands, or site risk
- entitlement path (by-right vs CUP vs rezone), timeline, or ADU/SB9/density bonus

you MUST first call `analyze_property` for that address and then cite ONLY the
numbers it returns. You may NOT:
- compute any of these yourself or derive them by hand,
- quote figures from your training knowledge or "industry benchmarks,"
- state a zoning code's density from its name (e.g. never read "RM-3-7" as
  "7 units/acre" — the tool returns the real density),
- present an estimate as if it were verified.

If `analyze_property` has not been run for the address in question, run it before
answering. If it returns a field as null/absent, tell the user that value is not
available — do NOT fill the gap with an estimate. If `offer_is_provisional` is
true, label the unit count and offer as PROVISIONAL, not firm, and say why.

ONCE you have run `analyze_property` for an address, its result stays available to
you for the rest of the conversation (an "ACTIVE GROUNDED ANALYSIS" block). Answer
EVERY follow-up about that property directly from those numbers. Do NOT re-run a
hypothetical, do NOT say "I don't have your assumptions" — the residual, comps,
fees, risk, and entitlement are already computed and in front of you.

ABSOLUTE RULE — when an ACTIVE GROUNDED ANALYSIS block is present you are FORBIDDEN
from producing any "hypothetical", "illustrative", "example", "typical", or
"estimated range" figure for units, land value, residual, fees, or entitlement
timeline: those numbers are in the block — quote them verbatim. If a specific field
is null/absent in the block, say in one sentence that it is "not available for this
parcel" and STOP — never substitute a generic range, a benchmark, or an invented
line item (there is NO "police impact fee" in San Diego). PROVISIONAL is NOT
"blocked" or "cannot be generated": present the real grounded number and simply
label it provisional. Telling the user a value "cannot be generated" while it sits
in the block, or filling the gap with a made-up number, is a critical failure.

Never invent an alternative ordinance reading (e.g. a different "sq ft per unit")
to manufacture a conflict — the verified driver the tool returns IS the answer.
San Diego is already fully ingested; never suggest "ingesting the ordinance" or
imply the data is missing. PROVISIONAL means automated verification was
inconclusive, not that data is absent — present the number and flag it.

Do NOT decompose or itemize an aggregate the tool returned as a single number.
Itemize the impact/dev fee ONLY if the tool gives an "impact_fee_breakdown" — then
cite those exact verified line items. If there is no breakdown, present the fee as
ONE coarse regional figure and never invent categories (park, fire, police,
school). When a value carries a "_basis" note saying it's a regional
default/estimate (e.g. ADV with adv_source != "comps", or a non-itemized fee),
state that provenance plainly — call it an estimate, not an appraised or verified
figure. If comps came back empty, say land value/exit is estimated from a regional
default; do not fabricate a comp range.

When the user gives a LIST of addresses/parcels and asks which fit their box or
pencil best, call `screen_properties` (not analyze_property one-by-one) and rank
only from its results.

If a value is genuinely outside the tools' output (e.g. a hyper-local fee
schedule or live utility capacity), say it is not modeled and that it must be
verified with the city — never fabricate a number to fill the gap.

## MATH RULE — NEVER CALCULATE IN YOUR HEAD
Every arithmetic operation — units × price, cost per sqft, total project cost,
residual, gap vs asking price, percentages, a unit count from lot area — MUST be
done with the `calculate` tool. Do NOT compute any number yourself; LLM mental
math is wrong often enough that it causes real financial harm. If you catch
yourself about to write a number you did not get from a tool, call `calculate`
first and cite its result. When a pre-formatted figure already exists in the
payload (GDV, residual, a sensitivity cell), quote THAT — do not recompute it.

## FEE RULE — NEVER FABRICATE FEE BREAKDOWNS
Development impact fees, permit fees, and any itemized cost breakdown MUST come
from a tool result. If the payload gives one coarse fee figure, present that ONE
figure and its basis — do NOT invent line items like "police fee,"
"transportation fee," "park fee," or a per-category split that is not in the tool
output. If you don't have an itemized schedule, say exactly: "Specific fee
breakdown not available for this project scope," and stop.

## DETERMINISTIC FIELDS — REPRODUCE, NEVER RE-DERIVE
Certain figures are pre-computed and pre-labeled for you. Reproduce them exactly;
never recompute, re-scale, or re-attribute them:
- SOURCE / CITATION: When asked "what's the source", "can I trust this", or to cite
  the ordinance, reproduce ONLY a VERIFIED driver's exact `citation` text and its
  `section` from the payload. NEVER output an ordinance section number or a quoted
  ordinance sentence that is not present verbatim in the payload — do not invent a
  subsection (e.g. "§131.0445(a)") and do not borrow a section from a different or
  CONFLICTING field's citation. If the verified driver has no section, say the exact
  subsection wasn't captured in the retrieved text — never fabricate one.
- EXIT VALUE / GDV: `adv_per_unit` is PER UNIT. Never read it as a project total or
  divide it by the unit count. Use the pre-formatted `exit_value_formula` and
  `gross_development_value` exactly as given (units × ADV/unit = GDV).
- SENSITIVITY: For "what if construction/exit moves" questions, cite the
  `sensitivity` scenarios from the payload verbatim (negative = does not pencil). Do
  NOT invent construction-cost or exit-price ranges or compute your own residual.
- CA UPSIDE PROGRAMS: Use ONLY the program `name`, `statute`, and unit counts in
  `ca_upside.programs`. Never invent a program (there is no "SB9" or "Educationally
  Impactful Development" pathway unless the payload lists it) or restate a statute's
  mechanics from memory.
- SITE RISK / TOPOGRAPHY / HAZARDS: Report flood, wetlands, and geologic hazard ONLY
  from `site_risk` (incl. `site_risk.geologic_hazard` and `risk_flags`). NEVER invent
  an elevation, a slope grade, or a "mild/moderate slope" — topography is not modeled.
  When `geologic_hazard.evaluated` is false, say the parcel was NOT evaluated by CGS
  (an unknown needing a geotechnical review) — never report it as "low risk" or a
  clearance. Report `site_risk.airport_influence` when present (Airport Influence
  Area → disclosure / height-notification review). Overlays NOT in the payload (e.g.
  Steep Hillsides / ESL slope review) are not checked — say they must be verified
  with the City; do not assert their status.
- LOT AREA & UNIT COUNT: The by-right count is lot area ÷ min-lot-area-per-unit, so
  it is only as firm as the lot area. Use the EXACT `lot_size_sqft`; never substitute
  a lot size from training knowledge or another listing. When `lot_size_source` is
  "geometry" (or `by_right.lot_size_confirmed` is false), the lot is a GIS
  parcel-polygon ESTIMATE, not the recorded legal lot — present the unit count as
  PROVISIONAL and say it must be confirmed with the county assessor, EVEN IF the
  ordinance rule verified. Never call the count "verified"/"firm" on a
  geometry-estimated lot. When `lot_size_source` is "assessor", the lot is
  authoritative — say so.
- DEVELOPMENT ACTIVITY: When `development_activity` is present (city permits on
  record), the parcel may ALREADY be an active, owned/entitled development — not raw
  land. Surface that fact (permit count + holders) before any "what can I pay for the
  land" / residual answer, and frame the residual as conditional on the site actually
  being available to acquire. Cite only the permit counts/holders the tool returns;
  never invent permit numbers, project names, or unit counts.
"""


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


def _build_report_context(report, *, suppress_grounded_fields: bool = False) -> str:
    """Summarize the ZoningReport for the agent's context.

    ``suppress_grounded_fields`` omits the trust-critical figures (lot size + source,
    by-right units/density, owner) that a freshly-computed ACTIVE GROUNDED ANALYSIS
    supersedes. Set it when the chat already has a fresh grounded analysis so a
    stale, browser-cached report_context can't reintroduce old numbers (the "crawls
    back to 6 units" bug) — its still-useful extras (setbacks, FAR, uses, year built,
    assessed value) are kept."""
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
    if report.max_density and not suppress_grounded_fields:
        parts.append(f"- Max Density: {report.max_density}")
    if report.floor_area_ratio:
        parts.append(f"- FAR: {report.floor_area_ratio}")
    if report.lot_coverage:
        parts.append(f"- Lot Coverage: {report.lot_coverage}")
    if report.parking_requirements:
        parts.append(f"- Parking: {report.parking_requirements}")

    if report.density_analysis and not suppress_grounded_fields:
        da = report.density_analysis
        parts.append(
            f"- Max Units: {da.max_units} (governing: {da.governing_constraint}, confidence: {da.confidence})"
        )
        for c in da.constraints:
            gov = " [GOVERNING]" if c.is_governing else ""
            parts.append(f"  - {c.name}: {c.max_units} units — {c.formula}{gov}")

    if report.property_record:
        pr = report.property_record
        if not suppress_grounded_fields:
            parts.append(f"- Lot Size: {pr.lot_size_sqft:,.0f} sqft")
            if pr.lot_size_source:
                src_labels = {
                    "assessor": "county assessor record",
                    "geometry": "GIS parcel geometry estimate",
                }
                label = src_labels.get(pr.lot_size_source, pr.lot_size_source)
                parts.append(f"- Lot Source: {label}")
        if pr.lot_dimensions:
            parts.append(f"- Lot Dimensions: {pr.lot_dimensions}")
        if pr.year_built:
            parts.append(f"- Year Built: {pr.year_built}")
        if pr.assessed_value:
            parts.append(f"- Assessed Value: ${pr.assessed_value:,.0f}")
        if pr.owner and not suppress_grounded_fields:
            parts.append(f"- Owner: {pr.owner}")

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

    sr = report.site_risk
    if sr is not None:
        fz = sr.flood_zone
        if fz is not None:
            parts.append(f"- Flood Zone: {fz.zone} ({fz.risk_level})")
        geo = sr.geologic
        if geo is not None:
            parts.append("- Geologic Hazard (CGS):")
            if geo.fault_zone:
                parts.append(f"  - Fault Zone: {geo.fault_zone}")
            if geo.landslide_zone:
                parts.append(f"  - Landslide: {geo.landslide_zone}")
            if geo.liquefaction_zone:
                parts.append(f"  - Liquefaction: {geo.liquefaction_zone}")

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
            "name": "analyze_property",
            "description": (
                "THE authoritative deal-analysis engine. Runs the full deterministic "
                "PlotLot pipeline for ONE address and returns GROUNDED, source-verified "
                "numbers: max buildable units by-right (with verification status), "
                "estimated land value + range, residual max land price ('what you can "
                "pay'), after-development value per unit (the exit), per-unit impact/dev "
                "fees, entitlement path + timeline (by-right vs CUP vs rezone), FEMA "
                "flood zone / coastal / wetlands risk, and California ADU/SB9/Density-"
                "Bonus upside. "
                "You MUST call this before stating ANY number about units, density, land "
                "value, comps, pro forma, fees, risk, or entitlement. NEVER compute these "
                "yourself or quote them from memory — only repeat what this tool returns. "
                "Pass the full street address; it self-geocodes and looks up the parcel."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {
                        "type": "string",
                        "description": "Full street address (e.g. '1233 Hueneme St, San Diego, CA 92110')",
                    },
                },
                "required": ["address"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": (
                "Deterministic calculator — evaluate EVERY arithmetic operation here "
                "before you state a number. Use it for units × price, cost per sqft, "
                "total project cost, residual, gap vs asking, percentages, a unit count "
                "from lot area — any math at all. Pass a plain arithmetic expression "
                "(numbers and + - * / // % ** and parentheses only). NEVER compute in your "
                "head: LLM mental math produces wrong $/unit and totals, which cause real "
                "financial harm. Returns the exact result for you to cite verbatim."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": (
                            "Arithmetic only, e.g. '7 * 750000' or '(4500000 - 240000) / 7'"
                        ),
                    },
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_upzoning",
            "description": (
                "Deterministic entitlement value-creation calculator — the developer's "
                "'buy the gap' play. Use it when the user asks about the UPSIDE of "
                "subdividing or rezoning: instant equity, value uplift, 'what if I split "
                "this into N lots', 'what's it worth if I get it upzoned', cost per lot, "
                "or exit/monetization options (flip, assign, sell-some-keep-rest-free, "
                "develop). It compares the by-right baseline yield to an upzoned target and "
                "computes the equity created BEFORE building. The per-lot finished value "
                "must come from the user or comps — never invent it. Returns exact figures "
                "to cite verbatim (no LLM math)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "lot_sqft": {
                        "type": "number",
                        "description": "Parcel lot area in square feet (from the grounded analysis).",
                    },
                    "value_per_lot": {
                        "type": "number",
                        "description": (
                            "Finished sale value per lot/unit, from the user or local comps. "
                            "Omit if unknown — the tool will not guess it."
                        ),
                    },
                    "purchase_price": {
                        "type": "number",
                        "description": "Contract/purchase price for the parcel (incl. closing).",
                    },
                    "entitlement_soft_costs": {
                        "type": "number",
                        "description": (
                            "Entitlement soft costs (survey, environmental, architect, zoning "
                            "consultant, application fees). Optional."
                        ),
                    },
                    "baseline_yield": {
                        "type": "integer",
                        "description": "By-right lots/units (e.g. the grounded by-right unit count).",
                    },
                    "upzoned_yield": {
                        "type": "integer",
                        "description": "Target lots/units after subdivision/upzoning the user is testing.",
                    },
                    "baseline_min_lot_area_sqft": {
                        "type": "number",
                        "description": "Alternative to baseline_yield: current min lot area to subdivide against.",
                    },
                    "upzoned_min_lot_area_sqft": {
                        "type": "number",
                        "description": "Alternative to upzoned_yield: target min lot area after upzoning.",
                    },
                    "yield_basis": {
                        "type": "string",
                        "description": "Label for the yield: 'buildable lots' (default) or 'dwelling units'.",
                    },
                },
                "required": ["lot_sqft"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "screen_properties",
            "description": (
                "Batch 'buy box' screening — analyze MANY candidate addresses at once "
                "and return only the ones that fit the user's criteria, ranked by the "
                "deterministic residual max land offer (best deals first). Use this when "
                "the user has a LIST of parcels/addresses and asks which fit their box or "
                "pencil best. Each address runs through the SAME grounded pipeline as "
                "analyze_property (verified units + residual), so the rankings are "
                "source-based, not estimated. Heavy operation — keep the list to ~20."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "addresses": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Candidate street addresses to screen (max ~20).",
                    },
                    "states": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional 2-letter state filter, e.g. ['CA'].",
                    },
                    "counties": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional county filter (case-insensitive).",
                    },
                    "zoning_prefixes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional zoning-code prefixes, e.g. ['RM','RD'].",
                    },
                    "min_lot_sqft": {"type": "number", "description": "Minimum lot size (sqft)."},
                    "max_lot_sqft": {"type": "number", "description": "Maximum lot size (sqft)."},
                    "min_units": {"type": "integer", "description": "Minimum buildable units."},
                    "min_residual": {
                        "type": "number",
                        "description": "Minimum residual max land offer — the deal must pencil to at least this.",
                    },
                    "require_verified": {
                        "type": "boolean",
                        "description": "If true, drop deals whose unit count is provisional/uncorroborated.",
                    },
                    "exclude_high_flood_risk": {
                        "type": "boolean",
                        "description": "If true, drop parcels in a high flood-risk area.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max qualified deals to return (default 25).",
                    },
                },
                "required": ["addresses"],
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
        "analyze_property",
        "calculate",
        "analyze_upzoning",
        "screen_properties",
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


# Street-type suffixes used to recognize a bare address as a property query.
_STREET_SUFFIX_RE = re.compile(
    r"\b("
    r"st|street|ave|avenue|blvd|boulevard|rd|road|dr|drive|ln|lane|way|ct|court|"
    r"pl|place|ter|terrace|cir|circle|hwy|highway|pkwy|parkway|trail|trl|loop|"
    r"run|path|row|sq|square|aly|alley|walk|cres|crescent|cv|cove|pt|point"
    r")\b",
    re.IGNORECASE,
)


def _looks_like_address(message: str) -> bool:
    """True when the message is (or leads with) a US street address.

    A bare address — "2307 Spanish Trail Road, Belvedere Tiburon, CA" — carries
    none of the zoning/deal keywords, so without this check it falls through to
    ``general_question`` and the agent answers from general knowledge (or tells
    the user to call the planning department) instead of running the
    geocode → property → zoning pipeline. Require a leading house number AND a
    street suffix so counts like "5 unit building" don't match.
    """
    m = message.strip()
    return bool(re.match(r"^\d{1,6}\s+\w", m)) and bool(_STREET_SUFFIX_RE.search(m))


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
    elif _looks_like_address(message):
        # A bare address is an implicit "analyze this property" request — route it
        # to the property pipeline instead of letting it fall to general_question.
        intent = "zoning_lookup"
        confidence = 0.75
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
            "The user gave a property/address to analyze. You MUST run the tools: call "
            "geocode, then lookup_property_info, then search_zoning_ordinance, and answer "
            "from their results. Do NOT answer from general knowledge, do NOT give 'typical' "
            "estimates, and do NOT tell the user to contact the planning department or check "
            "a county GIS — PlotLot has the ingested ordinance and parcel data; retrieve it. "
            "Report the lot size, zoning code, dimensional standards, setbacks, and permitted "
            "uses that the tools return."
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


def _build_active_analysis_context(payload: dict) -> str:
    """Render a stored analyze_property payload into an authoritative prompt block.

    The agent abandons grounded data after the turn the tool ran and reverts to
    hypotheticals on follow-ups (it even invents alternate ordinance readings).
    Promoting the verified numbers into the system prompt — and ordering it to
    answer follow-ups from them — is what keeps the whole conversation grounded.
    """
    if not payload or payload.get("status") != "success":
        return ""

    lines: list[str] = [
        "\n\n## ACTIVE GROUNDED ANALYSIS — AUTHORITATIVE (cite these EXACT numbers)",
        f"Property: {payload.get('address', '')} · Zoning: {payload.get('zoning_code', '')}",
    ]
    lot = payload.get("lot_size_sqft")
    if lot:
        lot_src = payload.get("lot_size_source") or ""
        if lot_src == "assessor":
            lines.append(f"Lot size: {lot:,.0f} sqft (county assessor — authoritative legal lot)")
        elif lot_src == "geometry":
            lines.append(
                f"Lot size: {lot:,.0f} sqft (GIS parcel-polygon ESTIMATE — not the legal lot; "
                "confirm with assessor, count is provisional on it)"
            )
        else:
            lines.append(f"Lot size: {lot:,.0f} sqft")

    owner = payload.get("owner")
    if owner:
        lines.append(
            f"Owner of record (county assessor): {owner} — this is the verified owner. "
            "If asked who owns the parcel, state THIS name; do NOT say the owner is "
            "unavailable or absent from the dataset."
        )

    by_right = payload.get("by_right") or {}
    if by_right:
        verif = by_right.get("verification", "")
        lines.append(
            f"By-right max units: {by_right.get('max_units')} "
            f"(governing: {by_right.get('governing_constraint')}, "
            f"verification: {verif.upper()})"
        )
        # Inject ONLY verified, cited drivers — never a conflicting field's
        # citation (the FAR-conflict citation literally contains "§131.0445(a)",
        # which the narrator borrowed and mis-attributed to the unit count).
        drivers = by_right.get("verified_drivers") or []
        for d in drivers:
            if d.get("status") == "verified" and d.get("citation"):
                sec = f" [{d['section']}]" if d.get("section") else ""
                lines.append(
                    f"  • VERIFIED source — {d.get('label') or d.get('field')}="
                    f'{d.get("source_value")}{sec}: "{d.get("citation")[:200]}"'
                )

    val = payload.get("valuation") or {}
    if val:
        # Pre-formatted, unambiguous exit line so the narrator can't read the
        # per-unit ADV as a project total and divide it (it did → "$125k/unit").
        if val.get("exit_value_formula"):
            lines.append(f"Exit value: {val['exit_value_formula']}")
        elif val.get("adv_per_unit") is not None:
            adv_note = "" if val.get("adv_source") == "comps" else " [regional estimate, no comps]"
            lines.append(
                f"After-development value PER UNIT (exit): ${val['adv_per_unit']:,.0f} "
                f"(source: {val.get('adv_source', 'n/a')}){adv_note} — this is per unit, "
                "do NOT divide by the unit count"
            )
        if val.get("max_land_price_residual") is not None:
            lines.append(f"Max land price (residual): ${val['max_land_price_residual']:,.0f}")
        # Full cost stack so the narrator quotes the verified line items instead of
        # reconstructing them (it used lot area for construction and dropped soft costs
        # + builder margin, so its breakdown never reconciled to this residual).
        if val.get("residual_formula"):
            lines.append(f"  Residual cost stack: {val['residual_formula']}")
        if val.get("hard_cost_basis"):
            lines.append(f"  ({val['hard_cost_basis']})")
        rng = val.get("land_value_range")
        if rng and rng[1]:  # only when comps gave a real range (else it's $0–$0)
            lines.append(f"Land value range: ${rng[0]:,.0f}–${rng[1]:,.0f}")
        if val.get("adv_basis"):
            lines.append(f"  ({val['adv_basis']})")
        if val.get("impact_fees_per_unit") is not None:
            # When a real itemized DIF schedule is registered, the payload carries
            # the verified line items + a basis note — surface them faithfully so a
            # FOLLOW-UP fees question is answered with the itemized DIFs, not the
            # coarse label. (The label was hardcoded here, which made the chat report
            # "coarse, not itemized" even though the payload had the $23,402 DIFs —
            # the same lossy-re-render class of bug as the dropped owner field.)
            breakdown = val.get("impact_fee_breakdown") or []
            if breakdown:
                items = "; ".join(
                    f"{c.get('name')} ${c.get('amount_per_unit', 0):,.0f}" for c in breakdown
                )
                dif_total = val.get("itemized_city_dif_per_unit") or val["impact_fees_per_unit"]
                lines.append(
                    f"Impact fees/unit: itemized city DIFs total ${dif_total:,.0f} — {items}."
                )
                if val.get("impact_fees_basis"):
                    lines.append(f"  ({val['impact_fees_basis']})")
            else:
                lines.append(
                    f"Impact fees/unit: ${val['impact_fees_per_unit']:,.0f} "
                    "[coarse regional aggregate — not itemized, not the city's DIF schedule]"
                )
        if val.get("market"):
            lines.append(f"Cost-model market: {val['market']}")

    sens = payload.get("sensitivity") or {}
    if sens.get("scenarios"):
        lines.append(
            f"Sensitivity (max land price; base ${sens.get('base_max_land_price', 0):,.0f} "
            f"at ${sens.get('base_construction_psf', 0):,.0f}/sf construction & "
            f"${sens.get('base_adv_per_unit', 0):,.0f}/unit exit) — negative = does not pencil:"
        )
        for s in sens["scenarios"]:
            lines.append(f"  • {s}")
        lines.append("  (Cite these for construction/exit 'what if' — do NOT invent ranges.)")

    ent = payload.get("entitlement") or {}
    if ent:
        lines.append(
            f"Entitlement: {ent.get('path')} "
            f"(~{ent.get('est_timeline_months')} mo, "
            f"impact fee/unit ${ent.get('impact_fee_per_unit', 0):,.0f})"
        )
        if ent.get("utilities_note"):
            lines.append(f"Utilities: {ent['utilities_note']}")

    risk = payload.get("site_risk") or {}
    if risk:
        lines.append(
            f"Site risk: flood zone {risk.get('flood_zone')} "
            f"(SFHA={risk.get('in_special_flood_hazard_area')}), "
            f"wetlands={risk.get('has_wetlands')}, overall={risk.get('overall_risk')}"
        )
        geo = risk.get("geologic_hazard") or {}
        if geo:
            lines.append(
                f"  Geologic (CGS): fault={geo.get('fault_zone')}; "
                f"landslide={geo.get('landslide_zone')}; "
                f"liquefaction={geo.get('liquefaction_zone')} "
                f"(evaluated={geo.get('evaluated')})"
            )
    coastal = payload.get("coastal_height_overlay") or {}
    if coastal:
        lines.append(
            f"Coastal (Prop D): applies={coastal.get('applies')} "
            f"(status={coastal.get('status')}, limit={coastal.get('height_limit_ft')} ft)"
        )

    dev = payload.get("development_activity") or {}
    if dev:
        holders = ", ".join(dev.get("permit_holders") or []) or "n/a"
        lines.append(
            f"Development activity: {dev.get('permit_count')} city permits on record "
            f"({dev.get('active_permit_count')} active); holders: {holders}. "
            "This parcel may ALREADY be an active development (owned/entitled), not raw "
            "land — say so before any 'what can I pay for the land' answer."
        )

    upside = payload.get("ca_upside") or {}
    if upside:
        lines.append(
            f"CA upside (separate from the firm base {upside.get('base_units')}): "
            f"max potential {upside.get('max_potential_units')} units, ONLY via these "
            "programs (do NOT invent others, e.g. no 'SB9' unless listed):"
        )
        for p in upside.get("programs", []):
            lines.append(
                f"  • {p.get('name')} ({p.get('statute')}): +{p.get('additional_units')} "
                f"→ {p.get('potential_units')} units [{p.get('eligibility')}]"
            )

    etr = payload.get("entitlement_timeline_risk") or {}
    if etr:
        lines.append(
            f"Timeline risk: ~{etr.get('est_months_min')}–{etr.get('est_months_max')}mo "
            f"({etr.get('risk_level')}), confidence={etr.get('confidence')}"
        )
        for d in etr.get("key_drivers") or []:
            lines.append(f"  Timeline driver: {d}")
        if etr.get("active_permits_exist"):
            lines.append("  Active permits on parcel — some approvals may already be in process.")
        for d in etr.get("ceqa_strong_matches") or []:
            sch = f"SCH {d.get('sch')}" if d.get("sch") else ""
            lines.append(
                f"  CEQA on parcel ({d.get('type')} {sch}, {d.get('match_basis')}): {d.get('url')}"
            )
        cands = etr.get("ceqa_candidates") or []
        if cands:
            lines.append(
                "  Possible related CEQA filings requiring verification — NOT confirmed on "
                "this parcel; do NOT cite as this parcel's CEQA status or use in the timeline:"
            )
            for d in cands[:5]:
                sch = f"SCH {d.get('sch')}" if d.get("sch") else ""
                lines.append(
                    f"    - {d.get('type')} {sch} ({d.get('match_basis')}): {d.get('url')}"
                )

    opr = payload.get("opposition_risk") or {}
    if opr:
        lines.append(
            f"Opposition risk: {opr.get('risk_level')} "
            f"(confidence={opr.get('confidence')} — qualitative, not a prediction)"
        )

    warnings = payload.get("warnings") or []
    for w in warnings[:4]:
        lines.append(f"Warning: {w}")

    lines.append(
        "\nUSE THESE NUMBERS for any follow-up about this property — what you can pay, "
        "comps, exit, fees, risk, entitlement, upside. Do NOT re-derive them with "
        "hypothetical/typical assumptions, do NOT invent alternative ordinance readings, "
        "and do NOT suggest ingesting data or 'verifying with the city' — the analysis is "
        "already grounded. PROVISIONAL means automated source-verification was "
        "inconclusive (flag it as such); it does NOT mean data is missing or that you "
        "should substitute a guess. Only call analyze_property again for a DIFFERENT address."
    )
    return "\n".join(lines)


# Source / trust / citation questions about an already-grounded property. These
# are answered DETERMINISTICALLY (below), not by the NIM narrator — it fabricated
# "§131.0445(a)" with an invented quote when asked "what's the source?".
_SOURCE_QUERY_RE = re.compile(
    r"\b(?:"
    r"what'?s?\s+the\s+source|what\s+is\s+the\s+source|the\s+source\b|"
    r"cite|citation|"
    r"where\s+(?:does|did)\s+(?:that|this|it|the\s+\w+)\s+come\s+from|"
    r"how\s+do\s+you\s+know|how\s+(?:can|do)\s+i\s+(?:know|trust)|"
    r"can\s+i\s+trust|should\s+i\s+trust|"
    r"is\s+(?:that|this|it)\s+(?:right|accurate|correct|reliable|verified|true)|"
    r"prove\s+it|back\s+(?:that|this|it)\s+up|"
    r"what'?s?\s+(?:the\s+)?basis|on\s+what\s+basis|"
    r"what\s+(?:code|ordinance|section|statute|regulation)\b"
    r")\b",
    re.IGNORECASE,
)


def _is_source_query(message: str) -> bool:
    """True when the user is asking for the source / trustworthiness of the numbers."""
    return bool(_SOURCE_QUERY_RE.search(message or ""))


# A property deal/source question whose answer must come from the grounded engine
# (units, value, fees, risk, entitlement, upside). The weak NIM model otherwise
# answers these from lookup + its own knowledge, bypassing the grounding — so we
# force analyze_property when one of these is asked (see the chat handler).
_DEAL_QUERY_RE = re.compile(
    r"\b(?:"
    r"units?|dwelling|densit(?:y|ies)|by[-\s]?right|buildable|build\s+(?:on|here|out)|"
    r"far\b|floor\s+area|setbacks?|max\s+height|stories|lot\s+coverage|"
    r"worth|valu(?:e|ation)|pay\s+for|residual|pencils?|margins?|pro\s*forma|"
    r"exit|adv\b|comps?\b|comparable|land\s+(?:price|value)|asking\s+price|"
    r"impact\s+fee|dev(?:elopment)?\s+fee|\bdif\b|fees?\s+per\s+unit|"
    r"flood|coastal|wetland|geologic|seismic|liquefaction|landslide|fault\s+zone|"
    r"airport|site\s+risk|hazard|"
    r"entitle|\bcup\b|conditional\s+use|rezon|\badu\b|sb\s?9|density\s+bonus|upside"
    r")\b",
    re.IGNORECASE,
)

# Extract a US street address from free text (street # + name + suffix, optional
# city/state/zip) so a deal question can self-resolve its parcel.
_ADDRESS_RE = re.compile(
    r"\d{1,6}\s+[A-Za-z0-9.'\-]+(?:\s+[A-Za-z0-9.'\-]+)*?\s+"
    # \b after the suffix so "st" doesn't match inside "Street" and truncate there.
    r"(?:st|street|ave|avenue|blvd|boulevard|rd|road|dr|drive|ln|lane|way|ct|court|"
    r"pl|place|cir|circle|ter|terrace|hwy|highway|pkwy|parkway|sq|square|trl|trail)\b"
    # City/state/ZIP tail, tolerant of the comma users often type before the ZIP
    # ("San Diego, CA, 92110"). Without that tolerance the group failed and the
    # address truncated to just the street ("1233 Hueneme St"), which geocodes at
    # low confidence and breaks forced grounding (the 6-units/no-owner regression).
    # ZIP stays required here: it anchors the lazy city matcher so it expands to the
    # full city instead of stopping after two letters ("San Di").
    r"\.?(?:,?\s+[A-Za-z .'\-]+?,?\s+[A-Za-z]{2},?\s+\d{5}(?:-\d{4})?)?",
    re.IGNORECASE,
)


def _needs_grounded_analysis(message: str) -> bool:
    """True when a message is a property deal/source question that must be grounded."""
    return bool(_is_source_query(message) or _DEAL_QUERY_RE.search(message or ""))


def _norm_addr(address: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (address or "").lower())


def _analysis_covers_address(analysis: dict | None, address: str) -> bool:
    """True when an existing grounded analysis already covers ``address``."""
    if not (analysis and analysis.get("address") and address):
        return False
    a, b = _norm_addr(analysis["address"]), _norm_addr(address)
    return bool(a and b and (a.startswith(b) or b.startswith(a)))


def _message_names_new_parcel(message: str, existing: dict | None) -> bool:
    """True when the message names an explicit street address the active grounded
    analysis does NOT already cover.

    Naming a new parcel must (re)ground that parcel even WITHOUT a deal/source
    keyword. Otherwise a bare address ("1230 Hueneme St") or a non-deal question
    about a named parcel ("who owns 1230 Hueneme St") left the grounded payload
    pinned to the PREVIOUS parcel: the owner/source echoes and the injected active
    context answered the stale property while the model free-formed the displayed
    one — the two silently diverged (1230 displayed, 1233 grounded). The inner
    force-analyze guard still skips a re-run when the address is already covered."""
    m = _ADDRESS_RE.search(message or "")
    if not m:
        return False
    return not _analysis_covers_address(existing, m.group(0).strip().rstrip(".,"))


def _resolve_deal_address(
    message: str,
    session_id: str,
    analysis: dict | None,
    report_context: object | None = None,
) -> str:
    """Resolve the parcel a deal question refers to: explicit address in the
    message, else the active grounded analysis, else the session property context,
    else the frontend-supplied report_context (the property on screen). Including
    report_context means a deal question about the displayed property forces a FRESH
    grounded analysis instead of leaning on a possibly-stale client snapshot."""
    m = _ADDRESS_RE.search(message or "")
    if m:
        return m.group(0).strip().rstrip(".,")
    if analysis and analysis.get("address"):
        return str(analysis["address"])
    ctx = _sessions.get_property_context(session_id)
    if ctx and ctx.get("address"):
        return str(ctx["address"])
    if report_context is not None:
        addr = getattr(report_context, "formatted_address", "") or getattr(
            report_context, "address", ""
        )
        if addr:
            return str(addr)
    return ""


# Display-hygiene: strip any leftover text-emitted tool-call blob (closed or
# dangling) so raw JSON never reaches the user. Parseable blobs are recovered and
# routed upstream in call_llm; this only cleans unparseable residue.
_TOOL_CALL_RESIDUE_RE = re.compile(r"<tool_call>.*?(?:</tool_call>|$)", re.DOTALL)

# Display-hygiene: a markdown link whose href is placeholder filler, not a real
# target. The weak narrator emits "[Art.01 Div.04](section link)" / "[here](link)" —
# a citation it wants to hyperlink but has no URL for — which renders as a dead link.
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]\n]+)\]\(([^)\n]*)\)")
_REAL_HREF_RE = re.compile(r"^(?:https?://|/|#|mailto:|tel:)", re.IGNORECASE)


def _strip_placeholder_links(text: str) -> str:
    """Collapse markdown links with a placeholder (non-URL) href to plain text.

    Keeps links with a real http(s)/anchor/mailto/tel target; for everything else
    (``[Art.01 Div.04](section link)``, ``[here](link)``, ``[breakdown](source)``) it
    drops the dead-link wrapper and keeps the visible label, so a citation reads as
    plain text instead of an un-clickable link. The deterministic source echo already
    formats real citations; this only cleans the model's free-formed narration."""
    if not text or "](" not in text:
        return text

    def _repl(m: re.Match[str]) -> str:
        label, href = m.group(1), m.group(2).strip()
        return m.group(0) if _REAL_HREF_RE.match(href) else label

    return _MARKDOWN_LINK_RE.sub(_repl, text)


def _build_source_answer(payload: dict) -> str | None:
    """Deterministic answer to 'what's the source / can I trust this?'.

    Reproduces a VERIFIED driver's exact citation + section straight from the
    grounded payload — no model narration — so the high-stakes citation cannot be
    fabricated or mis-attributed. Returns ``None`` when there is no verified, cited
    driver, so the caller falls back to the model (whose policy tells it to say the
    section wasn't captured rather than invent one).
    """
    by_right = payload.get("by_right") or {}
    drivers = by_right.get("verified_drivers") or []
    verified = [d for d in drivers if d.get("status") == "verified" and d.get("citation")]
    if not verified:
        return None

    max_units = by_right.get("max_units")
    zoning = payload.get("zoning_code") or "this zone"
    lot = payload.get("lot_size_sqft")
    lot_source = payload.get("lot_size_source") or ""
    lot_confirmed = lot_source == "assessor"
    lot_unconfirmed = lot_source == "geometry"

    # Prefer the driver matching the governing constraint, else the first verified.
    governing = by_right.get("governing_constraint") or ""
    driver = next((d for d in verified if d.get("field") == governing), verified[0])
    citation = (driver.get("citation") or "").strip().strip("•").strip()
    section = (driver.get("section") or "").strip()
    src_val = driver.get("source_value")
    label = driver.get("label") or driver.get("field") or "the governing constraint"

    lines = [
        f"**Source for the {max_units}-unit by-right count — {zoning}**",
        "",
        "This is source-verified: the count matches the exact San Diego Municipal "
        "Code sentence PlotLot retrieved for this parcel.",
        "",
        f'> "{citation}"' + (f"  — {section}" if section else ""),
        "",
    ]
    if src_val and lot:
        lot_label = (
            "county assessor — legal lot"
            if lot_confirmed
            else "GIS polygon ESTIMATE — confirm with assessor"
            if lot_unconfirmed
            else "lot area"
        )
        lines.append(f"- Governing constraint: {label} — {src_val:,.0f} sqft of lot area per unit")
        lines.append(f"- Lot area: {lot:,.0f} sqft ({lot_label})")
        lines.append(
            f"- Math: {lot:,.0f} sqft lot ÷ {src_val:,.0f} sqft/unit = "
            f"{lot / src_val:.2f} → **{max_units} units** (rounded down)"
        )
    if lot_unconfirmed:
        lines.append(
            "- Status: the density **rule** is VERIFIED against the ordinance, but the "
            "lot area is a GIS parcel-polygon estimate, not the recorded legal lot — so "
            f"the {max_units}-unit count is **PROVISIONAL** until the lot is confirmed "
            "with the county assessor (a different lot area changes the count)."
        )
    else:
        lines.append("- Verification status: **VERIFIED** against the retrieved ordinance text")
    if section:
        lines.append(
            f"\nThe quote above is the verbatim ordinance sentence from {section} — I'm "
            "not adding a finer subsection number or wording beyond what the retrieved "
            "text contains."
        )
    else:
        lines.append(
            "\nThe retrieved text didn't carry a section label, so I'm citing the "
            "sentence itself rather than guessing a subsection number."
        )

    # Honest provenance on the financial side — the unit count is verified, but the
    # exit/residual are regional estimates unless real comps were found.
    val = payload.get("valuation") or {}
    if val.get("adv_source") and val.get("adv_source") != "comps":
        lines.append(
            "\nNote: the unit count is verified, but the financial figures (exit value, "
            "residual) are regional estimates — no local sold-unit comps were found — so "
            "treat those as estimates, not appraised."
        )
    return "\n".join(lines)


# "Who owns this?" / "is it being developed?" — the owner of record is a county
# assessor lookup field (OWN_NAME1), not an inference, yet the weak NIM narrator
# intermittently claimed it was "not in the dataset" on follow-up turns (the
# persistent grounding block had dropped it). Detect these and answer them
# DETERMINISTICALLY from the grounded payload, the same way the citation echo
# removed the narrator's discretion over the high-stakes source quote.
_OWNER_QUERY_RE = re.compile(
    r"\b(?:"
    r"who\s+owns?|who'?s\s+the\s+owner|who\s+is\s+the\s+owner|whose\s+(?:property|parcel|lot|land)|"
    r"current\s+owner|owner\s+of\s+record|owner'?s?\s+name|ownership|owned\s+by|"
    r"who\s+holds?\s+(?:the\s+)?title|already\s+(?:being\s+)?develop|under\s+contract"
    r")\b",
    re.IGNORECASE,
)


def _is_owner_query(message: str) -> bool:
    """True when the user is asking who owns the parcel / whether it's being developed."""
    return bool(_OWNER_QUERY_RE.search(message or ""))


def _is_pure_owner_query(message: str) -> bool:
    """True only for a STANDALONE ownership question — safe to answer with the owner
    echo alone. A compound question that also asks a deal/source thing ("who owns it
    AND what's the residual?", "ownership rules for an ADU?") must NOT short-circuit,
    or the deal part is silently dropped; it goes to the model instead, which has the
    owner in its grounded context (the parity guard guarantees it) and is told to
    state it. This keeps the echo's anti-denial benefit without truncating answers."""
    return _is_owner_query(message) and not _needs_grounded_analysis(message)


def _echo_address_matches(message: str, *contexts: dict | None) -> bool:
    """Guard the deterministic echoes from answering the WRONG parcel.

    The owner/source echoes reproduce the CACHED analysis. If the user names a
    different explicit address than the one we have grounded data for, echoing the
    cache would return the wrong property's owner/citation — so return False and let
    the model resolve the new address. With no explicit address in the message the
    question is referential ("who owns it?") → True, use the active property."""
    m = _ADDRESS_RE.search(message or "")
    if not m:
        return True
    cand = m.group(0).strip().rstrip(".,")
    return any(_analysis_covers_address(ctx, cand) for ctx in contexts if ctx)


# "What are comps / what's land trading for nearby / what's my exit / what do
# finished units sell for?" — the exit (ADV) value, land-value range, and comp
# provenance are deterministic pipeline outputs. The weak narrator otherwise
# FABRICATES a table of specific nearby sales (invented addresses, lot sizes, and
# $/sqft the pipeline never produced) AND falsely claims it has no comps tool. Echo
# the grounded valuation instead — including the honest "no local sold comps were
# found, this is a regional estimate" when that is the case.
_COMPS_QUERY_RE = re.compile(
    r"\b(?:"
    r"comps?|comparable|comparables|"
    r"trading\s+for|selling\s+for|sell\s+for|sale\s+prices?|going\s+rate|resale|"
    r"price\s+per\s+(?:sq|square\s+foot|sf|acre)|"
    r"land\s+(?:sales|trading|comps)|"
    r"(?:my\s+)?exit(?:\s+(?:price|value|pricing|strategy))?|"
    r"what\s+do\s+(?:finished\s+)?units?\s+sell"
    r")\b",
    re.IGNORECASE,
)

# "What are San Diego's impact / development fees per unit?" — the fee schedule is a
# grounded payload field (itemized DIF line items WITH citations when a schedule is
# registered, else a labeled coarse aggregate). The narrator threw the verified DIFs
# away and invented a generic park/fire/library/water/school table from "similar
# municipalities" — so echo the grounded fees deterministically.
_FEE_QUERY_RE = re.compile(
    r"\b(?:"
    r"impact\s+fees?|development\s+fees?|dev\s+fees?|\bdifs?\b|"
    r"fees?\s+per\s+unit|per[-\s]?unit\s+fees?|permit\s+fees?"
    r")\b",
    re.IGNORECASE,
)

# A comps/fee question is only safe to answer with the deterministic echo ALONE when
# it isn't also asking a decision/density/risk/entitlement thing the echo would
# silently drop (mirrors _is_pure_owner_query). These markers force the full model
# path (which still runs forced grounding), so a compound question keeps every part.
_ECHO_DECISION_RE = re.compile(
    r"\b(?:"
    r"pencils?|does\s+(?:this|it)\s+(?:pencil|work|make\s+sense)|residual|"
    r"most\s+i\s+can\s+pay|max(?:imum)?\s+land|asking\s+price|should\s+i\s+(?:buy|pay|offer)|"
    r"how\s+many\s+units?|by[-\s]?right|buildable|"
    r"flood|coastal|wetland|geologic|seismic|liquefaction|landslide|fault|site\s+risk|"
    r"entitle|\bcup\b|conditional\s+use|rezon|timeline|how\s+long"
    r")\b",
    re.IGNORECASE,
)


def _is_pure_comps_query(message: str) -> bool:
    """Standalone comps/exit/land-value question — safe to answer from the echo alone."""
    msg = message or ""
    return bool(_COMPS_QUERY_RE.search(msg) and not _ECHO_DECISION_RE.search(msg))


def _is_pure_fee_query(message: str) -> bool:
    """Standalone impact/development-fee question — safe to answer from the echo alone."""
    msg = message or ""
    return bool(_FEE_QUERY_RE.search(msg) and not _ECHO_DECISION_RE.search(msg))


# "What if construction jumps 20% / exit softens 10%?" — the residual sensitivity grid
# is a grounded pipeline output (pre-labeled scenarios). The narrator otherwise
# re-derives the cells with its own wrong arithmetic and CONTRADICTS the grounded
# grid (it said construction +20% "pencils" when the grid says it does not). Echo the
# grid.
_SENSITIVITY_QUERY_RE = re.compile(
    r"\b(?:"
    r"what\s+if|sensitivit(?:y|ies)|stress(?:\s+test)?|downside|worst[-\s]?case|"
    r"construction\s+(?:jump|jumps|rise|rises|increase|increases|spike|spikes|up\b|"
    r"higher|overrun|goes?\s+up)|"
    r"(?:exit|price|value)\s+(?:soften|softens|soft\b|drop|drops|fall|falls|decline|"
    r"declines|lower|down\b|dip|dips)|"
    r"costs?\s+(?:go\s+up|rise|rises|increase|increases|jump|jumps)"
    r")\b",
    re.IGNORECASE,
)

# "What's the most I can pay / does this pencil at $X?" — the residual and its full
# cost stack are grounded; the narrator quoted the right residual but a fabricated
# breakdown (lot-area construction, no soft costs or builder margin). Echo the stack.
_RESIDUAL_QUERY_RE = re.compile(
    r"\b(?:"
    r"most\s+i\s+can\s+pay|max(?:imum)?\s+(?:land|i\s+can\s+pay|offer|price)|residual|"
    r"(?:does|will|would)\s+(?:this|it|that)\s+pencil|still\s+pencils?|"
    r"how\s+much\s+(?:can|should)\s+i\s+pay|what\s+can\s+i\s+pay|can\s+i\s+afford|"
    r"still\s+make\s+(?:margins?|money)|make\s+margins?"
    r")\b",
    re.IGNORECASE,
)

# A dollar amount in the message (asking price for the pencil test). Tolerates
# "$1,500,000", "$1.5M", "1.5 million", "750k". Only values ≥ $50k are treated as a
# land asking price so unit counts / percentages don't get read as money.
_MONEY_RE = re.compile(
    r"\$?\s*(\d[\d,]*(?:\.\d+)?)\s*(k|m|mm|million|thousand)?\b",
    re.IGNORECASE,
)


# "What's my ADU / density-bonus / SB9 upside?" — the applicable statutory programs
# are a grounded payload field (ca_upside.programs, with real statutes like ADU
# §65852.2 and Density Bonus §65915). The narrator invented "SB 9" applicability
# (SB 9 is a single-family lot-split law, not a multifamily program), a fabricated
# §143.0720, and "+2 bonus units" — so echo only the grounded programs.
_UPSIDE_QUERY_RE = re.compile(
    r"\b(?:"
    r"\badu\b|\bjadu\b|accessory\s+dwelling|"
    r"density\s+bonus|state\s+density|sb\s?9\b|"
    r"bonus\s+units?|how\s+many\s+more\s+units|additional\s+units|"
    r"unit\s+upside|density\s+upside"
    r")\b",
    re.IGNORECASE,
)

_SB9_RE = re.compile(r"\bsb\s?9\b", re.IGNORECASE)


def _mentions_sb9(message: str) -> bool:
    return bool(_SB9_RE.search(message or ""))


def _is_pure_upside_query(message: str) -> bool:
    """Standalone ADU/density-bonus/SB9 upside question — safe to answer from the echo
    alone (a compound decision/risk question keeps the full model path)."""
    msg = message or ""
    return bool(_UPSIDE_QUERY_RE.search(msg) and not _ECHO_DECISION_RE.search(msg))


def _is_sensitivity_query(message: str) -> bool:
    """True for a construction/exit 'what if' stress question."""
    return bool(_SENSITIVITY_QUERY_RE.search(message or ""))


def _is_residual_query(message: str) -> bool:
    """True for a 'most I can pay / does this pencil' residual question."""
    return bool(_RESIDUAL_QUERY_RE.search(message or ""))


def _extract_asking_price(message: str) -> float | None:
    """Largest plausible dollar amount in the message, or None — the asking price for
    a pencil test ('at a $1,500,000 asking price, does this pencil?')."""
    best: float | None = None
    for m in _MONEY_RE.finditer(message or ""):
        try:
            val = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        suffix = (m.group(2) or "").lower()
        if suffix in ("k", "thousand"):
            val *= 1_000
        elif suffix in ("m", "mm", "million"):
            val *= 1_000_000
        if val >= 50_000:
            best = val if best is None else max(best, val)
    return best


def _build_owner_answer(payload: dict | None, prop_ctx: dict | None) -> str | None:
    """Deterministic answer to 'who owns this / is it already being developed?'.

    The owner of record comes straight from the county assessor (OWN_NAME1) and is
    reliable run-to-run — but the narrator kept denying it existed on follow-ups
    after the grounding block stopped carrying it. Reproduce the owner (and any
    development-permit signals) verbatim from the grounded payload / session
    property context, bypassing the model. Returns ``None`` when no owner is known,
    so the caller falls back to the model (whose policy is to say a field is
    unavailable rather than invent one — never a silent wrong answer).
    """
    owner = ""
    if payload and payload.get("status") == "success":
        owner = str(payload.get("owner") or "").strip()
    if not owner and prop_ctx:
        owner = str(prop_ctx.get("owner") or "").strip()
    if not owner:
        return None

    addr = ""
    if payload and payload.get("address"):
        addr = str(payload["address"])
    elif prop_ctx and prop_ctx.get("address"):
        addr = str(prop_ctx["address"])

    lines = [
        "**Owner of record**",
        "",
        f"{owner} — per the county assessor record" + (f" for {addr}" if addr else "") + ".",
    ]

    # Development-permit signals (when grounded). Permit holders are
    # contractors/applicants, NOT necessarily the owner — keep them distinct so the
    # owner name isn't conflated with a sprinkler or construction company.
    dev = (payload or {}).get("development_activity") or {}
    if dev.get("permit_count"):
        active = dev.get("active_permit_count")
        active_note = f" ({active} active)" if active else ""
        lines += [
            "",
            "**Development activity**",
            "",
            f"{dev['permit_count']} city permits are on record{active_note} — this parcel "
            "may already be an active development, not raw land.",
        ]
        holders = ", ".join(dev.get("permit_holders") or [])
        if holders:
            lines.append(
                f"Permit holders (contractors/applicants, not necessarily the owner): {holders}."
            )
    return "\n".join(lines)


def _fmt_money(value: object) -> str | None:
    """Format a numeric dollar value, or None when it isn't a usable number."""
    try:
        return f"${float(value):,.0f}"  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _build_comps_answer(payload: dict | None) -> str | None:
    """Deterministic answer to 'what are comps / what's land trading for / what's my
    exit?'. Reproduces the grounded valuation — exit (ADV) per unit + range, GDV,
    land value, and the comp PROVENANCE — instead of letting the narrator fabricate a
    table of specific nearby sales (it invented addresses, lot sizes, and $/sqft the
    pipeline never produced, and falsely claimed it had no comps tool). When no local
    sold comps were found it says so plainly rather than inventing them. Returns
    ``None`` when no valuation was grounded, so the caller falls back to the model."""
    val = (payload or {}).get("valuation") or {}
    adv = val.get("adv_per_unit")
    adv_money = _fmt_money(adv)
    if not adv_money:
        return None

    adv_source = (val.get("adv_source") or "").strip()
    adv_rng = val.get("adv_per_unit_range") or []
    land_money = _fmt_money(val.get("estimated_land_value"))
    land_rng = val.get("land_value_range") or []
    gdv_money = _fmt_money(val.get("gross_development_value"))
    residual_money = _fmt_money(val.get("max_land_price_residual"))
    market = (val.get("market") or "").strip()
    state = ((payload or {}).get("state") or "").strip().upper()
    addr = (payload or {}).get("address") or ""
    units = ((payload or {}).get("by_right") or {}).get("max_units")

    def _range(rng: list) -> str:
        lo, hi = (_fmt_money(rng[0]), _fmt_money(rng[1])) if len(rng) == 2 else (None, None)
        return f" (range {lo}–{hi})" if lo and hi else ""

    lines = ["**Exit value & comps" + (f" — {addr}" if addr else "") + "**", ""]
    if adv_source == "comps":
        lines.append(
            f"- Finished-unit exit (ADV): **{adv_money}/unit**{_range(adv_rng)} — from "
            "sold-unit comparables near this parcel."
        )
        if units and gdv_money:
            lines.append(
                f"- Gross development value: {units} units × {adv_money}/unit = **{gdv_money}**."
            )
        if land_money:
            lines.append(f"- Implied land value from comps: {land_money}{_range(land_rng)}.")
    else:
        lines.append(
            "- No verified local sold-unit comps were found for this parcel, so I won't "
            "invent specific nearby sales. The exit is a **regional market estimate**: "
            f"**{adv_money}/unit**" + (f" ({market} market default)" if market else "") + "."
        )
        if state == "CA":
            lines.append(
                "- Why no comps: California's open parcel/assessor layers carry no sale "
                "price (assessed ≠ market) and there's no free sold-price feed — a real "
                "comp set needs a paid source or a broker pull."
            )
        else:
            lines.append(
                "- Treat the exit as an estimate, not appraised — no open sold-price comps "
                "were available for this market."
            )
        if units and gdv_money:
            lines.append(
                f"- At that estimate: {units} units × {adv_money}/unit = **{gdv_money}** gross "
                "development value (an estimate, not appraised)."
            )
        if residual_money:
            lines.append(
                f"- Grounded residual at this estimate: max land **{residual_money}** — what "
                "the deal supports, not what land is listed at."
            )
    return "\n".join(lines)


def _build_fees_answer(payload: dict | None) -> str | None:
    """Deterministic answer to 'what are the impact/development fees per unit?'.
    Reproduces the grounded fee schedule — the itemized DIF line items WITH citations
    when a real schedule is registered (plus the basis note explaining which fees are
    separate), else the labeled coarse aggregate. Never breaks a coarse aggregate into
    invented per-category amounts the way the narrator did (a fabricated park/fire/
    library/water/school table). Returns ``None`` when no fee figure was grounded."""
    val = (payload or {}).get("valuation") or {}
    per_unit = val.get("impact_fees_per_unit")
    breakdown = val.get("impact_fee_breakdown") or []
    basis = (val.get("impact_fees_basis") or "").strip()
    dif_total = val.get("itemized_city_dif_per_unit")
    if per_unit is None and not breakdown:
        return None

    units = ((payload or {}).get("by_right") or {}).get("max_units")
    addr = (payload or {}).get("address") or ""
    lines = ["**Impact / development fees" + (f" — {addr}" if addr else "") + "**", ""]

    if breakdown:
        lines.append("Verified itemized fees (per dwelling unit):")
        lines.append("")
        for c in breakdown:
            amt = _fmt_money(c.get("amount_per_unit"))
            cite = (c.get("citation") or "").strip()
            lines.append(
                f"- {c.get('name') or 'fee'}: {amt or 'n/a'}/unit" + (f" — {cite}" if cite else "")
            )
        itemized_total = dif_total
        if not itemized_total:
            comp_sum = sum((c.get("amount_per_unit") or 0) for c in breakdown)
            itemized_total = comp_sum or per_unit
        total_money = _fmt_money(itemized_total)
        if total_money:
            across = ""
            if units and isinstance(itemized_total, (int, float)):
                project = _fmt_money(itemized_total * units)
                across = f", or {project} across {units} units" if project else ""
            lines += ["", f"**Itemized total = {total_money}/unit{across}.**"]
        # The basis string already states which fees are separate (RTCIP/school/utility)
        # and the conservative all-in the residual budgets — reproduce it, don't paraphrase.
        if basis:
            lines += ["", basis]
    else:
        amt = _fmt_money(per_unit)
        across = ""
        if units and isinstance(per_unit, (int, float)):
            project = _fmt_money(per_unit * units)
            across = f" ({project} across {units} units)" if project else ""
        lines.append(f"- Impact/development fees budget at **{amt}/unit**{across}.")
        lines.append(
            "- This is a single coarse regional aggregate (school/park/traffic/utility "
            "combined), NOT an itemized published schedule — I won't break it into "
            "per-category amounts the data doesn't contain. For exact line items, pull the "
            "jurisdiction's current development-impact-fee schedule."
        )
    return "\n".join(lines)


def _build_residual_answer(payload: dict | None, message: str = "") -> str | None:
    """Deterministic answer to 'what's the most I can pay / does this pencil at $X?'.
    Reproduces the grounded residual COST STACK verbatim — GDV − hard − soft − builder
    margin − impact fees = max land — so the breakdown reconciles to the residual. The
    narrator quoted the right residual but a fabricated stack (it used the LOT area for
    construction and dropped soft costs and builder margin). When the message carries an
    asking price, adds the pencil verdict + gap. Returns ``None`` when no residual was
    grounded, so the caller falls back to the model."""
    val = (payload or {}).get("valuation") or {}
    residual = val.get("max_land_price_residual")
    if residual is None:
        return None
    residual_money = _fmt_money(residual)
    if not residual_money:
        return None

    addr = (payload or {}).get("address") or ""
    units = ((payload or {}).get("by_right") or {}).get("max_units")
    adv_source = (val.get("adv_source") or "").strip()
    lines = ["**Most you can pay (residual land value)" + (f" — {addr}" if addr else "") + "**", ""]
    lines.append(
        f"- **Max land price: {residual_money}**" + (f" across {units} units" if units else "")
    )
    if val.get("residual_formula"):
        lines.append(f"- Cost stack: {val['residual_formula']}")
    if val.get("hard_cost_basis"):
        lines.append(f"  - {val['hard_cost_basis']}")
    if adv_source and adv_source != "comps":
        lines.append(
            "- Exit value is a regional market estimate (no local sold comps), so treat "
            "the residual as an estimate, not appraised."
        )

    # Pencil test when the message names an asking price.
    asking = _extract_asking_price(message)
    if asking is not None and isinstance(residual, (int, float)):
        asking_money = _fmt_money(asking)
        if asking > residual:
            gap = _fmt_money(asking - residual)
            lines += [
                "",
                f"- **At {asking_money}, this does NOT pencil** — that's {gap} above the "
                f"{residual_money} the deal supports. You'd need lower construction cost, a "
                "higher exit, or more units to close the gap.",
            ]
        else:
            room = _fmt_money(residual - asking)
            lines += [
                "",
                f"- **At {asking_money}, this pencils** — {room} below the {residual_money} "
                "maximum, so the margin assumption holds with room to spare.",
            ]
    return "\n".join(lines)


def _build_sensitivity_answer(payload: dict | None) -> str | None:
    """Deterministic answer to 'what if construction +20% / exit softens 10%?'.
    Reproduces the grounded sensitivity scenarios verbatim. The narrator otherwise
    re-derives the cells with its own arithmetic and contradicts the grounded grid
    (it called construction +20% 'pencils' when the grid says it does not). Returns
    ``None`` when no sensitivity grid was grounded."""
    sens = (payload or {}).get("sensitivity") or {}
    scenarios = sens.get("scenarios") or []
    if not scenarios:
        return None

    addr = (payload or {}).get("address") or ""
    base = _fmt_money(sens.get("base_max_land_price"))
    base_constr = _fmt_money(sens.get("base_construction_psf"))
    base_adv = _fmt_money(sens.get("base_adv_per_unit"))
    lines = [
        "**Sensitivity — max land price under stress" + (f" — {addr}" if addr else "") + "**",
        "",
    ]
    if base:
        basis = []
        if base_constr:
            basis.append(f"{base_constr}/sf construction")
        if base_adv:
            basis.append(f"{base_adv}/unit exit")
        basis_note = f" (base {base}" + (f" at {', '.join(basis)}" if basis else "") + ")"
        lines.append(f"Negative = the deal does not pencil at that move{basis_note}:")
    else:
        lines.append("Negative = the deal does not pencil at that move:")
    lines.append("")
    for s in scenarios:
        lines.append(f"- {s}")
    lines += [
        "",
        "These are the grounded stress cells — I won't invent cost or price ranges beyond them.",
    ]
    return "\n".join(lines)


def _build_upside_answer(payload: dict | None, message: str = "") -> str | None:
    """Deterministic answer to 'what's my ADU / density-bonus / SB9 upside?'.
    Reproduces ONLY the grounded statutory programs (ca_upside.programs) — the narrator
    invented "SB 9" applicability (SB 9 is a single-family lot-split law, not a
    multifamily program), a fabricated §143.0720, and "+2 bonus units". When the user
    raises SB 9 and it is not among the applicable programs, says so plainly rather than
    inventing it. Returns ``None`` when no upside was grounded AND SB 9 wasn't raised, so
    the caller falls back to the model (whose policy is to not invent programs)."""
    upside = (payload or {}).get("ca_upside") or {}
    programs = upside.get("programs") or []
    sb9_raised = _mentions_sb9(message)
    if not programs and not sb9_raised:
        return None

    addr = (payload or {}).get("address") or ""
    zoning = (payload or {}).get("zoning_code") or ""
    base = upside.get("base_units")
    max_pot = upside.get("max_potential_units")
    lines = ["**Density upside" + (f" — {addr}" if addr else "") + "**", ""]
    if base is not None and max_pot is not None:
        lines.append(
            f"- Firm by-right base: **{base} units**. Statutory ceiling with programs: "
            f"**up to {max_pot} units** (eligibility maxima, not guaranteed)."
        )

    if programs:
        lines += [
            "",
            "Applicable programs (the only ones evaluated for this parcel — I won't invent others):",
        ]
        for p in programs:
            add = p.get("additional_units")
            pot = p.get("potential_units")
            delta = f": +{add} → {pot} units" if add is not None and pot is not None else ""
            elig = f" [{p.get('eligibility')}]" if p.get("eligibility") else ""
            lines.append(f"- {p.get('name')} ({p.get('statute')}){delta}{elig}")
    elif not sb9_raised:
        lines.append(
            "- No by-right statutory density program (ADU / density bonus) was found to add "
            "units on this parcel."
        )

    # Explicit SB 9 rebuttal when the user raises it and it isn't a grounded program.
    sb9_grounded = any(
        _mentions_sb9(p.get("name") or "")
        or "65852.21" in (p.get("statute") or "")
        or "66411.7" in (p.get("statute") or "")
        for p in programs
    )
    if sb9_raised and not sb9_grounded:
        zone_note = f" this {zoning} parcel" if zoning else " this parcel"
        lines += [
            "",
            "- **SB 9 does not apply here.** SB 9 (Gov. Code §65852.21 / §66411.7) is a "
            "lot-split / two-unit law for parcels in **single-family (R-1)** zones — it is "
            f"not among the programs applicable to{zone_note}.",
        ]
    return "\n".join(lines)


# "By-right, CUP, or rezone? how long?" — the entitlement path + timeline range +
# parcel-confirmed CEQA are grounded (entitlement.path, entitlement_timeline_risk);
# the narrator invented a 6–12mo by-right timeline (grounded is 2–6mo) and freelanced
# the path. Echo the grounded path + range + drivers + CEQA instead.
_TIMELINE_QUERY_RE = re.compile(
    r"\b(?:"
    r"timeline|how\s+long|how\s+many\s+months|when\s+can\s+i\s+(?:build|start|develop)|"
    r"by[-\s]?right\b|conditional\s+use|\bcup\b|rezon|entitle|"
    r"permit(?:ting)?\s+(?:time|timeline|long)|approval\s+time|"
    r"ceqa|environmental\s+review|\beir\b|\bmnd\b|\bnod\b|\bnoe\b"
    r")\b",
    re.IGNORECASE,
)


def _is_timeline_query(message: str) -> bool:
    """True for an entitlement-path / timeline / CEQA question."""
    return bool(_TIMELINE_QUERY_RE.search(message or ""))


def _build_timeline_answer(payload: dict | None) -> str | None:
    """Deterministic answer to 'by-right, CUP, or rezone? how long?'.

    Reproduces the grounded entitlement path + timeline range + drivers + any
    parcel-CONFIRMED CEQA filings (strong matches), labeling candidate filings as
    verify-only. The narrator otherwise invented the path and a wrong timeline (it
    said by-right is 6–12mo; the grounded range is 2–6mo). Returns ``None`` when no
    entitlement/timeline was grounded."""
    p = payload or {}
    ent = p.get("entitlement") or {}
    etr = p.get("entitlement_timeline_risk") or {}
    path = (ent.get("path") or "").strip()
    if not path and not etr:
        return None
    addr = p.get("address") or ""
    path_label = {
        "by_right": "By-right — no discretionary approval / public hearing required",
        "conditional_use": "Conditional Use Permit (CUP) — requires a public hearing",
        "rezoning": "Rezoning — a legislative act (multiple hearings, uncertain outcome)",
        "unknown": "Undetermined from the retrieved ordinance",
    }.get(path, path or "Undetermined")
    lines = ["**Entitlement path & timeline" + (f" — {addr}" if addr else "") + "**", ""]
    lines.append(f"- **Path: {path_label}**")
    lo, hi = etr.get("est_months_min"), etr.get("est_months_max")
    if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and hi > 0:
        lines.append(
            f"- **Estimated timeline: {lo:g}–{hi:g} months** "
            f"(risk {etr.get('risk_level', 'n/a')}, confidence {etr.get('confidence', 'low')})"
        )
    elif ent.get("est_timeline_months"):
        lines.append(f"- Estimated timeline: ~{ent['est_timeline_months']:g} months")
    for d in etr.get("key_drivers") or []:
        lines.append(f"  - {d}")
    if etr.get("active_permits_exist"):
        lines.append("  - Active permits already on the parcel — some approvals may be in process.")
    for d in etr.get("ceqa_strong_matches") or []:
        sch = f"SCH {d.get('sch')}" if d.get("sch") else ""
        lines.append(f"  - CEQA confirmed on this parcel: {d.get('type')} {sch} — {d.get('url')}")
    cands = etr.get("ceqa_candidates") or []
    if cands:
        lines.append(
            f"  - {len(cands)} possible nearby CEQA filing(s) exist but are NOT confirmed on "
            "this parcel — verify before relying on them; they do not affect the timeline."
        )
    return "\n".join(lines)


def _build_grounded_deal_answer(payload: dict | None, message: str) -> str | None:
    """Composite deterministic answer for a COMPOUND or decision deal question.

    Single-intent questions are handled by the dedicated echoes; this is the
    catch-all so a multi-part deal question ("what's the valuation AND the fees?",
    "most I can pay and still make margins?") gets the grounded numbers verbatim
    instead of the weak narrator freelancing them. Assembles only the field echoes
    the message actually touches; returns ``None`` if none of them are grounded."""
    msg = message or ""
    parts: list[str] = []

    def _add(answer: str | None) -> None:
        if answer:
            parts.append(answer)

    if _COMPS_QUERY_RE.search(msg) or re.search(
        r"\b(?:valuation|valu(?:e|ed)|worth|land\s+value)\b", msg, re.I
    ):
        _add(_build_comps_answer(payload))
    if _is_residual_query(msg):
        _add(_build_residual_answer(payload, msg))
    # Broader than _FEE_QUERY_RE (bare "fees") — safe here, already a grounded deal Q.
    if _FEE_QUERY_RE.search(msg) or re.search(r"\bfees?\b", msg, re.I):
        _add(_build_fees_answer(payload))
    if _is_timeline_query(msg):
        _add(_build_timeline_answer(payload))
    if _UPSIDE_QUERY_RE.search(msg):
        _add(_build_upside_answer(payload, msg))
    if _is_sensitivity_query(msg):
        _add(_build_sensitivity_answer(payload))

    if not parts:
        return None
    return "\n\n---\n\n".join(parts)


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


def _round(value: float | None, ndigits: int = 0) -> float | None:
    """Round a value for compact tool output, preserving None."""
    if value is None:
        return None
    return round(value, ndigits)


def _format_sensitivity(sens) -> dict:
    """Render the deterministic residual sensitivity into citable scenarios.

    ``sens.grid[row][col]`` is the max land price at construction $/sf (rows) ×
    ADV per unit (cols); negative means the deal no longer pencils. We pre-label
    each move as a percentage off the base case so the narrator can quote a stress
    result verbatim instead of inventing cost ranges (it previously freelanced
    "$150-200k/unit hard costs" and bogus negative-equity math).
    """
    base_row = sens.base_row_index
    base_col = sens.base_col_index
    base_constr = sens.row_values[base_row] if sens.row_values else 0.0
    base_adv = sens.col_values[base_col] if sens.col_values else 0.0

    def _pct(value: float, base: float) -> str:
        if not base:
            return ""
        delta = round((value / base - 1) * 100)
        return f"{delta:+d}%" if delta else "base"

    def _flag(cell: float) -> str:
        return "  (does not pencil)" if cell < 0 else ""

    scenarios: list[str] = []
    # Construction stress at base exit (vary the row).
    for i, constr in enumerate(sens.row_values):
        if i == base_row:
            continue
        cell = sens.grid[i][base_col]
        scenarios.append(
            f"Construction {_pct(constr, base_constr)} (${constr:,.0f}/sf): "
            f"${cell:,.0f}{_flag(cell)}"
        )
    # Exit stress at base construction (vary the column).
    for j, adv in enumerate(sens.col_values):
        if j == base_col:
            continue
        cell = sens.grid[base_row][j]
        scenarios.append(
            f"Exit {_pct(adv, base_adv)} (${adv:,.0f}/unit): ${cell:,.0f}{_flag(cell)}"
        )
    # Combined adverse stress: highest construction cost + one step below base exit
    # (a realistic "costs up AND exit soft" combo, more decision-relevant than the
    # extreme corner). Falls back to the bottom-left corner if exit has no base-1.
    if sens.row_values and sens.col_values:
        combo_col = base_col - 1 if base_col >= 1 else 0
        combo = sens.grid[-1][combo_col]
        scenarios.append(
            f"Construction {_pct(sens.row_values[-1], base_constr)} AND "
            f"Exit {_pct(sens.col_values[combo_col], base_adv)}: ${combo:,.0f}{_flag(combo)}"
        )

    return {
        "base_max_land_price": _round(sens.base_value),
        "base_construction_psf": base_constr,
        "base_adv_per_unit": base_adv,
        "scenarios": scenarios,
        "note": (
            "Max land price under stress. Negative = the deal does not pencil at "
            "that asking price. Cite these exact scenarios for construction/exit "
            "'what if' questions; do not invent cost or price ranges."
        ),
    }


def _format_grounded_analysis(report) -> dict:
    """Render a ZoningReport into the grounded payload the agent may cite.

    Every figure here is produced by the deterministic pipeline and carries its
    verification status. The agent is instructed (in the tool description and the
    system prompt) to repeat ONLY these numbers — never to compute or recall its
    own — which is what stops the chat agent from hallucinating unit counts,
    comps, fees, and flood zones the way it did before this tool existed.
    """
    out: dict[str, Any] = {
        "status": "success",
        "address": report.formatted_address or report.address,
        "municipality": report.municipality,
        "county": report.county,
        "state": report.state,
        "zoning_code": report.zoning_district or "",
        "zoning_description": report.zoning_description or "",
    }

    pr = report.property_record
    out["lot_size_sqft"] = _round(pr.lot_size_sqft, 0) if pr and pr.lot_size_sqft else None
    # Lot-size provenance gates trust: the unit count is lot ÷ min-lot-area, so a
    # count is only as firm as the lot area it was built on. "assessor" = the
    # recorded legal lot (authoritative); "geometry" = a GIS polygon estimate that
    # can diverge from the legal lot (it once read 6,471 vs the assessor's 7,710,
    # flipping 6↔7 units) — so a count on it is NOT firm. "" = unknown provider.
    lot_source = (pr.lot_size_source if pr else "") or ""
    out["lot_size_source"] = lot_source
    lot_unconfirmed = lot_source == "geometry"
    if lot_unconfirmed:
        out["lot_size_basis"] = (
            "lot area is a GIS parcel-polygon estimate, NOT the recorded legal lot — "
            "it can diverge from the assessor's figure; confirm before treating the "
            "unit count as firm"
        )
    elif lot_source == "assessor":
        out["lot_size_basis"] = (
            "lot area is the county assessor's recorded legal lot (authoritative)"
        )

    # Owner of record (county assessor OWN_NAME1) — a deterministic lookup field,
    # never an LLM guess. Carried in the grounded payload so it PERSISTS across
    # turns: the per-turn grounding block used to drop it, which let the narrator
    # claim "owner is not in the dataset" on follow-ups even though the assessor
    # record reliably returns it. Keep it here so the count's data carrier also
    # carries the owner.
    if pr and pr.owner:
        out["owner"] = pr.owner

    density = report.density_analysis
    ev = report.extraction_verification
    if density is not None:
        # A count built on an unconfirmed (geometry) lot area cannot be firm even
        # when the ordinance rule itself verified — the INPUT is unverified.
        provisional = bool(ev and ev.offer_is_provisional) or lot_unconfirmed
        out["by_right"] = {
            "max_units": density.max_units,
            "governing_constraint": density.governing_constraint,
            "confidence": density.confidence,
            "verification": "provisional" if provisional else "verified",
            "offer_is_provisional": provisional,
            "lot_size_confirmed": not lot_unconfirmed and lot_source == "assessor",
            "verified_drivers": [
                {
                    "field": f.field,
                    "label": f.label,
                    "status": f.status,
                    "source_value": f.source_value,
                    "citation": (f.citation[:240] if f.citation else ""),
                    "section": f.section,
                }
                for f in (ev.fields if ev else [])
            ],
        }
    else:
        out["by_right"] = None
        out["note"] = "No residential unit count could be computed for this parcel."

    comps = report.comp_analysis
    pf = report.pro_forma
    valuation: dict[str, Any] = {}
    if comps is not None:
        valuation["estimated_land_value"] = _round(comps.estimated_land_value)
        valuation["land_value_range"] = [
            _round(comps.estimated_land_value_low),
            _round(comps.estimated_land_value_high),
        ]
        valuation["adv_per_unit"] = _round(comps.adv_per_unit)
        valuation["adv_per_unit_range"] = [
            _round(comps.adv_per_unit_low),
            _round(comps.adv_per_unit_high),
        ]
        valuation["adv_source"] = comps.adv_source or "regional_default"
        valuation["comp_confidence"] = round(comps.confidence, 2)
    if pf is not None:
        valuation["max_land_price_residual"] = _round(pf.max_land_price)
        valuation["gross_development_value"] = _round(pf.gross_development_value)
        valuation["impact_fees_per_unit"] = _round(pf.impact_fees_per_unit)
        # Full residual COST STACK. The narrator otherwise reconstructed this from the
        # inputs and got it wrong — it multiplied $/sf by the LOT area instead of the
        # buildable area, and dropped soft costs and builder margin entirely, so its
        # listed costs didn't reconcile to the (correct) residual. Surface the exact
        # computed line items so every breakdown is read, not re-derived.
        valuation["hard_costs"] = _round(pf.hard_costs)
        valuation["soft_costs"] = _round(pf.soft_costs)
        valuation["builder_margin"] = _round(pf.builder_margin)
        valuation["impact_fees_total"] = _round(pf.impact_fees)
        if pf.gross_development_value and pf.max_land_price is not None:
            valuation["residual_formula"] = (
                f"GDV ${_round(pf.gross_development_value):,.0f} "
                f"− hard ${_round(pf.hard_costs):,.0f} "
                f"− soft ${_round(pf.soft_costs):,.0f} "
                f"− builder margin ${_round(pf.builder_margin):,.0f} "
                f"− impact fees ${_round(pf.impact_fees):,.0f} "
                f"= max land ${_round(pf.max_land_price):,.0f}"
            )
        if pf.max_units and pf.avg_unit_size_sqft and pf.construction_cost_psf:
            valuation["hard_cost_basis"] = (
                f"hard costs = {pf.max_units} units × {pf.avg_unit_size_sqft:,.0f} sqft/unit "
                f"× ${pf.construction_cost_psf:,.0f}/sf (BUILDABLE area — never the lot area)"
            )
        # If a real itemized fee schedule is registered for this jurisdiction, emit
        # the verified line items (the agent MAY cite these). Otherwise the fee is a
        # single coarse regional aggregate — label it so the agent can't invent a
        # park/fire/police breakdown the data doesn't contain.
        from plotlot.pipeline.fee_schedule import get_fee_schedule

        fee_schedule = get_fee_schedule(report.state, report.county)
        if fee_schedule is not None and fee_schedule.is_itemized:
            dif_total = _round(fee_schedule.total_per_unit)
            valuation["impact_fee_breakdown"] = [
                {
                    "name": c.name,
                    "amount_per_unit": _round(c.amount_per_unit),
                    "citation": c.citation,
                }
                for c in fee_schedule.components
            ]
            eff = (
                f" (effective {fee_schedule.effective_date})" if fee_schedule.effective_date else ""
            )
            if fee_schedule.covers_all_fees:
                # Comprehensive schedule IS the fee basis (also drives the residual).
                valuation["impact_fees_per_unit"] = dif_total
                valuation["impact_fees_basis"] = f"itemized from {fee_schedule.source}{eff}"
            else:
                # Partial schedule (SD city DIFs only): itemize the verified DIFs, but
                # leave impact_fees_per_unit as the residual's conservative all-in so the
                # offer is never optimistically understated.
                valuation["itemized_city_dif_per_unit"] = dif_total
                valuation["impact_fees_basis"] = (
                    f"{fee_schedule.source}{eff}. Verified City DIFs total "
                    f"${dif_total:,.0f}/unit (the itemized line items below). The residual "
                    f"budgets a conservative ${valuation['impact_fees_per_unit']:,.0f}/unit "
                    "all-in because RTCIP (SANDAG), school (SDUSD), and water/sewer capacity "
                    "fees are separate and not itemized here. Cite the verified DIF line "
                    "items; present the rest as additional separate fees — never invent amounts."
                )
        else:
            valuation["impact_fees_basis"] = (
                "coarse regional aggregate (school/park/traffic/utility combined) — "
                "NOT an itemized published schedule; do not break it into line items"
            )
        valuation["construction_cost_psf"] = _round(pf.construction_cost_psf)
        valuation["adv_per_unit"] = _round(pf.adv_per_unit)
        # Pre-format the exit value unambiguously so the narrator can't read the
        # PER-UNIT ADV as a project total (it did: "$750,000 total ($125k/unit)").
        if pf.adv_per_unit and density is not None and density.max_units:
            valuation["exit_value_formula"] = (
                f"{density.max_units} units x ${_round(pf.adv_per_unit):,.0f}/unit "
                f"(ADV per unit) = ${_round(pf.gross_development_value):,.0f} gross "
                "development value (GDV). ADV is PER UNIT — never divide it by the "
                "unit count."
            )
        valuation["adv_source"] = pf.adv_source or valuation.get("adv_source", "")
        if valuation["adv_source"] != "comps":
            valuation["adv_basis"] = (
                "regional market default — no local sold-unit comps were found; "
                "treat exit value and residual as estimates, not appraised"
            )
        valuation["market"] = pf.market
    out["valuation"] = valuation or None

    # Deterministic residual sensitivity (Task 3) — surface it so stress questions
    # ("what if construction +20% / exit -10%?") are answered from the grid instead
    # of the narrator freelancing invented cost ranges.
    sens = report.sensitivity
    if sens is not None and sens.grid:
        out["sensitivity"] = _format_sensitivity(sens)

    ent = report.entitlement
    if ent is not None:
        out["entitlement"] = {
            "path": ent.path,
            "complexity": ent.complexity,
            "est_timeline_months": _round(ent.est_timeline_months, 1),
            "impact_fee_per_unit": _round(ent.impact_fee_per_unit),
            "impact_fees_total": _round(ent.impact_fees_total),
            "utilities_note": ent.utilities_note,
        }

    sr = report.site_risk
    if sr is not None:
        fz = sr.flood_zone
        out["site_risk"] = {
            "flood_zone": fz.zone if fz else None,
            "in_special_flood_hazard_area": bool(fz and fz.in_sfha),
            "flood_risk_level": fz.risk_level if fz else "undetermined",
            "has_wetlands": sr.has_wetlands,
            "overall_risk": sr.overall_risk,
            "airport_influence": list(sr.airport_influence),
            "risk_flags": list(sr.risk_flags),
            "data_sources": sr.data_sources,
        }
        geo = sr.geologic
        if geo is not None:
            out["site_risk"]["geologic_hazard"] = {
                "fault_zone": geo.fault_zone,
                "landslide_zone": geo.landslide_zone,
                "liquefaction_zone": geo.liquefaction_zone,
                "in_any_hazard_zone": geo.in_any_hazard_zone,
                "evaluated": geo.evaluated,
                "flags": list(geo.flags),
                "source": "California Geological Survey (CGS) Seismic Hazard Zones",
            }

    co = report.coastal_overlay
    if co is not None and co.status != "not_applicable":
        out["coastal_height_overlay"] = {
            "applies": co.applies,
            "height_limit_ft": co.height_limit_ft,
            "status": co.status,
            "citation": co.citation,
        }

    dev = report.development_signals
    if dev and dev.get("permit_count"):
        out["development_activity"] = {
            "permit_count": dev.get("permit_count"),
            "active_permit_count": dev.get("active_permit_count"),
            "permit_holders": list(dev.get("unique_permit_holders") or [])[:8],
            "data_source": dev.get("data_source"),
            "note": (
                "This parcel has development permits on record with the city — it may "
                "already be an active development (owned/entitled), NOT raw land. Surface "
                "this before any 'what can I pay for the land' framing; the residual "
                "assumes the site is available to acquire and re-entitle."
            ),
        }

    etr = report.entitlement_timeline_risk
    if etr is not None:

        def _ceqa_brief(d):
            return {
                "sch": d.sch_number,
                "type": d.doc_type,
                "status": d.status,
                "title": d.title[:120],
                "url": d.source_url,
                "match_basis": d.match_basis,
                "match_confidence": d.match_confidence,
            }

        out["entitlement_timeline_risk"] = {
            "est_months_min": round(etr.est_months_min, 1),
            "est_months_max": round(etr.est_months_max, 1),
            "risk_level": etr.risk_level,
            "confidence": etr.confidence,
            "key_drivers": list(etr.key_drivers),
            "active_permits_exist": etr.active_permits_exist,
            # Tier 1 (parcel-confirmed, drives the timeline) vs Tier 2 (verify-only).
            "ceqa_strong_matches": [_ceqa_brief(d) for d in etr.ceqa_documents],
            "ceqa_candidates": [_ceqa_brief(d) for d in etr.ceqa_candidates],
        }

    opr = report.opposition_risk
    if opr is not None:
        out["opposition_risk"] = {
            "risk_level": opr.risk_level,
            "flags": list(opr.flags),
            "assessment": opr.assessment[:500] if opr.assessment else "",
            "confidence": opr.confidence,
        }

    uplift = report.density_uplift
    if uplift is not None:
        out["ca_upside"] = {
            "base_units": uplift.base_units,
            "max_potential_units": uplift.max_potential_units,
            "note": "Statutory maxima/eligibility ceilings, separate from the firm by-right count.",
            "programs": [
                {
                    "name": p.name,
                    "statute": p.statute,
                    "eligibility": p.eligibility,
                    "additional_units": p.additional_units,
                    "potential_units": p.potential_units,
                }
                for p in uplift.programs
            ],
        }

    # Surface only USER-FACING warnings. The extraction-verification warnings
    # (e.g. "6 u/ac contradicts source min lot area", "FAR 1.5 vs source 4") are
    # internal density-reconciliation diagnostics — the conflict is already
    # represented in by_right.verified_drivers' statuses, and leaking them as
    # top-level warnings just confuses the user (Q1 polish). Keep genuinely
    # actionable ones (e.g. ADV is a regional estimate).
    ev_warnings = set(ev.warnings) if ev else set()
    user_warnings = [w for w in (report.warnings or []) if w not in ev_warnings]
    if lot_unconfirmed and out.get("lot_size_sqft"):
        user_warnings.append(
            f"Lot area ({out['lot_size_sqft']:,.0f} sqft) is a GIS parcel-polygon "
            "estimate, not the recorded legal lot — confirm with the county assessor; "
            "the by-right unit count is provisional until it is."
        )
    if user_warnings:
        out["warnings"] = user_warnings

    out["grounding_note"] = (
        "These are the ONLY figures you may cite for this property. Do not add, "
        "round differently, or invent any number. If a field is null or absent, "
        "tell the user it is not available rather than estimating. If "
        "by_right.offer_is_provisional is true, present the unit count and offer "
        "as PROVISIONAL, not firm."
    )
    return out


async def _execute_analyze_property(address: str, session_id: str = "") -> str:
    """Run the full deterministic deal pipeline and return grounded numbers.

    This is the anti-hallucination engine for chat: the agent calls it instead of
    free-forming density, valuation, fees, or risk. It composes the same steps as
    ``/analyze`` (verified density → comps → residual → entitlement → site risk →
    CA uplift) via ``analyze_property_deep``.
    """
    if not address or not address.strip():
        return json.dumps({"status": "error", "message": "An address is required."})

    # Reuse a cached analysis for the same parcel — avoids re-running the ~minute
    # pipeline when grounding was already forced this turn (or computed on a prior
    # turn for this address), including a redundant model-issued call after forcing.
    if session_id:
        cached = _sessions.get_analysis(session_id)
        if _analysis_covers_address(cached, address):
            return json.dumps(cached)

    from plotlot.pipeline.analyze import analyze_property_deep

    try:
        report = await analyze_property_deep(address)
    except Exception as e:  # noqa: BLE001 — surface a structured error, never 500 the chat
        logger.warning("analyze_property failed for %s: %s", address[:60], e)
        return json.dumps({"status": "error", "message": f"Analysis failed: {str(e)[:200]}"})

    if report is None:
        return json.dumps(
            {
                "status": "not_found",
                "message": f"Could not geocode or analyze: {address}",
            }
        )

    # Persist lightweight property context so follow-up tools (document
    # generation, the active-property panel) stay consistent with this analysis.
    if session_id and report.property_record:
        pr = report.property_record
        _sessions.set_property_context(
            session_id,
            {
                "address": report.formatted_address or report.address,
                "municipality": report.municipality,
                "county": report.county,
                "state": report.state,
                "zoning_code": report.zoning_district or pr.zoning_code,
                "zoning_description": report.zoning_description,
                "lot_size_sqft": pr.lot_size_sqft,
                "owner": pr.owner,
            },
        )

    payload = _format_grounded_analysis(report)
    # Persist the grounded payload so EVERY follow-up turn can be answered from
    # these exact numbers (injected into the system prompt) without the model
    # re-deriving them from its own knowledge. This is what makes the grounding
    # stick across a conversation instead of only on the turn the tool ran.
    if session_id:
        _sessions.set_analysis(session_id, payload)
    return json.dumps(payload)


# Cap batch size so a chat turn can't kick off an unbounded analysis fan-out.
_MAX_SCREEN_ADDRESSES = 20


def _execute_calculate(expression: str) -> str:
    """Evaluate an arithmetic expression deterministically (no LLM mental math)."""
    from plotlot.pipeline.safe_calc import CalcError, safe_calculate

    try:
        result = safe_calculate(expression)
    except CalcError as exc:
        return json.dumps(
            {
                "status": "error",
                "expression": expression,
                "message": (
                    f"Could not evaluate '{expression}': {exc}. Pass arithmetic only "
                    "(numbers and + - * / // % ** and parentheses)."
                ),
            }
        )
    # Render an int cleanly when the result is whole (units, dollars).
    value: float | int = int(result) if result == int(result) else round(result, 4)
    return json.dumps({"status": "success", "expression": expression, "result": value})


def _execute_analyze_upzoning(args: dict) -> str:
    """Deterministic entitlement value-creation (subdivision/upzoning) analysis.

    Compares the by-right baseline yield to an upzoned target and computes the
    instant equity created — the developer's 'buy the gap' play. All math is
    deterministic; the per-lot value is a caller input, never fabricated.
    """
    from plotlot.pipeline.upzoning import analyze_upzoning

    def _num(key: str) -> float | None:
        v = args.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
        return None

    def _int(key: str) -> int | None:
        v = args.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
            return int(v)
        return None

    lot_sqft = _num("lot_sqft")
    if not lot_sqft or lot_sqft <= 0:
        return json.dumps(
            {"status": "error", "message": "A positive lot_sqft is required for upzoning analysis."}
        )

    a = analyze_upzoning(
        lot_sqft=lot_sqft,
        value_per_lot=_num("value_per_lot"),
        purchase_price=_num("purchase_price") or 0.0,
        entitlement_soft_costs=_num("entitlement_soft_costs") or 0.0,
        baseline_yield=_int("baseline_yield"),
        upzoned_yield=_int("upzoned_yield"),
        baseline_min_lot_area_sqft=_num("baseline_min_lot_area_sqft"),
        upzoned_min_lot_area_sqft=_num("upzoned_min_lot_area_sqft"),
        yield_basis=str(args.get("yield_basis") or "buildable lots"),
        value_source="comps" if args.get("value_source") == "comps" else "override",
    )

    def _scenario(s) -> dict | None:
        if s is None:
            return None
        return {
            "name": s.name,
            "yield_count": s.yield_count,
            "yield_basis": s.yield_basis,
            "value_per_yield": round(s.value_per_yield),
            "gross_value": round(s.gross_value),
            "instant_equity": round(s.instant_equity),
            "formula": s.formula,
        }

    return json.dumps(
        {
            "status": "success",
            "all_in_basis": round(a.all_in_basis),
            "value_source": a.value_source,
            "baseline": _scenario(a.baseline),
            "upzoned": _scenario(a.upzoned),
            "value_uplift": round(a.value_uplift),
            "equity_created": round(a.equity_created),
            "cost_per_yield": round(a.cost_per_yield),
            "exit_options": a.exit_options,
            "notes": a.notes,
            "warnings": a.warnings,
            "grounding_note": (
                "Cite these EXACT figures. Equity = (upzoned lots × per-lot value) − all-in "
                "basis. If value_source is 'missing', tell the user a per-lot value is needed "
                "and do NOT estimate the equity yourself."
            ),
        }
    )


async def _execute_screen_properties(args: dict) -> str:
    """Batch-screen a list of addresses against a buy box and rank the winners.

    Reuses the deterministic screening pipeline (``screen_addresses`` +
    ``analyze_property_full``) so rankings come from verified units + the
    residual offer — never the model's guess about which parcel is best.
    """
    from plotlot.pipeline.analyze import analyze_property_full
    from plotlot.pipeline.screening import BuyBox, screen_addresses

    raw = args.get("addresses") or []
    addresses = [a.strip() for a in raw if isinstance(a, str) and a.strip()][:_MAX_SCREEN_ADDRESSES]
    if not addresses:
        return json.dumps({"status": "error", "message": "Provide a list of addresses to screen."})

    buy_box = BuyBox(
        states=args.get("states") or [],
        counties=args.get("counties") or [],
        zoning_prefixes=args.get("zoning_prefixes") or [],
        min_lot_sqft=args.get("min_lot_sqft"),
        max_lot_sqft=args.get("max_lot_sqft"),
        min_units=args.get("min_units"),
        min_residual=args.get("min_residual"),
        exclude_high_flood_risk=bool(args.get("exclude_high_flood_risk", False)),
        require_verified=bool(args.get("require_verified", False)),
        max_results=int(args.get("max_results", 25)),
    )

    async def _analyze(addr: str):
        return await analyze_property_full(addr, with_comps=False)

    try:
        batch = await screen_addresses(
            addresses, buy_box, _analyze, concurrency=4, per_item_timeout=90.0
        )
    except Exception as e:  # noqa: BLE001 — structured error, never 500 the chat
        logger.warning("screen_properties failed: %s", e)
        return json.dumps({"status": "error", "message": f"Screening failed: {str(e)[:200]}"})

    def _row(r) -> dict:
        return {
            "address": r.address,
            "max_units": r.max_units,
            "max_land_price": _round(r.max_land_price),
            "zoning": r.zoning_district,
            "county": r.county,
            "state": r.state,
            "offer_is_provisional": r.offer_is_provisional,
        }

    return json.dumps(
        {
            "status": "success",
            "screened": batch.total,
            "qualified_count": batch.qualified_count,
            # Already ranked best-first (highest residual offer) by the pipeline.
            "qualified": [_row(r) for r in batch.qualified],
            "rejected_count": len(batch.rejected),
            "rejected_sample": [
                {"address": r.address, "reasons": r.reasons} for r in batch.rejected[:5]
            ],
            "error_count": len(batch.errors),
            "grounding_note": (
                "Rankings come from the deterministic residual offer on verified units. "
                "Cite only these results. Deals marked offer_is_provisional have an "
                "unverified unit count — flag them as provisional, not firm."
            ),
        }
    )


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


# Chat tools that execute through HarnessRuntime.call_tool (policy + evidence +
# events + one shared implementation with REST/MCP). This must cover EVERY chat
# tool: a name missing here silently falls back to the bespoke _execute_tool
# path below, which has no governance — the guard test in
# test_chat_runtime_routing.py enforces full coverage.
_RUNTIME_ROUTED_TOOLS = frozenset(
    {
        "geocode_address",
        "lookup_property_info",
        "search_zoning_ordinance",
        "search_municode_live",
        "discover_open_data_layers",
        "generate_document",
        "analyze_property",
        "calculate",
        "analyze_upzoning",
        "screen_properties",
        "web_search",
        "search_properties",
        "filter_dataset",
        "get_dataset_info",
        "export_dataset",
        "create_spreadsheet",
        "create_document",
    }
)


def _cached_grounded_analysis(session_id: str, address: str) -> dict | None:
    """Session-cached grounded payload covering ``address``, or None.

    Reusing it skips the ~minute analyze pipeline on repeat calls — including
    the model re-issuing analyze_property right after forced grounding already
    ran it this turn.
    """
    if not session_id:
        return None
    cached = _sessions.get_analysis(session_id)
    if _analysis_covers_address(cached, address):
        return cached
    return None


def _mirror_grounded_analysis_to_session(session_id: str, payload: Any) -> None:
    """Persist a runtime-produced grounded analysis into the chat session.

    The harness handler is session-free by design, so chat owns this mirroring:
    set_analysis keeps every follow-up turn answering from these exact numbers
    (the active-analysis context and the deterministic echoes read it), and
    set_property_context keeps doc-gen/panel defaults on the same parcel.
    """
    if not session_id or not isinstance(payload, dict):
        return
    if payload.get("status") != "success":
        return
    _sessions.set_analysis(session_id, payload)
    if not (payload.get("municipality") or payload.get("county")):
        return
    _sessions.set_property_context(
        session_id,
        {
            "address": payload.get("address", ""),
            "municipality": payload.get("municipality", ""),
            "county": payload.get("county", ""),
            "state": payload.get("state", ""),
            "zoning_code": payload.get("zoning_code", ""),
            "zoning_description": payload.get("zoning_description", ""),
            "lot_size_sqft": payload.get("lot_size_sqft"),
            "owner": payload.get("owner", ""),
        },
    )


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
    elif name == "analyze_property":
        return await _execute_analyze_property(args.get("address", ""), session_id=session_id)
    elif name == "calculate":
        return _execute_calculate(args.get("expression", ""))
    elif name == "analyze_upzoning":
        return _execute_analyze_upzoning(args)
    elif name == "screen_properties":
        return await _execute_screen_properties(args)
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

            # Build system prompt. The grounding policy is appended unconditionally —
            # it is the guard that keeps the agent citing tool output, not hallucinating.
            system_content = AGENT_SYSTEM_PROMPT + GROUNDING_POLICY

            # Force grounding FIRST (before choosing the context source). The weak NIM
            # model otherwise answers units/fees/comps/risk/entitlement from lookup +
            # its own knowledge, bypassing the grounded engine. Run analyze_property
            # deterministically (it persists the payload) so the verified numbers are
            # in context BEFORE the model speaks. Resolving the address also from
            # request.report_context means a deal question about the on-screen property
            # refreshes it. Cached per address: only the first deal question for a
            # parcel pays the latency; a non-resolvable address just falls through.
            #
            # We force not only on deal/source KEYWORDS but also whenever the message
            # NAMES A NEW PARCEL the active analysis doesn't cover — a bare address or
            # a non-deal question about a different address ("who owns 1230 ...") must
            # swap the grounded payload to that parcel, else the echoes and injected
            # context keep answering the previous one while the model free-forms the
            # named one (the 1230-displayed / 1233-grounded divergence).
            _existing = _sessions.get_analysis(session_id)
            if _needs_grounded_analysis(request.message) or _message_names_new_parcel(
                request.message, _existing
            ):
                _deal_addr = _resolve_deal_address(
                    request.message, session_id, _existing, request.report_context
                )
                if _deal_addr and not _analysis_covers_address(_existing, _deal_addr):
                    yield _sse_event(
                        "tool_use",
                        {
                            "tool": "analyze_property",
                            "args": {"address": _deal_addr},
                            "message": "Running grounded deal analysis...",
                        },
                    )
                    try:
                        await _execute_analyze_property(_deal_addr, session_id)
                    except Exception as exc:  # noqa: BLE001 — non-fatal; model can still answer
                        logger.warning("Forced analyze_property failed: %s", exc)

            # Choose the AUTHORITATIVE grounding source for the prompt. A freshly
            # computed grounded analysis SUPERSEDES the frontend-supplied
            # report_context — the browser can replay report_context stale from before
            # a backend fix, which is what made chat "crawl back" to 6 units / 6,471
            # sqft even after the assessor lot fix landed. When both exist, inject the
            # grounded analysis plus only report_context's NON-grounded extras
            # (setbacks, FAR, uses) so the stale lot/units/owner can't override the
            # verified ones. Fall back to report_context, then the lightweight session
            # context, only when no grounded analysis is available.
            active_analysis = _sessions.get_analysis(session_id)
            if active_analysis:
                if request.report_context:
                    system_content += _build_report_context(
                        request.report_context, suppress_grounded_fields=True
                    )
                system_content += _build_active_analysis_context(active_analysis)
            elif request.report_context:
                system_content += _build_report_context(request.report_context)
            else:
                # Lightweight property context from session even when no full
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
                    if prop_ctx.get("owner"):
                        ctx_lines.append(
                            f"- Owner of record (county assessor): {prop_ctx['owner']} "
                            "(state this if asked who owns it; do not say it is unavailable)"
                        )
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

            # Deterministic source/citation echo. The citation is too high-stakes to
            # leave to the NIM narrator (it fabricated "§131.0445(a)" with an invented
            # quote by borrowing a CONFLICTING field's section). When the user asks for
            # the source/trust of an already-grounded property, answer verbatim from the
            # verified driver — bypassing the model entirely for this fact.
            if (
                active_analysis
                and _is_source_query(request.message)
                and _echo_address_matches(request.message, active_analysis)
            ):
                source_answer = _build_source_answer(active_analysis)
                if source_answer:
                    yield _sse_event("tool_use", {"tool": "verified_source", "args": {}})
                    yield _sse_event("token", {"content": source_answer})
                    memory.append({"role": "assistant", "content": source_answer})
                    if len(memory) > MAX_MEMORY_MESSAGES:
                        del memory[:-MAX_MEMORY_MESSAGES]
                    yield _sse_event("done", {"full_content": source_answer})
                    return

            # Deterministic owner echo. The owner of record is a county-assessor
            # lookup field (reliable run-to-run), but the narrator kept claiming it
            # was "not in the dataset" on follow-up turns once the grounding block
            # dropped it. When asked who owns the parcel, answer verbatim from the
            # grounded payload / property context — bypassing the model. Falls
            # through to the model only when no owner is on record (then policy is to
            # say it's unavailable, never to invent one).
            _owner_prop_ctx = _sessions.get_property_context(session_id)
            if _is_pure_owner_query(request.message) and _echo_address_matches(
                request.message, active_analysis, _owner_prop_ctx
            ):
                owner_answer = _build_owner_answer(active_analysis, _owner_prop_ctx)
                if owner_answer:
                    yield _sse_event("tool_use", {"tool": "verified_owner", "args": {}})
                    yield _sse_event("token", {"content": owner_answer})
                    memory.append({"role": "assistant", "content": owner_answer})
                    if len(memory) > MAX_MEMORY_MESSAGES:
                        del memory[:-MAX_MEMORY_MESSAGES]
                    yield _sse_event("done", {"full_content": owner_answer})
                    return

            # Deterministic comps/exit echo. The exit (ADV) value and comp provenance
            # are grounded fields; the narrator otherwise fabricates a table of specific
            # nearby sales it never retrieved (invented addresses + $/sqft) and falsely
            # claims it has no comps tool. Answer from the grounded valuation instead —
            # including the honest "no local comps, this is a regional estimate".
            if (
                active_analysis
                and _is_pure_comps_query(request.message)
                and _echo_address_matches(request.message, active_analysis)
            ):
                comps_answer = _build_comps_answer(active_analysis)
                if comps_answer:
                    yield _sse_event("tool_use", {"tool": "verified_comps", "args": {}})
                    yield _sse_event("token", {"content": comps_answer})
                    memory.append({"role": "assistant", "content": comps_answer})
                    if len(memory) > MAX_MEMORY_MESSAGES:
                        del memory[:-MAX_MEMORY_MESSAGES]
                    yield _sse_event("done", {"full_content": comps_answer})
                    return

            # Deterministic impact-fee echo. The fee schedule (itemized DIF line items
            # with citations, or a labeled coarse aggregate) is grounded; the narrator
            # threw the verified DIFs away and invented a generic per-category table from
            # "similar municipalities". Answer from the grounded fees instead.
            if (
                active_analysis
                and _is_pure_fee_query(request.message)
                and _echo_address_matches(request.message, active_analysis)
            ):
                fees_answer = _build_fees_answer(active_analysis)
                if fees_answer:
                    yield _sse_event("tool_use", {"tool": "verified_fees", "args": {}})
                    yield _sse_event("token", {"content": fees_answer})
                    memory.append({"role": "assistant", "content": fees_answer})
                    if len(memory) > MAX_MEMORY_MESSAGES:
                        del memory[:-MAX_MEMORY_MESSAGES]
                    yield _sse_event("done", {"full_content": fees_answer})
                    return

            # Deterministic sensitivity echo. The residual sensitivity grid is grounded;
            # the narrator re-derived the cells with its own arithmetic and contradicted
            # the grid (calling construction +20% "pencils" when the grid says it does
            # not). Checked BEFORE the residual echo so a "what if … does it pencil?"
            # routes to the grid. Reproduce the grounded scenarios verbatim.
            if (
                active_analysis
                and _is_sensitivity_query(request.message)
                and _echo_address_matches(request.message, active_analysis)
            ):
                sens_answer = _build_sensitivity_answer(active_analysis)
                if sens_answer:
                    yield _sse_event("tool_use", {"tool": "verified_sensitivity", "args": {}})
                    yield _sse_event("token", {"content": sens_answer})
                    memory.append({"role": "assistant", "content": sens_answer})
                    if len(memory) > MAX_MEMORY_MESSAGES:
                        del memory[:-MAX_MEMORY_MESSAGES]
                    yield _sse_event("done", {"full_content": sens_answer})
                    return

            # Deterministic residual / pencil echo. The residual and its full cost stack
            # are grounded; the narrator quoted the right residual but a fabricated
            # breakdown (lot-area construction, no soft costs or builder margin, that
            # didn't reconcile). Reproduce the stack — and the pencil verdict when the
            # message names an asking price.
            if (
                active_analysis
                and _is_residual_query(request.message)
                and _echo_address_matches(request.message, active_analysis)
            ):
                residual_answer = _build_residual_answer(active_analysis, request.message)
                if residual_answer:
                    yield _sse_event("tool_use", {"tool": "verified_residual", "args": {}})
                    yield _sse_event("token", {"content": residual_answer})
                    memory.append({"role": "assistant", "content": residual_answer})
                    if len(memory) > MAX_MEMORY_MESSAGES:
                        del memory[:-MAX_MEMORY_MESSAGES]
                    yield _sse_event("done", {"full_content": residual_answer})
                    return

            # Deterministic density-upside echo. The applicable ADU/density-bonus
            # programs are grounded (ca_upside.programs); the narrator invented "SB 9"
            # applicability (a single-family lot-split law, not a multifamily program), a
            # fabricated §143.0720, and "+2 bonus units". Reproduce only the grounded
            # programs and rebut SB 9 when raised.
            if (
                active_analysis
                and _is_pure_upside_query(request.message)
                and _echo_address_matches(request.message, active_analysis)
            ):
                upside_answer = _build_upside_answer(active_analysis, request.message)
                if upside_answer:
                    yield _sse_event("tool_use", {"tool": "verified_upside", "args": {}})
                    yield _sse_event("token", {"content": upside_answer})
                    memory.append({"role": "assistant", "content": upside_answer})
                    if len(memory) > MAX_MEMORY_MESSAGES:
                        del memory[:-MAX_MEMORY_MESSAGES]
                    yield _sse_event("done", {"full_content": upside_answer})
                    return

            # Deterministic entitlement-path / timeline echo. The grounded path +
            # range + parcel-confirmed CEQA are authoritative; the narrator invented a
            # 6–12mo by-right timeline (grounded is 2–6mo) and freelanced the path.
            if (
                active_analysis
                and _is_timeline_query(request.message)
                and _echo_address_matches(request.message, active_analysis)
            ):
                timeline_answer = _build_timeline_answer(active_analysis)
                if timeline_answer:
                    yield _sse_event("tool_use", {"tool": "verified_timeline", "args": {}})
                    yield _sse_event("token", {"content": timeline_answer})
                    memory.append({"role": "assistant", "content": timeline_answer})
                    if len(memory) > MAX_MEMORY_MESSAGES:
                        del memory[:-MAX_MEMORY_MESSAGES]
                    yield _sse_event("done", {"full_content": timeline_answer})
                    return

            # Composite deterministic deal answer — the catch-all for a COMPOUND or
            # decision deal question that no single echo above fully handled ("valuation
            # AND fees?", "most I can pay and still make margins?"). Assemble the grounded
            # field answers the message touches so the numbers come from the payload, not
            # the narrator. Only fires for a grounded deal question about the analyzed parcel.
            if (
                active_analysis
                and _needs_grounded_analysis(request.message)
                and _echo_address_matches(request.message, active_analysis)
            ):
                deal_answer = _build_grounded_deal_answer(active_analysis, request.message)
                if deal_answer:
                    yield _sse_event("tool_use", {"tool": "verified_deal_facts", "args": {}})
                    yield _sse_event("token", {"content": deal_answer})
                    memory.append({"role": "assistant", "content": deal_answer})
                    if len(memory) > MAX_MEMORY_MESSAGES:
                        del memory[:-MAX_MEMORY_MESSAGES]
                    yield _sse_event("done", {"full_content": deal_answer})
                    return

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
                    # No tools — stream the text response. Strip any unparseable
                    # <tool_call> residue so raw tool-call JSON never reaches the
                    # user (parseable blobs were already recovered + routed upstream),
                    # and collapse dead placeholder citation links to plain text.
                    if content and "<tool_call>" in content:
                        content = _TOOL_CALL_RESIDUE_RE.sub("", content).strip()
                    content = _strip_placeholder_links(content)
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
                        "analyze_property": "Running grounded deal analysis...",
                        "screen_properties": "Screening parcels against your buy box...",
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

                        # Route chat tools through the shared harness runtime.
                        if fn_name in _RUNTIME_ROUTED_TOOLS:
                            # For generate_document: inject accumulated session evidence IDs
                            # when the agent didn't pass any (common case in chat-only flow).
                            if fn_name == "generate_document" and not fn_args.get("evidence_ids"):
                                accumulated = _sessions.get_evidence_ids(session_id)
                                if accumulated:
                                    fn_args = {**fn_args, "evidence_ids": accumulated}

                            cached_analysis = (
                                _cached_grounded_analysis(
                                    session_id, str(fn_args.get("address") or "")
                                )
                                if fn_name == "analyze_property"
                                else None
                            )
                            if cached_analysis is not None:
                                result = json.dumps(cached_analysis)
                            else:
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
                                                "owner": prop.get("owner", ""),
                                            },
                                        )
                                if fn_name == "analyze_property":
                                    _mirror_grounded_analysis_to_session(
                                        session_id, tool_result.result
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
            final_content = _strip_placeholder_links(final_content)
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
