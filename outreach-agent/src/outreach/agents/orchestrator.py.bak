from __future__ import annotations

"""
OutreachOrchestrator — the main Claude agent loop.

Uses Claude tool use to decide what to do each run:
  1. find_prospects     → discover new targets
  2. enrich_emails      → find work emails for queued prospects
  3. run_email_campaign → send personalized cold emails
  4. scout_events       → find networking events to attend
  5. queue_linkedin     → draft LinkedIn messages for manual review
  6. queue_twitter      → draft Twitter DMs for manual review
  7. get_pipeline_stats → report on current prospect pipeline
"""

import json
from datetime import datetime, timezone

import anthropic
import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from outreach.agents.email_agent import enrich_email, run_email_campaign
from outreach.agents.event_scout import scout_events
from outreach.agents.pitch_writer import write_pitch
from outreach.agents.prospect_finder import find_prospects
from outreach.config import settings
from outreach.core.db import EventRow, OutreachMessageRow, ProspectRow, SessionLocal, init_db
from outreach.core.types import (
    Channel,
    Event,
    ICPType,
    OutreachMessage,
    PitchContext,
    Prospect,
    ProspectStatus,
)

logger = structlog.get_logger(__name__)

_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

TOOLS: list[dict] = [
    {
        "name": "find_prospects",
        "description": "Search for new prospects (VP Land Acquisition, site selectors, investors, journalists) "
                       "via web search and parse them into the pipeline. Call when the queued prospect count is low.",
        "input_schema": {
            "type": "object",
            "properties": {
                "icp_types": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["residential", "datacenter", "press", "investor"]},
                    "description": "Which ICP types to search for. Omit for all.",
                },
            },
        },
    },
    {
        "name": "enrich_emails",
        "description": "Find work emails for queued prospects that don't have one yet via Hunter.io.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "run_email_campaign",
        "description": "Draft personalized cold emails and send them to queued prospects with verified emails.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dry_run": {
                    "type": "boolean",
                    "description": "If true, draft emails but do not send. Useful for review.",
                },
            },
        },
    },
    {
        "name": "scout_events",
        "description": "Discover upcoming in-person networking events (ULI, BIA, NAIOP, etc.) "
                       "where PlotLot's ICP will be present. Returns ranked events with pitch strategy.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "queue_linkedin",
        "description": "Draft LinkedIn connection notes and follow-up messages for queued prospects "
                       "and save them to the DB for manual sending or Playwright automation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "prospect_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Specific prospect IDs to draft for. Omit to draft for all queued.",
                },
            },
        },
    },
    {
        "name": "queue_twitter",
        "description": "Draft Twitter/X DMs for prospects who have a Twitter handle "
                       "and save to DB. Sends automatically if Twitter API is configured.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_pipeline_stats",
        "description": "Return current outreach pipeline stats: queued, emailed, connected, replied, demos.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


ORCHESTRATOR_SYSTEM = f"""You are an autonomous outreach agent for PlotLot, an AI-powered land analysis platform.

Your mission: find qualified prospects, reach out to them across email/LinkedIn/Twitter, and discover
in-person networking events — all on behalf of Earl Perry (founder).

PlotLot ICP:
- Residential: VP/Director Land Acquisition at homebuilders (D.R. Horton, Lennar, KB Home, etc.) in NorCal/Bay Area
- Data center: site originators at energy/infrastructure firms (nationwide)
- Press: CRE journalists who cover NorCal real estate transactions
- Investors: multifamily and infill investors in Bay Area/Sacramento

Each run, assess the pipeline and decide what actions to take. Be systematic:
1. If queued prospects < 10, find more
2. If prospects lack emails, enrich them
3. If prospects have emails and haven't been emailed, run the email campaign
4. Scout events weekly
5. Queue LinkedIn + Twitter messages for all uncontacted prospects
6. Report pipeline stats at the end

Today: {datetime.now(timezone.utc).strftime("%Y-%m-%d")}
"""


async def _execute_tool(name: str, inputs: dict, session: AsyncSession) -> str:
    """Execute a tool call and return the result as a JSON string."""

    if name == "get_pipeline_stats":
        stats = {}
        for status in ProspectStatus:
            count_result = await session.execute(
                select(func.count()).where(ProspectRow.status == status.value)
            )
            stats[status.value] = count_result.scalar() or 0
        event_count = await session.execute(select(func.count()).select_from(EventRow))
        stats["events_discovered"] = event_count.scalar() or 0
        return json.dumps(stats)

    if name == "find_prospects":
        icp_types = None
        if inputs.get("icp_types"):
            icp_types = [ICPType(t) for t in inputs["icp_types"]]
        prospects = await find_prospects(icp_types=icp_types)
        saved = 0
        for p in prospects:
            # Skip duplicates (check linkedin_url)
            if p.linkedin_url:
                existing = await session.execute(
                    select(ProspectRow).where(ProspectRow.linkedin_url == p.linkedin_url)
                )
                if existing.scalar_one_or_none():
                    continue
            row = ProspectRow(
                name=p.name, first_name=p.first_name, last_name=p.last_name,
                title=p.title, company=p.company, market=p.market,
                icp_type=p.icp_type.value, linkedin_url=p.linkedin_url,
                twitter_handle=p.twitter_handle, notes=p.notes, source=p.source,
            )
            session.add(row)
            saved += 1
        await session.commit()
        return json.dumps({"prospects_found": len(prospects), "prospects_saved": saved})

    if name == "enrich_emails":
        result = await session.execute(
            select(ProspectRow)
            .where(ProspectRow.status == ProspectStatus.QUEUED.value)
            .where(ProspectRow.email.is_(None))
            .limit(20)
        )
        rows = result.scalars().all()
        enriched = 0
        for row in rows:
            p = Prospect(
                id=row.id, name=row.name, first_name=row.first_name, last_name=row.last_name,
                title=row.title, company=row.company, market=row.market,
                icp_type=row.icp_type, email=row.email,
            )
            updated = await enrich_email(p)
            if updated.email:
                row.email = updated.email
                row.email_verified = updated.email_verified
                enriched += 1
        await session.commit()
        return json.dumps({"enriched": enriched, "checked": len(rows)})

    if name == "run_email_campaign":
        dry_run = inputs.get("dry_run", False)
        results = await run_email_campaign(session, dry_run=dry_run)
        sent = sum(1 for r in results if r.get("status") == "sent")
        return json.dumps({"emails_attempted": len(results), "emails_sent": sent, "dry_run": dry_run})

    if name == "scout_events":
        events = await scout_events()
        saved = 0
        for ev in events:
            row = EventRow(
                name=ev.name, organizer=ev.organizer,
                date=ev.date, location=ev.location,
                url=ev.url, description=ev.description,
                relevance_score=ev.relevance_score,
            )
            session.add(row)
            saved += 1
        await session.commit()
        top = [{"name": ev.name, "organizer": ev.organizer, "location": ev.location,
                "score": ev.relevance_score, "url": ev.url} for ev in events[:5]]
        return json.dumps({"events_discovered": len(events), "saved": saved, "top_events": top})

    if name == "queue_linkedin":
        prospect_ids = inputs.get("prospect_ids")
        query = select(ProspectRow).where(
            ProspectRow.status == ProspectStatus.QUEUED.value,
            ProspectRow.linkedin_url.isnot(None),
        )
        if prospect_ids:
            query = query.where(ProspectRow.id.in_(prospect_ids))
        result = await session.execute(query.limit(20))
        rows = result.scalars().all()
        drafted = 0
        for row in rows:
            p = Prospect(
                id=row.id, name=row.name, first_name=row.first_name, last_name=row.last_name,
                title=row.title, company=row.company, market=row.market, icp_type=row.icp_type,
                linkedin_url=row.linkedin_url, notes=row.notes,
            )
            # Connection note (200 char limit)
            ctx = PitchContext(
                prospect=p, channel=Channel.LINKEDIN,
                plotlot_demo_url=settings.plotlot_demo_url,
                plotlot_counties=settings.plotlot_counties,
                char_limit=200,
            )
            note = await write_pitch(ctx)
            msg_row = OutreachMessageRow(
                prospect_id=row.id, channel=Channel.LINKEDIN.value,
                body=note, status="drafted",
            )
            session.add(msg_row)
            drafted += 1
        await session.commit()
        return json.dumps({"linkedin_messages_drafted": drafted})

    if name == "queue_twitter":
        result = await session.execute(
            select(ProspectRow)
            .where(ProspectRow.status == ProspectStatus.QUEUED.value)
            .where(ProspectRow.twitter_handle.isnot(None))
            .limit(20)
        )
        rows = result.scalars().all()
        drafted = 0
        for row in rows:
            p = Prospect(
                id=row.id, name=row.name, first_name=row.first_name, last_name=row.last_name,
                title=row.title, company=row.company, market=row.market, icp_type=row.icp_type,
                twitter_handle=row.twitter_handle, notes=row.notes,
            )
            ctx = PitchContext(
                prospect=p, channel=Channel.TWITTER,
                plotlot_demo_url=settings.plotlot_demo_url,
                plotlot_counties=settings.plotlot_counties,
            )
            body = await write_pitch(ctx)
            msg_row = OutreachMessageRow(
                prospect_id=row.id, channel=Channel.TWITTER.value,
                body=body, status="drafted",
            )
            session.add(msg_row)
            drafted += 1
        await session.commit()
        return json.dumps({"twitter_messages_drafted": drafted})

    return json.dumps({"error": f"unknown_tool: {name}"})


async def run_agent(goal: str | None = None) -> str:
    """
    Run the outreach agent for one full cycle.
    Uses Claude tool use to decide which actions to take.
    Returns a plain-text summary of what was done.
    """
    await init_db()

    user_goal = goal or (
        "Run the full outreach cycle: check pipeline stats, find new prospects if needed, "
        "enrich emails, send the email campaign, scout events, and queue LinkedIn/Twitter messages."
    )

    messages = [{"role": "user", "content": user_goal}]

    async with SessionLocal() as session:
        while True:
            response = _client.messages.create(
                model=settings.anthropic_model,
                max_tokens=4096,
                system=ORCHESTRATOR_SYSTEM,
                tools=TOOLS,
                messages=messages,
            )

            # Append assistant turn
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                # Extract final text response
                for block in response.content:
                    if hasattr(block, "text"):
                        return block.text
                return "Outreach cycle complete."

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        logger.info("tool_call", name=block.name, inputs=block.input)
                        result = await _execute_tool(block.name, block.input, session)
                        logger.info("tool_result", name=block.name, result=result[:200])
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })

                messages.append({"role": "user", "content": tool_results})
                continue

            # Unexpected stop reason
            break

    return "Outreach cycle complete."
