from __future__ import annotations

import httpx
import structlog

logger = structlog.get_logger(__name__)

DDGS_URL = "https://api.duckduckgo.com/"


async def web_search(query: str, max_results: int = 10) -> list[dict]:
    """
    Search the web via DuckDuckGo Instant Answer API.
    Returns a list of {title, url, snippet} dicts.
    Free, no API key required.
    """
    params = {"q": query, "format": "json", "no_redirect": "1", "no_html": "1", "skip_disambig": "1"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(DDGS_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.error("web_search_failed", query=query, error=str(exc))
            return []

    results: list[dict] = []

    # Abstract (top answer)
    if data.get("Abstract"):
        results.append({
            "title": data.get("Heading", query),
            "url": data.get("AbstractURL", ""),
            "snippet": data["Abstract"],
        })

    # Related topics
    for topic in data.get("RelatedTopics", [])[:max_results]:
        if isinstance(topic, dict) and topic.get("Text"):
            results.append({
                "title": topic.get("Text", "")[:80],
                "url": topic.get("FirstURL", ""),
                "snippet": topic.get("Text", ""),
            })

    logger.info("web_search_done", query=query, results=len(results))
    return results[:max_results]


async def search_prospects(
    title_keywords: list[str],
    market: str,
    company_types: list[str] | None = None,
) -> list[dict]:
    """Compose and run targeted LinkedIn prospect searches via DuckDuckGo."""
    results = []
    for title in title_keywords:
        query = f'site:linkedin.com/in "{title}" "{market}"'
        if company_types:
            query += f' ({" OR ".join(company_types)})'
        hits = await web_search(query, max_results=5)
        results.extend(hits)
    return results


async def search_events(keywords: list[str], location: str, year: int = 2026) -> list[dict]:
    """Search for relevant real estate / land acquisition networking events."""
    results = []
    for kw in keywords:
        query = f'"{kw}" event {location} {year} networking land acquisition real estate'
        hits = await web_search(query, max_results=5)
        results.extend(hits)
    return results
