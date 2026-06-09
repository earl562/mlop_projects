from __future__ import annotations

from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from outreach.core.db import OutreachMessageRow, ProspectRow
from outreach.core.types import Channel, OutreachMessage, PitchContext, Prospect, ProspectStatus
from outreach.agents.pitch_writer import write_email_subject, write_pitch
from outreach.config import settings
from outreach.tools.smtp_email import send_email
from outreach.tools.hunter import domain_from_company, find_email, verify_email

logger = structlog.get_logger(__name__)

# Rate limit: max emails per run to stay off spam radar
MAX_EMAILS_PER_RUN = getattr(settings, 'max_emails_per_run', 300)


async def enrich_email(prospect: Prospect) -> Prospect:
    """Find and verify a prospect's work email via Hunter.io."""
    domain = domain_from_company(prospect.company)
    if not domain:
        logger.info("domain_unknown", company=prospect.company)
        return prospect

    result = await find_email(prospect.first_name, prospect.last_name, domain)
    if not result:
        return prospect

    email = result["email"]
    score = result.get("score", 0)

    # Only use if confidence score ≥ 50
    if score >= 50:
        verify = await verify_email(email)
        if verify.get("result") not in ("undeliverable", "unknown"):
            prospect.email = email
            prospect.email_verified = True
            logger.info("email_enriched", name=prospect.name, email=email, score=score)

    return prospect


async def run_email_campaign(session: AsyncSession, dry_run: bool = False    ) -> list[dict[str, str]]:
    """
    Find queued prospects with emails, draft personalized pitches, and send.
    Returns a list of result dicts per email attempted.
    """
    # Load queued prospects who have an email
    result = await session.execute(
        select(ProspectRow)
        .where(ProspectRow.status == ProspectStatus.QUEUED.value)
        .where(ProspectRow.email.isnot(None))
        .limit(MAX_EMAILS_PER_RUN)
    )
    rows = result.scalars().all()

    if not rows:
        logger.info("no_queued_prospects_with_email")
        return []

    results = []
    for row in rows:
        prospect = Prospect(
            id=row.id,
            name=row.name,
            first_name=row.first_name,
            last_name=row.last_name,
            title=row.title,
            company=row.company,
            market=row.market,
            icp_type=row.icp_type,
            email=row.email,
            linkedin_url=row.linkedin_url,
            twitter_handle=row.twitter_handle,
            notes=row.notes,
        )

        ctx = PitchContext(
            prospect=prospect,
            channel=Channel.EMAIL,
            plotlot_demo_url=settings.plotlot_demo_url,
            plotlot_counties=settings.plotlot_counties,
        )

        body = await write_pitch(ctx)
        subject = await write_email_subject(prospect)

        if dry_run:
            logger.info("dry_run_email", to=prospect.email, subject=subject)
            results.append({"prospect": prospect.name, "email": prospect.email or "",
                            "subject": subject, "body": body, "status": "dry_run"})
            continue

        if not prospect.email:
            logger.warning("skip_no_email", prospect=prospect.name)
            continue

        attachment = settings.outreach_attachment_path or None
        send_result = await send_email(prospect.email, subject, body, attachment)
        status = send_result.get("status", "failed")

        # Save message to DB
        msg_row = OutreachMessageRow(
            prospect_id=row.id,
            channel=Channel.EMAIL.value,
            subject=subject,
            body=body,
            status=status,
            sent_at=datetime.now(timezone.utc) if status == "sent" else None,
            error=send_result.get("error"),
        )
        session.add(msg_row)

        # Update prospect status
        row.status = ProspectStatus.EMAIL_SENT.value if status == "sent" else row.status
        row.updated_at = datetime.now(timezone.utc)

        await session.commit()
        logger.info("email_campaign_result", prospect=prospect.name, status=status)
        results.append({"prospect": prospect.name, "email": prospect.email,
                        "subject": subject, "status": status})

    return results
