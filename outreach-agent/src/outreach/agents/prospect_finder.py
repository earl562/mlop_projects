from __future__ import annotations

import json
import re
import urllib.parse
from datetime import datetime

import structlog

from outreach.core.types import ICPType, Prospect, ProspectStatus
from outreach.tools.web_search import search_prospects

logger = structlog.get_logger(__name__)

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
        "icp_type": ICPType.RESIDENTIAL,
        "titles": ["VP Land Acquisition", "Director Land Acquisition", "Land Acquisition Manager",
                   "Division President", "Land Entitlements"],
        "markets": ["South Florida", "Miami", "Fort Lauderdale", "Palm Beach"],
        "company_types": ["Homebuilder", "D.R. Horton", "Lennar", "KB Home",
                          "Taylor Morrison", "Meritage Homes", "CC Homes",
                          "GL Homes", "Minto Communities", "Kolter Homes"],
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


def _parse_search_result_item(item: dict, icp_type: ICPType, market: str) -> Prospect | None:
    """Parse a single search result item into a Prospect object."""
    try:
        # Extract basic info from the search result
        title = item.get("title", "")
        snippet = item.get("snippet", "")
        url = item.get("url", "")
        
        # Try to extract name, title, company from title/snippet
        name = ""
        job_title = ""
        company = ""
        
        # Common patterns in LinkedIn search results
        # Pattern: "Name | Title at Company" or "Name - Title - Company"
        if " | " in title:
            parts = title.split(" | ")
            if len(parts) >= 2:
                name = parts[0].strip()
                rest = " | ".join(parts[1:]) if len(parts) > 2 else parts[1]
                if " at " in rest:
                    title_part, company_part = rest.split(" at ", 1)
                    job_title = title_part.strip()
                    company = company_part.strip()
                elif " - " in rest:
                    title_part, company_part = rest.split(" - ", 1)
                    job_title = title_part.strip()
                    company = company_part.strip()
                else:
                    job_title = rest.strip()
        elif " - " in title:
            parts = title.split(" - ")
            if len(parts) >= 3:
                name = parts[0].strip()
                job_title = parts[1].strip()
                company = " - ".join(parts[2:]).strip()
            elif len(parts) == 2:
                name = parts[0].strip()
                job_title = parts[1].strip()
        
        # If we couldn't parse structured data, use fallback
        if not name:
            # Extract name from beginning of title (before first separator)
            separators = [" | ", " - ", ":"]
            for sep in separators:
                if sep in title:
                    name = title.split(sep)[0].strip()
                    break
            if not name:
                name = title.split()[0] if title.split() else "Unknown"
        
        if not job_title:
            job_title = "Unknown"
        if not company:
            company = "Unknown"
            
        # Extract first and last name
        name_parts = name.split()
        first_name = name_parts[0] if name_parts else ""
        last_name = name_parts[-1]                            if len(name_parts) > 1 else ""
        
        # Determine geographic market from snippet or title
        detected_market = market  # default
        market_indicators = ["bay area", "sacramento", "norcal", "northern california", 
                           "san francisco", "silicon valley", "california",
                           "south florida", "miami", "fort lauderdale",
                           "palm beach", "broward", "miami-dade"]
        text_to_search = (title + " " + snippet).lower()
        for indicator in market_indicators:
            if indicator in text_to_search:
                detected_market = indicator.title()
                break
        
        # Create prospect
        prospect = Prospect(
            name=name or "Unknown",
            first_name=first_name,
            last_name=last_name,
            title=job_title or "Unknown",
            company=company or "Unknown",
            market=detected_market,
            icp_type=icp_type,
            linkedin_url=url if "linkedin.com" in url else None,
            notes=snippet[:200] if snippet else None,
            source="web_search",
            status=ProspectStatus.QUEUED,
        )
        
        return prospect
        
    except Exception as exc:
        logger.warning("prospect_parse_failed", item=item, error=str(exc))
        return None


async def find_prospects(
    icp_types: list[ICPType] | None = None,
    max_per_target: int = 5,
) -> list[Prospect]:
    """
    Discover new prospects via web search + template-based parsing.
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
            logger.info("searching_for_prospects", 
                       icp_type=icp_type.value, 
                       market=market,
                       titles=target["titles"][:3])
            
            raw = await search_prospects(
                title_keywords=target["titles"][:3],
                market=market,
                company_types=target.get("company_types"),
            )
            
            # Limit results to process
            results_to_process = raw[:max_per_target] if raw else []
            
            for item in results_to_process:
                prospect = _parse_search_result_item(item, icp_type, market)
                if prospect and prospect.linkedin_url:
                    url = prospect.linkedin_url
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_prospects.append(prospect)
                elif prospect:
                    # Prospect without LinkedIn URL - still valuable
                    all_prospects.append(prospect)

    logger.info("prospects_found", count=len(all_prospects))
    return all_prospects
