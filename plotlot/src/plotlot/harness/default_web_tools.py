from __future__ import annotations

from typing import Any

from plotlot.land_use.models import ToolContext


async def handle_web_search(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    import httpx

    from plotlot.config import settings

    query = str(args.get("query", "") or "").strip()
    if not query:
        return {"status": "error", "results": [], "message": "query is required"}
    if not settings.jina_api_key:
        return {
            "status": "not_configured",
            "results": [],
            "message": "Web search connector is not configured (JINA_API_KEY not set)",
        }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"https://s.jina.ai/{query}",
                headers={
                    "Authorization": f"Bearer {settings.jina_api_key}",
                    "Accept": "application/json",
                    "X-Retain-Images": "none",
                },
            )
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        return {
            "status": "error",
            "results": [],
            "message": f"Web search failed: {type(exc).__name__}: {exc}",
        }

    results = [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "description": str(item.get("description", ""))[:300],
            "content": str(item.get("content", ""))[:500],
        }
        for item in data.get("data", [])[:5]
    ]
    return {"status": "success", "results": results}
