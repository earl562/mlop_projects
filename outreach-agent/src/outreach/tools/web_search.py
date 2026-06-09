from __future__ import annotations

import httpx
import structlog

from outreach.config import settings

logger = structlog.get_logger(__name__)

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


async def web_search(query: str, max_results: int = 10) -> list[dict]:
    """
    Search the web via Tavily API.
    Free tier: 1,000 searches/month.
    Returns a list of {title, url, snippet} dicts.
    """
    if not settings.tavily_api_key:
        logger.warning("tavily_api_key_missing — set TAVILY_API_KEY in .env")
        return []

    payload = {
        "api_key": settings.tavily_api_key,
        "query": query,
        "search_depth": "basic",
        "include_answer": False,
        "include_images": False,
        "include_raw_content": False,
        "max_results": min(max_results, 20),
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                TAVILY_SEARCH_URL,
                headers={"Content-Type": "application/json"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "tavily_search_http_error",
                status=exc.response.status_code,
                query=query,
            )
            return []
        except Exception as exc:
            logger.error("tavily_search_failed", query=query, error=str(exc))
            return []

    results = []
    for item in data.get("results", []):
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("content", ""),
        })

    logger.info("web_search_done", query=query, results=len(results))
    return results[:max_results]


async def search_prospects(
    title_keywords: list[str],
    market: str,
    company_types: list[str] | None = None,
) -> list[dict]:
    """Compose and run targeted LinkedIn prospect searches via Tavily Search."""
    results = []
    for title in title_keywords:
        query = f'site:linkedin.com/in "{title}" "{market}"'
        if company_types:
            query += f' ({" OR ".join(company_types[:4])})'
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
