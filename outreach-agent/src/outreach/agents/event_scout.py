from __future__ import annotations

from datetime import datetime

import structlog

from outreach.core.types import Event, EventStatus
from outreach.tools.eventbrite import discover_events

logger = structlog.get_logger(__name__)


async def scout_events() -> list[Event]:
    """
    Discover upcoming networking events relevant to PlotLot outreach.
    Uses template-based scoring and returns Event objects ready to be saved to DB.
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

        # Calculate relevance score based on keywords
        relevance_score = _calculate_relevance_score(ev)
        
        events.append(Event(
            name=ev["name"],
            organizer=ev.get("organizer", "Unknown"),
            date=date,
            location=ev.get("location", ""),
            url=ev.get("url"),
            description=ev.get("description"),
            relevance_score=relevance_score,
            status=EventStatus.DISCOVERED,
        ))

    # Sort by relevance score (highest first)
    events.sort(key=lambda e: e.relevance_score, reverse=True)
    
    logger.info("events_scouted", count=len(events))
    return events


def _calculate_relevance_score(event: dict) -> float:
    """
    Calculate relevance score for an event based on keywords.
    Returns a score between 0.0 and 1.0.
    """
    # Combine text fields to search
    text_fields = [
        event.get("name", ""),
        event.get("description", ""),
        event.get("organizer", ""),
        event.get("location", "")
    ]
    text_to_search = " ".join(text_fields).lower()
    
    # Keywords that indicate high relevance for PlotLot's target audience
    high_value_keywords = [
        "uli", "urban land institute",
        "bia", "building industry association", 
        "naiop", "commercial real estate development association",
        "land acquisition",
        "land development",
        "real estate",
        "multifamily",
        "infill",
        "data center",
        "infrastructure",
        "site selection",
        "site acquisition",
        "zoning",
        "entitlements",
        "homebuilder",
        "developer",
        "investor",
        "cre", "commercial real estate"
    ]
    
    # Medium value keywords
    medium_value_keywords = [
        "networking",
        "conference",
        "summit",
        "forum",
        "meetup",
        "mixer",
        "panel",
        "workshop",
        "seminar",
        "expo",
        "convention"
    ]
    
    # Calculate score
    score = 0.0
    max_possible_score = 0.0
    
    # Check for high value keywords (worth 0.2 each, up to 1.0)
    for keyword in high_value_keywords:
        if keyword in text_to_search:
            score += 0.2
        max_possible_score += 0.2
    
    # Check for medium value keywords (worth 0.1 each, up to 0.3)
    medium_matches = 0
    for keyword in medium_value_keywords:
        if keyword in text_to_search:
            medium_matches += 1
    score += min(medium_matches * 0.1, 0.3)
    max_possible_score += 0.3
    
    # Normalize score to 0.0-1.0 range
    if max_possible_score > 0:
        normalized_score = min(score / max_possible_score, 1.0)
    else:
        normalized_score = 0.0
    
    # Ensure minimum score for any event (so we don't miss potential opportunities)
    final_score = max(normalized_score, 0.1)
    
    return min(final_score, 1.0)
