from __future__ import annotations

import anthropic
import structlog

from outreach.config import settings
from outreach.core.types import Channel, ICPType, PitchContext, Prospect

logger = structlog.get_logger(__name__)

_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

PLOTLOT_CONTEXT = """
PlotLot is an AI-powered land analysis platform built for real estate and infrastructure professionals.

RESIDENTIAL PIPELINE:
- Input: any US property address
- Output: zoning code, density limits, setbacks, max buildable units, binding constraint, residual land valuation (pro forma)
- Live data: Sacramento, Santa Clara, Alameda, Contra Costa, San Mateo counties
- Key value: answers "what can I build here and does it pencil?" in <30 seconds vs 30 minutes manually

DATA CENTER PIPELINE:
- Input: any US site address
- Output: SiteScorecard across 5 signals — power (EIA), fiber (FCC), flood (FEMA), seismic (USGS), zoning compliance
- Works nationwide
- Key value: quick-filter for site originators before committing to full due diligence

SENDER: Earl Perry, founder of PlotLot
"""

SYSTEM_PROMPT = f"""You are Earl Perry, founder of PlotLot. You write short, direct, highly personalized
outreach messages to real estate and infrastructure professionals.

{PLOTLOT_CONTEXT}

WRITING RULES:
- Never use buzzwords: "game-changer", "revolutionary", "excited to", "reach out", "synergy"
- Lead with what PlotLot does for THEIR specific role, not what it is
- Close with a stress-test offer: "try it on an address you've already underwritten"
- Sound human — written by an engineer who built the tool, not a salesperson
- Match tone to channel: LinkedIn = professional brevity, Email = slightly warmer, Twitter = most casual
- For LinkedIn connection notes (200 char limit): lead with tool + market + role, end with offer
"""


async def write_pitch(ctx: PitchContext) -> str:
    """
    Generate a personalized pitch for a prospect using Claude.
    Returns the message body as a plain string.
    """
    p = ctx.prospect
    icp_label = {
        ICPType.RESIDENTIAL: "residential land acquisition / homebuilder",
        ICPType.DATACENTER: "data center / infrastructure site origination",
        ICPType.PRESS: "CRE journalist / real estate media",
        ICPType.INVESTOR: "multifamily / infill investor",
    }[p.icp_type]

    char_constraint = ""
    if ctx.char_limit:
        char_constraint = f"\nCRITICAL: This message MUST be {ctx.char_limit} characters or fewer. Count carefully."

    prompt = f"""Write a {ctx.channel.value} outreach message for this prospect:

Name: {p.first_name} {p.last_name}
Title: {p.title}
Company: {p.company}
Market / Geography: {p.market}
ICP type: {icp_label}
LinkedIn URL: {p.linkedin_url or "N/A"}
Twitter: {p.twitter_handle or "N/A"}
Notes: {p.notes or "None"}

Channel: {ctx.channel.value}
PlotLot demo URL: {ctx.plotlot_demo_url}
Counties with live data: {ctx.plotlot_counties}
{char_constraint}

Write ONLY the message body. No subject line, no greeting prefix like "Message:", no explanation.
Sign off as: — Earl
"""

    response = _client.messages.create(
        model=settings.anthropic_model,
        max_tokens=600,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    pitch = response.content[0].text.strip()
    logger.info("pitch_written", prospect=p.name, channel=ctx.channel.value, chars=len(pitch))
    return pitch


async def write_email_subject(prospect: Prospect) -> str:
    """Generate a cold email subject line for a prospect."""
    p = prospect
    prompt = f"""Write a cold email subject line for this prospect:

Name: {p.first_name} {p.last_name}
Title: {p.title}
Company: {p.company}
ICP: {p.icp_type.value}

Rules:
- Under 60 characters
- No clickbait, no ALL CAPS, no emojis
- Reference their role or market specifically
- Sound like it's from a founder, not a marketing team
- Examples of good subject lines:
  "AI zoning tool for D.R. Horton's NorCal land pipeline"
  "PlotLot — density calc for Bay Area land acq"
  "Site scoring for data center origination"

Output ONLY the subject line, nothing else.
"""
    response = _client.messages.create(
        model=settings.anthropic_model,
        max_tokens=80,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip().strip('"')
