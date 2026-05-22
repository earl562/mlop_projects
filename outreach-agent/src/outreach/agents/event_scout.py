from __future__ import annotations

from datetime import datetime

import anthropic
import structlog

from outreach.config import settings
from outreach.core.types import Event, EventStatus
from outreach.tools.eventbrite import discover_events

logger = structlog.get_logger(__name__)

_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)


async def scout_events() -> list[Event]:
    """
    Discover upcoming networking events relevant to PlotLot outreach.
    Ranks by relevance score and returns Event objects ready to be saved to DB.
    """
    raw = await discover_events()

    events = []
    for ev in raw:
        date = None
        if ev.get("date"):
            try:
                date = datetime.fromisoformat(ev["date"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        events.append(Event(
            name=ev["name"],
            organizer=ev.get("organizer", "Unknown"),
            date=date,
            location=ev.get("location", ""),
            url=ev.get("url"),
            description=ev.get("description"),
            relevance_score=ev.get("relevance_score", 0.0),
            status=EventStatus.DISCOVERED,
        ))

    # Ask Claude to rank and annotate the top events
    if events:
        events = await _rank_and_annotate(events)

    logger.info("events_scouted", count=len(events))
    return events


async def _rank_and_annotate(events: list[Event]) -> list[Event]:
    """Use Claude to add a pitch strategy note to the most relevant events."""
    top = sorted(events, key=lambda e: e.relevance_score, reverse=True)[:10]

    summaries = "\n".join(
        f"{i+1}. {e.name} — {e.organizer} — {e.location} — score: {e.relevance_score:.2f}"
        for i, e in enumerate(top)
    )

    response = _client.messages.create(
        model=settings.anthropic_model,
        max_tokens=800,
        messages=[{
            "role": "user",
            "content": f"""You're helping Earl Perry (founder of PlotLot — AI zoning tool for NorCal land acquisition)
decide which events to attend to pitch in person.

PlotLot targets: VP/Director Land Acquisition at homebuilders, land entitlements managers, energy/data center
site originators, multifamily investors. All in NorCal/Bay Area.

Rate each event and add a one-line pitch strategy. Format your response as:
1. [event name] — [why attend / who you'd meet / pitch angle]
2. ...

Events:
{summaries}
""",
        }],
    )

    annotation_text = response.content[0].text
    lines = [l.strip() for l in annotation_text.strip().split("\n") if l.strip()]

    for i, event in enumerate(top):
        if i < len(lines):
            event.description = (event.description or "") + f"\n[Strategy] {lines[i]}"

    return sorted(top, key=lambda e: e.relevance_score, reverse=True)
