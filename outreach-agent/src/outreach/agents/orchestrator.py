from __future__ import annotations

"""
OutreachOrchestrator — the main agent loop.

Follows a systematic approach to manage the outreach pipeline:
1. If queued prospects < 10, find more
2. If prospects lack emails, enrich them
3. If prospects have emails and haven't been emailed, run the email campaign
4. Scout events weekly
5. Queue LinkedIn + Twitter messages for all uncontacted prospects
6. Report pipeline stats at the end
"""

import asyncio
import json
from datetime import datetime, timezone

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


async def run_agent(goal: str | None = None, dry_run: bool = False) -> str:
    """
    Run the outreach agent for one full cycle.
    Follows systematic logic instead of using external LLM for decision making.
    Returns a plain-text summary of what was done.
    """
    await init_db()

    # Default goal if none provided
    user_goal = goal or (
        "Run the full outreach cycle: check pipeline stats, find new prospects if needed, "
        "enrich emails, send the email campaign, scout events, and queue LinkedIn/Twitter messages."
    )

    logger.info("starting_outreach_agent", goal=user_goal, dry_run=dry_run)
    
    # Track what we did for the summary
    actions_taken = []

    async with SessionLocal() as session:
        # Step 1: Get initial pipeline stats
        stats_result = await _execute_tool("get_pipeline_stats", {}, session)
        stats = json.loads(stats_result)
        queued_count = stats.get("queued", 0)
        actions_taken.append(f"Initial pipeline check: {queued_count} queued prospects")

        # Step 2: If queued prospects < 10, find more
        if queued_count < 10:
            logger.info("queued_prospects_low", count=queued_count)
            find_result = await _execute_tool("find_prospects", {}, session)
            find_data = json.loads(find_result)
            actions_taken.append(
                f"Found {find_data['prospects_found']} prospects, saved {find_data['prospects_saved']} new ones"
            )
            # Update stats after finding
            stats_result = await _execute_tool("get_pipeline_stats", {}, session)
            stats = json.loads(stats_result)
            queued_count = stats.get("queued", 0)

        # Step 3: If prospects lack emails, enrich them
        # Check how many queued prospects lack emails
        result = await session.execute(
            select(func.count()).select_from(ProspectRow)
            .where(ProspectRow.status == ProspectStatus.QUEUED.value)
            .where(ProspectRow.email.is_(None))
        )
        no_email_count = result.scalar() or 0
        
        if no_email_count > 0:
            logger.info("prospects_lacking_emails", count=no_email_count)
            enrich_result = await _execute_tool("enrich_emails", {}, session)
            enrich_data = json.loads(enrich_result)
            actions_taken.append(
                f"Enriched emails for {enrich_data['enriched']} out of {enrich_data['checked']} prospects"
            )

        # Step 4: If prospects have emails and haven't been emailed, run email campaign
        # Check how many queued prospects have emails but haven't been emailed
        result = await session.execute(
            select(func.count()).select_from(ProspectRow)
            .where(ProspectRow.status == ProspectStatus.QUEUED.value)
            .where(ProspectRow.email.isnot(None))
            .outerjoin(
                OutreachMessageRow,
                (ProspectRow.id == OutreachMessageRow.prospect_id) &
                (OutreachMessageRow.channel == Channel.EMAIL.value)
            )
            .where(OutreachMessageRow.id.is_(None))  # No email sent yet
        )
        email_ready_count = result.scalar() or 0
        
        if email_ready_count > 0:
            logger.info("prospects_ready_for_email", count=email_ready_count)
            # Limit to MAX_EMAILS_PER_RUN per cycle to avoid sending too many at once
            email_limit = min(settings.max_emails_per_run, email_ready_count)
            email_result = await _execute_tool(
                "run_email_campaign", 
                {"dry_run": dry_run}, 
                session
            )
            email_data = json.loads(email_result)
            if dry_run:
                actions_taken.append(
                    f"Would send {email_data['emails_attempted']} emails (dry run)"
                )
            else:
                actions_taken.append(
                    f"Sent {email_data['emails_sent']} out of {email_data['emails_attempted']} emails"
                )

        # Step 5: Scout events (do this periodically - we'll do it every time for simplicity)
        # In a real implementation, you might want to check when last scouted
        logger.info("scouting_events")
        scout_result = await _execute_tool("scout_events", {}, session)
        scout_data = json.loads(scout_result)
        actions_taken.append(
            f"Discovered {scout_data['events_discovered']} events, saved {scout_data['saved']} new ones"
        )

        # Step 6: Queue LinkedIn + Twitter messages for all uncontacted prospects
        logger.info("queuing_social_messages")
        linkedin_result = await _execute_tool("queue_linkedin", {}, session)
        linkedin_data = json.loads(linkedin_result)
        twitter_result = await _execute_tool("queue_twitter", {}, session)
        twitter_data = json.loads(twitter_result)
        actions_taken.append(
            f"Queued {linkedin_data['linkedin_messages_drafted']} LinkedIn messages and "
            f"{twitter_data['twitter_messages_drafted']} Twitter messages"
        )

        # Step 7: Get final pipeline stats
        final_stats_result = await _execute_tool("get_pipeline_stats", {}, session)
        final_stats = json.loads(final_stats_result)
        actions_taken.append(
            f"Final pipeline: {final_stats.get('queued', 0)} queued, "
            f"{final_stats.get('email_sent', 0)} emailed, "
            f"{final_stats.get('events_discovered', 0)} events discovered"
        )

    # Create summary
    summary = "\n".join([f"✓ {action}" for action in actions_taken])
    logger.info("outreach_cycle_complete", actions=len(actions_taken))
    
    return f"Outreach cycle completed successfully:\n{summary}"


# Keep the old run_agent signature for backward compatibility with CLI
# but make it ignore the goal parameter since we're using systematic logic
def run_agent_sync(goal: str | None = None, dry_run: bool = False) -> str:
    """Synchronous wrapper for run_agent."""
    return asyncio.run(run_agent(goal, dry_run=dry_run))
