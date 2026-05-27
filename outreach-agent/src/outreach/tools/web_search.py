from __future__ import annotations

import httpx
import structlog

from outreach.config import settings

logger = structlog.get_logger(__name__)

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


async def web_search(query: str, max_results: int = 10) -> list[dict]:
    """
    Search the web via Brave Search API.
    Free tier: 2,000 queries/month. Supports site:, "exact match", and all standard operators.
    Returns a list of {title, url, snippet} dicts.
    """
    if not settings.brave_api_key:
        logger.warning("brave_api_key_missing — set BRAVE_API_KEY in .env")
        return []

    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": settings.brave_api_key,
    }
    params = {"q": query, "count": min(max_results, 20), "search_lang": "en", "country": "us"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(BRAVE_SEARCH_URL, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            logger.error("brave_search_http_error", status=exc.response.status_code, query=query)
            return []
        except Exception as exc:
            logger.error("brave_search_failed", query=query, error=str(exc))
            return []

    results = []
    for item in data.get("web", {}).get("results", []):
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("description", ""),
        })

    logger.info("web_search_done", query=query, results=len(results))
    return results[:max_results]


async def search_prospects(
    title_keywords: list[str],
    market: str,
    company_types: list[str] | None = None,
) -> list[dict]:
    """Compose and run targeted LinkedIn prospect searches via Brave Search."""
    results = []
    for title in title_keywords:
        query = f'site:linkedin.com/in "{title}" "{market}"'
        if company_types:
            query += f' ({" OR ".join(company_types[:4])})'  # Brave handles up to ~4 OR terms cleanly
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
