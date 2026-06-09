from __future__ import annotations

import structlog

from outreach.config import settings
from outreach.core.types import Channel, ICPType, PitchContext, Prospect

logger = structlog.get_logger(__name__)

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


async def write_pitch(ctx: PitchContext) -> str:
    """
    Generate a personalized pitch for a prospect using templates.
    Returns the message body as a plain string.
    """
    p = ctx.prospect
    icp_label = {
        ICPType.RESIDENTIAL: "residential land acquisition / homebuilder",
        ICPType.DATACENTER: "data center / infrastructure site origination",
        ICPType.PRESS: "CRE journalist / real estate media",
        ICPType.INVESTOR: "multifamily / infill investor",
    }[p.icp_type]

    # Template-based pitch generation
    first_name = p.first_name or ""
    company = p.company or "your company"
    market = p.market or "your area"
    
    # Different templates for different channels
    if ctx.channel == Channel.EMAIL:
        # Email template - slightly warmer
        pitch = f"""Hi {first_name},

I help {icp_label}s like you at {company} quickly analyze land opportunities in {market} with PlotLot.

Our AI-powered platform gives you instant zoning, density, and feasibility analysis for any US property—what normally takes 30 minutes of manual research happens in under 30 seconds.

Try it on an address you've already underwritten to see how it compares.

Regards,
Earl Perry
Founder, PlotLot"""
        
    elif ctx.channel == Channel.LINKEDIN:
        # LinkedIn template - professional brevity (200 char limit for connection notes)
        pitch = f"""Hi {first_name}, I'm Earl Perry, founder of PlotLot. We help {icp_label}s in {market} analyze land opportunities in <30 seconds instead of 30 minutes. Try it on an address you've underwritten."""
        
        # Truncate to 200 characters if needed for connection notes
        if ctx.char_limit and len(pitch) > ctx.char_limit:
            pitch = pitch[:ctx.char_limit-3] + "..."
            
    elif ctx.channel == Channel.TWITTER:
        # Twitter template - most casual
        pitch = f"""Hey {first_name}! I'm Earl from PlotLot. We built an AI tool that does instant land analysis for {icp_label}s in {market}. What takes 30 mins manually takes us 30 secs. Want to try it?"""
        
    else:
        # Default template
        pitch = f"""Hi {first_name},

I'm Earl Perry, founder of PlotLot. We help {icp_label}s like you at {company} analyze land opportunities in {market} much faster.

Instead of 30 minutes of manual research, our AI-powered platform gives you instant zoning, density, and feasibility analysis for any US property in under 30 seconds.

Try it on an address you've already underwritten to see the difference.

Regards,
Earl Perry
Founder, PlotLot"""

    # Apply character limit if specified
    if ctx.char_limit and len(pitch) > ctx.char_limit:
        # Try to truncate at a sentence boundary
        truncated = pitch[:ctx.char_limit]
        last_period = truncated.rfind('.')
        last_exclamation = truncated.rfind('!')
        last_question = truncated.rfind('?')
        last_sentence_end = max(last_period, last_exclamation, last_question)
        
        if last_sentence_end > ctx.char_limit * 0.7:  # If we can keep at least 70% and end at sentence
            pitch = pitch[:last_sentence_end + 1]
        else:
            pitch = truncated + "..."

    logger.info("pitch_written", prospect=p.name, channel=ctx.channel.value, chars=len(pitch))
    return pitch


async def write_email_subject(prospect: Prospect) -> str:
    """Generate a cold email subject line for a prospect using templates."""
    p = prospect
    first_name = p.first_name or ""
    company = p.company or "your company"
    icp_type = p.icp_type.value if p.icp_type else "professional"
    
    # Template-based subject lines
    if icp_type == "residential":
        subject = f"AI zoning tool for {company}'s {p.market} land pipeline"
    elif icp_type == "datacenter":
        subject = f"PlotLot — site scoring for {company}'s data center origination"
    elif icp_type == "press":
        subject = f"PlotLot — instant land analysis for {market} CRE coverage"
    elif icp_type == "investor":
        subject = f"PlotLot — multifamily/infill land analysis for {company}"
    else:
        subject = f"PlotLot — AI land analysis for {icp_type}s in {p.market}"

    # Ensure under 60 characters
    if len(subject) > 60:
        subject = f"PlotLot — AI land analysis for {icp_type}s"
        if len(subject) > 60:
            subject = "PlotLot — Instant land analysis"

    logger.info("email_subject_written", prospect=p.name, subject=subject)
    return subject.strip('"')
