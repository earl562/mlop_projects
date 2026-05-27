from __future__ import annotations

import httpx
import structlog

from outreach.config import settings

logger = structlog.get_logger(__name__)

BASE_URL = "https://api.hunter.io/v2"


async def find_email(first_name: str, last_name: str, domain: str) -> dict | None:
    """
    Find a work email via Hunter.io Email Finder.
    Free tier: 25 searches/month.
    Returns {email, score, sources} or None if not found.
    """
    if not settings.hunter_api_key:
        logger.warning("hunter_api_key_missing")
        return None

    params = {
        "first_name": first_name,
        "last_name": last_name,
        "domain": domain,
        "api_key": settings.hunter_api_key,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(f"{BASE_URL}/email-finder", params=params)
            resp.raise_for_status()
            data = resp.json().get("data", {})
        except httpx.HTTPStatusError as exc:
            logger.error("hunter_http_error", status=exc.response.status_code, domain=domain)
            return None
        except Exception as exc:
            logger.error("hunter_error", error=str(exc))
            return None

    email = data.get("email")
    if not email:
        logger.info("hunter_not_found", first=first_name, last=last_name, domain=domain)
        return None

    result = {
        "email": email,
        "score": data.get("score", 0),
        "sources": [s.get("uri") for s in data.get("sources", [])],
    }
    logger.info("hunter_found", email=email, score=result["score"])
    return result


async def verify_email(email: str) -> dict:
    """
    Verify an email address via Hunter.io Email Verifier.
    Returns {result, score, regexp, gibberish, disposable, webmail, mx_records, smtp_server, smtp_check}.
    """
    if not settings.hunter_api_key:
        return {"result": "unknown", "score": 0}

    params = {"email": email, "api_key": settings.hunter_api_key}
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(f"{BASE_URL}/email-verifier", params=params)
            resp.raise_for_status()
            return resp.json().get("data", {})
        except Exception as exc:
            logger.error("hunter_verify_error", email=email, error=str(exc))
            return {"result": "unknown", "score": 0}


def domain_from_company(company: str) -> str | None:
    """
    Derive a likely domain from a known company name.
    Covers the main homebuilders and firms in PlotLot's ICP.
    """
    known = {
        # Homebuilders
        "d.r. horton": "drhorton.com",
        "dr horton": "drhorton.com",
        "lennar": "lennar.com",
        "kb home": "kbhome.com",
        "pulte": "pultegroup.com",
        "pultegroup": "pultegroup.com",
        "meritage": "meritagehomes.com",
        "meritage homes": "meritagehomes.com",
        "taylor morrison": "taylormorrison.com",
        "tri pointe": "tripointehomes.com",
        "tri pointe homes": "tripointehomes.com",
        "william lyon": "lyonhomes.com",
        "shea homes": "sheahomes.com",
        "calathlantic": "calatlantichomes.com",
        # CRE brokers
        "cbre": "cbre.com",
        "jll": "jll.com",
        "colliers": "colliers.com",
        "cushman & wakefield": "cushmanwakefield.com",
        "cushman and wakefield": "cushmanwakefield.com",
        "newmark": "nmrk.com",
        "marcus & millichap": "marcusmillichap.com",
        "kidder mathews": "kiddermathews.com",
        # Press / media
        "bisnow": "bisnow.com",
        "the real deal": "therealdeal.com",
        "san francisco business times": "bizjournals.com",
        "sacramento business journal": "bizjournals.com",
        "globest": "globest.com",
        "the san francisco standard": "sfstandard.com",
        "bay area reporter": "ebar.com",
        "nbc bay area": "nbcbayarea.com",
        "los angeles times": "latimes.com",
        "bloomberg news": "bloomberg.net",
        "bloomberg": "bloomberg.net",
        # Investors / developers
        "valley oak partners": "valleyoakpartners.com",
        "kenji capital": "kenjicapital.com",
        "tierra energy": "tierraenergy.com",
        "manulife investment management": "manulife.com",
        "kilroy realty": "kilroyrealty.com",
        "kilroy realty corporation": "kilroyrealty.com",
        "cohen ventures co.": "cohenventures.com",
        "cohen ventures": "cohenventures.com",
        "jakob ventures": "jakobventures.com",
        "c3 development group": "c3devgroup.com",
        "massimino development": "massiminodevelopment.com",
        "massimino impact housing": "massiminodevelopment.com",
        "norcal realty": "norcalrealty.com",
        "saliman investments": "salimaninvestments.com",
    }
    key = company.lower().strip()
    # exact match first
    if key in known:
        return known[key]
    # partial match fallback
    for k, v in known.items():
        if k in key or key in k:
            return v
    return None
