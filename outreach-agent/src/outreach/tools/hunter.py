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
        "d.r. horton": "drhorton.com",
        "dr horton": "drhorton.com",
        "lennar": "lennar.com",
        "kb home": "kbhome.com",
        "pulte": "pultegroup.com",
        "meritage": "meritagehomes.com",
        "taylor morrison": "taylormorrison.com",
        "tri pointe": "tripointehomes.com",
        "william lyon": "lyonhomes.com",
        "valley oak partners": "valleyoakpartners.com",
        "kenji capital": "kenjicapital.com",
        "tierra energy": "tierraenergy.com",
        "cbre": "cbre.com",
        "jll": "jll.com",
        "colliers": "colliers.com",
    }
    return known.get(company.lower().strip())
