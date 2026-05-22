from __future__ import annotations

from datetime import datetime, timezone

import httpx
import structlog

from outreach.config import settings
from outreach.tools.web_search import search_events

logger = structlog.get_logger(__name__)

EVENTBRITE_BASE = "https://www.eventbriteapi.com/v3"

# Organizers and keywords that signal strong ICP relevance for PlotLot
HIGH_RELEVANCE_KEYWORDS = [
    "land acquisition", "zoning", "entitlements", "homebuilder",
    "real estate development", "ULI", "BIA", "NAIOP", "multifamily",
    "data center", "site selection", "infrastructure", "ground-up development",
]

SEARCH_KEYWORDS = [
    "ULI", "BIA Bay Area", "NAIOP", "land acquisition", "real estate development",
    "zoning entitlements", "homebuilder", "data center land", "site selection",
]

TARGET_LOCATIONS = ["Bay Area", "Sacramento", "San Francisco", "San Jose", "Silicon Valley"]


def _score_event(name: str, description: str) -> float:
    """Score an event 0-1 based on keyword relevance to PlotLot ICP."""
    text = f"{name} {description}".lower()
    hits = sum(1 for kw in HIGH_RELEVANCE_KEYWORDS if kw.lower() in text)
    return min(hits / 4.0, 1.0)


async def fetch_eventbrite_events(location: str, keywords: str) -> list[dict]:
    """Query Eventbrite API for upcoming events matching keywords and location."""
    if not settings.eventbrite_api_key:
        logger.warning("eventbrite_api_key_missing — falling back to web search")
        return []

    headers = {"Authorization": f"Bearer {settings.eventbrite_api_key}"}
    params = {
        "q": keywords,
        "location.address": location,
        "location.within": "50mi",
        "start_date.range_start": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sort_by": "date",
        "expand": "venue,organizer",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(f"{EVENTBRITE_BASE}/events/search/", headers=headers, params=params)
            resp.raise_for_status()
            return resp.json().get("events", [])
        except Exception as exc:
            logger.error("eventbrite_error", error=str(exc))
            return []


async def discover_events() -> list[dict]:
    """
    Discover upcoming in-person networking events relevant to PlotLot outreach.
    Combines Eventbrite API + web search fallback.
    Returns list of normalized event dicts.
    """
    normalized: list[dict] = []

    for location in TARGET_LOCATIONS:
        for kw in SEARCH_KEYWORDS[:3]:  # cap to avoid rate limits
            raw_events = await fetch_eventbrite_events(location, kw)
            for ev in raw_events:
                venue = ev.get("venue", {}) or {}
                organizer = ev.get("organizer", {}) or {}
                name = ev.get("name", {}).get("text", "")
                description = ev.get("description", {}).get("text", "") or ""
                score = _score_event(name, description)
                if score < 0.1:
                    continue
                normalized.append({
                    "name": name,
                    "organizer": organizer.get("name", "Unknown"),
                    "date": ev.get("start", {}).get("utc"),
                    "location": venue.get("address", {}).get("localized_address_display", location),
                    "url": ev.get("url"),
                    "description": description[:500],
                    "relevance_score": score,
                })

    # Web search fallback for events Eventbrite doesn't list (ULI, NAIOP chapter events)
    web_hits = await search_events(SEARCH_KEYWORDS, "Bay Area OR Sacramento")
    for hit in web_hits:
        score = _score_event(hit.get("title", ""), hit.get("snippet", ""))
        if score >= 0.1:
            normalized.append({
                "name": hit.get("title", ""),
                "organizer": "Unknown",
                "date": None,
                "location": "Bay Area / Sacramento",
                "url": hit.get("url"),
                "description": hit.get("snippet", "")[:500],
                "relevance_score": score,
            })

    # Deduplicate by URL
    seen: set[str] = set()
    unique = []
    for ev in sorted(normalized, key=lambda x: x["relevance_score"], reverse=True):
        url = ev.get("url") or ev.get("name", "")
        if url not in seen:
            seen.add(url)
            unique.append(ev)

    logger.info("events_discovered", count=len(unique))
    return unique
