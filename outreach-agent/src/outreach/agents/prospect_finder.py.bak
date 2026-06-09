from __future__ import annotations

import json
import re

import anthropic
import structlog

from outreach.config import settings
from outreach.core.types import ICPType, Prospect, ProspectStatus
from outreach.tools.web_search import search_prospects

logger = structlog.get_logger(__name__)

_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

# Search targets mapped to ICP type
SEARCH_TARGETS: list[dict] = [
    {
        "icp_type": ICPType.RESIDENTIAL,
        "titles": ["VP Land Acquisition", "Director Land Acquisition", "Land Acquisition Manager",
                   "Division President", "Land Entitlements"],
        "markets": ["Bay Area", "Sacramento", "NorCal", "Northern California"],
        "company_types": ["Homebuilder", "D.R. Horton", "Lennar", "KB Home", "Meritage",
                          "Taylor Morrison", "Tri Pointe", "private equity real estate"],
    },
    {
        "icp_type": ICPType.RESIDENTIAL,
        "titles": ["Land Acquisition", "Land Development", "Entitlements Manager", "Division President"],
        "markets": ["Bay Area", "Sacramento", "NorCal"],
        "company_types": ["Taylor Morrison", "Meritage Homes", "Tri Pointe Homes",
                          "William Lyon", "Shea Homes", "CalAtlantic"],
    },
    {
        "icp_type": ICPType.DATACENTER,
        "titles": ["Site Acquisition", "Site Selection", "Land Acquisition", "Real Estate",
                   "Infrastructure Development"],
        "markets": ["California", "Western US", "Bay Area"],
        "company_types": ["data center", "energy consulting", "utility-scale solar",
                          "BESS", "infrastructure development"],
    },
    {
        "icp_type": ICPType.INVESTOR,
        "titles": ["Principal", "Managing Partner", "Acquisitions", "Investment Manager"],
        "markets": ["Bay Area", "Sacramento", "NorCal"],
        "company_types": ["multifamily", "infill developer", "real estate investment"],
    },
    {
        "icp_type": ICPType.PRESS,
        "titles": ["reporter", "journalist", "editor", "correspondent"],
        "markets": ["Bay Area", "California", "NorCal"],
        "company_types": ["Bisnow", "The Real Deal", "San Francisco Business Times",
                          "Sacramento Business Journal", "GlobeSt"],
    },
]

PARSE_SYSTEM = """You parse LinkedIn search result snippets and extract structured prospect data.
Return a JSON array. Each element must have:
{
  "name": "Full Name",
  "first_name": "First",
  "last_name": "Last",
  "title": "Job Title",
  "company": "Company Name",
  "market": "Geographic market",
  "linkedin_url": "https://linkedin.com/in/...",
  "notes": "Any relevant context from the snippet"
}
If a field cannot be determined, use null. Return ONLY valid JSON — no explanation, no markdown.
"""


async def _parse_search_results(
    raw_results: list[dict], icp_type: ICPType, market: str
) -> list[Prospect]:
    """Use Claude to parse raw web search results into structured Prospect objects."""
    if not raw_results:
        return []

    content = json.dumps(raw_results, indent=2)
    response = _client.messages.create(
        model=settings.anthropic_model,
        max_tokens=2000,
        system=PARSE_SYSTEM,
        messages=[{"role": "user", "content": f"Parse these search results:\n\n{content}"}],
    )

    try:
        text = response.content[0].text.strip()
        # Strip markdown code fences if present
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        parsed = json.loads(text)
    except (json.JSONDecodeError, IndexError) as exc:
        logger.error("prospect_parse_failed", error=str(exc))
        return []

    prospects = []
    for item in parsed:
        if not item.get("name") or not item.get("linkedin_url"):
            continue
        try:
            prospects.append(Prospect(
                name=item["name"],
                first_name=item.get("first_name") or item["name"].split()[0],
                last_name=item.get("last_name") or item["name"].split()[-1],
                title=item.get("title") or "Unknown",
                company=item.get("company") or "Unknown",
                market=item.get("market") or market,
                icp_type=icp_type,
                linkedin_url=item.get("linkedin_url"),
                notes=item.get("notes"),
                source="web_search",
                status=ProspectStatus.QUEUED,
            ))
        except Exception as exc:
            logger.warning("prospect_build_failed", item=item, error=str(exc))

    return prospects


async def find_prospects(
    icp_types: list[ICPType] | None = None,
    max_per_target: int = 5,
) -> list[Prospect]:
    """
    Discover new prospects via web search + Claude parsing.
    Returns deduplicated list of Prospect objects ready to be saved to DB.
    """
    targets = SEARCH_TARGETS
    if icp_types:
        targets = [t for t in SEARCH_TARGETS if t["icp_type"] in icp_types]

    all_prospects: list[Prospect] = []
    seen_urls: set[str] = set()

    for target in targets:
        icp_type = target["icp_type"]
        for market in target["markets"]:
            raw = await search_prospects(
                title_keywords=target["titles"][:3],
                market=market,
                company_types=target.get("company_types"),
            )
            parsed = await _parse_search_results(raw[:max_per_target], icp_type, market)
            for p in parsed:
                url = p.linkedin_url or ""
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_prospects.append(p)

    logger.info("prospects_found", count=len(all_prospects))
    return all_prospects
