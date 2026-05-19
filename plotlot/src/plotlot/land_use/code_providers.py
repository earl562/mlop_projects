"""Discover county ordinance/code providers beyond the Municode zoning scanner."""

from __future__ import annotations

import asyncio
import html
import re
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

import httpx

OPEN_LEGAL_CODES_API = "https://openlegalcodes.org/api/v1"
DUCKDUCKGO_HTML_URL = "https://html.duckduckgo.com/html/"
WEB_SEARCH_TIMEOUT = httpx.Timeout(12.0, connect=5.0, read=12.0, write=5.0, pool=5.0)
BLOCKED_DISCOVERY_DOMAINS = {
    "adufloridainfo.com",
    "allpermitsearch.org",
    "countyoffice.org",
    "courts.ca.gov",
    "edit.zoningatlas.org",
    "inspectapedia.com",
    "ncdot.gov",
    "pubrecord.org",
    "newsbreak.com",
    "41nbc.com",
    "zoningpoint.com",
    "zoningatlas.org",
    "zoneomics.com",
    "images1.showcase.com",
    "kingsridgecofc.org",
}
US_STATE_NAMES = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
}


@dataclass(frozen=True)
class CodeAuthority:
    """A discovered ordinance/code authority source."""

    county: str
    state: str
    name: str
    authority_type: str
    platform: str
    publisher: str
    source_url: str
    status: str
    jurisdiction_id: str | None = None
    discovery_source: str = "unknown"
    confidence: str = "low"
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_label(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _state_name(state: str) -> str:
    return US_STATE_NAMES.get(state.upper(), state.upper())


def _county_exact_tokens(county: str) -> set[str]:
    base = normalize_label(county)
    return {
        f"{base} county",
        f"county of {base}",
        f"{base} co",
        base if base == "san francisco" else f"{base} county",
    }


def _compact_label(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _is_exact_county_authority(name: str, county: str) -> bool:
    normalized = normalize_label(name)
    if normalize_label(county) == "san francisco":
        return normalized in {
            "san francisco ca",
            "san francisco county ca",
            "city and county of san francisco",
            "city and county of san francisco ca",
        }
    return any(token in normalized for token in _county_exact_tokens(county))


def platform_from_url(url: str, publisher: str | None = None) -> str:
    text = f"{publisher or ''} {url}".lower()
    if "municode" in text:
        return "municode"
    if "ecode360" in text or "generalcode" in text:
        return "ecode360"
    if "amlegal" in text:
        return "amlegal"
    if "codepublishing" in text:
        return "codepublishing"
    if "municipalcodeonline" in text:
        return "municipal_code_online"
    if "encodeplus" in text:
        return "encodeplus"
    if "elaws.us" in text:
        return "elaws"
    if urlparse(url).netloc.endswith(".gov"):
        return "official_county_site"
    return publisher or "unknown"


def _display_platform(platform: str) -> str:
    labels = {
        "municode": "Municode",
        "ecode360": "eCode360 / General Code",
        "amlegal": "American Legal Publishing",
        "codepublishing": "Code Publishing",
        "municipal_code_online": "Municipal Code Online",
        "encodeplus": "enCodePlus",
        "elaws": "eLaws",
        "official_county_site": "Official county site",
        "ca-leginfo": "California Legislative Information",
    }
    return labels.get(platform, platform)


async def _openlegalcodes_jurisdictions(state: str) -> list[dict[str, Any]]:
    payload: dict[str, Any] = {}
    async with httpx.AsyncClient(timeout=45.0) as client:
        for attempt in range(3):
            response = await client.get(
                f"{OPEN_LEGAL_CODES_API}/jurisdictions",
                params={"state": state.upper(), "limit": 1000},
            )
            if response.status_code < 500 or attempt == 2:
                response.raise_for_status()
                payload = response.json()
                break
    data = payload.get("data") if isinstance(payload, dict) else []
    return data if isinstance(data, list) else []


async def discover_openlegalcodes_authorities(
    *,
    county: str,
    state: str,
) -> list[CodeAuthority]:
    """Discover exact county code sources from Open Legal Codes metadata."""

    authorities: list[CodeAuthority] = []
    for item in await _openlegalcodes_jurisdictions(state):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        authority_type = str(item.get("type") or "")
        if authority_type != "county" and not _is_exact_county_authority(name, county):
            continue
        if not _is_exact_county_authority(name, county):
            continue

        source_url = str(item.get("sourceUrl") or "")
        publisher = str(item.get("publisher") or "")
        platform = platform_from_url(source_url, publisher)
        if platform == "ca-leginfo":
            continue
        authorities.append(
            CodeAuthority(
                county=county,
                state=state.upper(),
                name=name,
                authority_type=authority_type or "county",
                platform=platform,
                publisher=_display_platform(platform),
                source_url=source_url,
                status=str(item.get("status") or "available"),
                jurisdiction_id=str(item.get("id") or "") or None,
                discovery_source="openlegalcodes",
                confidence="high",
            )
        )

    return authorities


def _decode_duckduckgo_url(raw_url: str) -> str:
    raw = html.unescape(raw_url)
    if raw.startswith("//"):
        raw = f"https:{raw}"
    parsed = urlparse(raw)
    uddg = parse_qs(parsed.query).get("uddg")
    if uddg:
        return unquote(uddg[0])
    return raw


def _strip_tags(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value)
    return html.unescape(value).strip()


def _is_probable_official_county_site(
    url: str,
    title: str,
    county: str,
    state: str,
) -> bool:
    parsed = urlparse(url)
    netloc = parsed.netloc.lower().removeprefix("www.")
    if not any(suffix in netloc for suffix in (".gov", ".us", ".org", ".net")):
        return False
    haystack = normalize_label(f"{netloc} {parsed.path} {title}")
    compact_haystack = _compact_label(f"{netloc} {parsed.path} {title}")
    if _compact_label(county) not in compact_haystack:
        return False
    county_label = normalize_label(county)
    for state_code, state_name in US_STATE_NAMES.items():
        if state_code == state.upper():
            continue
        normalized_state_name = normalize_label(state_name)
        if normalized_state_name == county_label:
            continue
        if normalized_state_name in haystack:
            return False
    state_token = state.lower()
    return (
        "county" in haystack
        or state_token in set(haystack.split())
        or _state_name(state).lower() in haystack
    )


def _mentions_county(url: str, title: str, county: str) -> bool:
    haystack = normalize_label(f"{url} {title}")
    compact_haystack = _compact_label(f"{url} {title}")
    return normalize_label(county) in haystack or _compact_label(county) in compact_haystack


def _candidate_platform(url: str, title: str, county: str, state: str) -> str:
    platform = platform_from_url(url)
    if platform == "unknown" and _is_probable_official_county_site(url, title, county, state):
        return "official_county_site"
    return platform


def _result_relevance(
    url: str,
    title: str,
    county: str,
    state: str,
    *,
    platform: str | None = None,
) -> int:
    haystack = normalize_label(f"{url} {title}")
    haystack_tokens = set(haystack.split())
    county_base = normalize_label(county)
    score = 0
    if county_base in haystack:
        score += 3
    if "county" in haystack:
        score += 2
    if state.lower() in haystack_tokens or _state_name(state).lower() in haystack:
        score += 1
    if any(term in haystack for term in ("code", "ordinance", "zoning", "development")):
        score += 2
    platform = platform or platform_from_url(url)
    if platform != "unknown":
        score += 5
    if urlparse(url).netloc.endswith(".gov"):
        score += 1
    return score


def _is_source_candidate(url: str, title: str, county: str, state: str) -> bool:
    netloc = urlparse(url).netloc.lower().removeprefix("www.")
    if any(netloc == blocked or netloc.endswith(f".{blocked}") for blocked in BLOCKED_DISCOVERY_DOMAINS):
        return False
    haystack = normalize_label(f"{url} {title}")
    if normalize_label(county) == "san francisco" and "south san francisco" in haystack:
        return False
    platform = _candidate_platform(url, title, county, state)
    if platform == "elaws" and _compact_label(county) not in _compact_label(
        urlparse(url).netloc
    ):
        return False
    if platform != "unknown" and not _mentions_county(url, title, county):
        return False
    if platform == "official_county_site" and not _is_probable_official_county_site(
        url,
        title,
        county,
        state,
    ):
        return False
    if platform in {
        "municode",
        "ecode360",
        "amlegal",
        "codepublishing",
        "municipal_code_online",
        "encodeplus",
        "elaws",
        "official_county_site",
    }:
        return _result_relevance(url, title, county, state, platform=platform) >= 4
    return False


def _platform_priority(platform: str) -> int:
    priorities = {
        "municode": 90,
        "ecode360": 80,
        "amlegal": 80,
        "codepublishing": 80,
        "municipal_code_online": 80,
        "encodeplus": 75,
        "elaws": 75,
        "official_county_site": 20,
        "unknown": 0,
    }
    return priorities.get(platform, 10)


def _parse_duckduckgo_html(text: str) -> list[tuple[str, str]]:
    pattern = re.compile(
        r'class="result__a"\s+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
        flags=re.IGNORECASE | re.DOTALL,
    )
    return [
        (_decode_duckduckgo_url(match.group("href")), _strip_tags(match.group("title")))
        for match in pattern.finditer(text)
    ]


def _parse_duckduckgo_markdown(text: str) -> list[tuple[str, str]]:
    pattern = re.compile(r"^## \[(?P<title>[^\]]+)\]\((?P<href>[^)]+)\)", flags=re.MULTILINE)
    return [
        (_decode_duckduckgo_url(match.group("href")), _strip_tags(match.group("title")))
        for match in pattern.finditer(text)
    ]


async def _direct_platform_results(
    client: httpx.AsyncClient,
    *,
    county: str,
    state: str,
) -> list[tuple[str, str]]:
    county_slug = _compact_label(county)
    direct_urls = [
        (
            f"https://{county_slug}.municipalcodeonline.com/",
            f"Municipal Code Online - {county} County",
        ),
        (
            f"http://{county_slug}county-{state.lower()}.elaws.us/bookview/coor",
            f"{county} County, {state.upper()} Code of Ordinances - eLaws",
        ),
        (
            f"http://{county_slug}co-{state.lower()}.elaws.us/code/coor",
            f"{county} County, {state.upper()} Code of Ordinances - eLaws",
        ),
    ]
    results: list[tuple[str, str]] = []
    for url, title in direct_urls:
        try:
            response = await client.get(url)
        except httpx.HTTPError:
            continue
        final_url = str(response.url)
        if response.status_code >= 400:
            continue
        if platform_from_url(url) != platform_from_url(final_url):
            continue
        results.append((final_url, title))
    return results


async def discover_web_code_sources(
    *,
    county: str,
    state: str,
    limit: int = 5,
) -> list[CodeAuthority]:
    """Discover likely official/platform code sources with DuckDuckGo HTML."""

    queries = [
        f'"{county} County" "{state.upper()}" code of ordinances zoning',
        f'"{county} County" "{_state_name(state)}" code of ordinances zoning',
        f'"{county} County" "Municipal Code Online"',
        f'"{county} County" "zoning ordinance"',
        f'site:ecode360.com "{county} County" "{state.upper()}"',
        f'site:codelibrary.amlegal.com "{county} County" "{state.upper()}"',
        f'site:codepublishing.com "{county} County" "{state.upper()}"',
        f'site:online.encodeplus.com "{county} County"',
        f'site:elaws.us "{county} County"',
        f'site:library.municode.com "{county} County" "{state.upper()}"',
    ]
    headers = {"User-Agent": "Mozilla/5.0"}
    candidates: list[tuple[int, int, CodeAuthority]] = []
    seen: set[str] = set()
    async with httpx.AsyncClient(
        timeout=WEB_SEARCH_TIMEOUT,
        follow_redirects=True,
        headers=headers,
    ) as client:
        def add_candidate(
            url: str,
            title: str,
            *,
            discovery_source: str = "duckduckgo_html",
        ) -> None:
            if not url or url in seen:
                return
            seen.add(url)
            if not _is_source_candidate(url, title, county, state):
                return
            platform = _candidate_platform(url, title, county, state)
            candidates.append(
                (
                    _platform_priority(platform),
                    _result_relevance(url, title, county, state, platform=platform),
                    CodeAuthority(
                        county=county,
                        state=state.upper(),
                        name=title or f"{county} County code source",
                        authority_type="county",
                        platform=platform,
                        publisher=_display_platform(platform),
                        source_url=url,
                        status="candidate",
                        discovery_source=discovery_source,
                        confidence="medium" if platform != "official_county_site" else "low",
                    ),
                )
            )

        for url, title in await _direct_platform_results(client, county=county, state=state):
            add_candidate(url, title, discovery_source="direct_platform_probe")

        for query in queries:
            jina_url = f"https://r.jina.ai/http://html.duckduckgo.com/html/?q={quote(query)}"
            response: httpx.Response | None = None
            for attempt in range(2):
                try:
                    response = await client.get(jina_url)
                except httpx.HTTPError:
                    if attempt == 0:
                        await asyncio.sleep(0.25)
                    continue
                if response.status_code in {429, 500, 502, 503, 504} and attempt == 0:
                    await asyncio.sleep(0.25)
                    continue
                break
            if response is None:
                continue
            if response.status_code >= 400:
                continue

            parsed_results = _parse_duckduckgo_html(response.text) or _parse_duckduckgo_markdown(
                response.text
            )
            for url, title in parsed_results:
                add_candidate(url, title)
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [authority for _, _, authority in candidates[:limit]]


def _dedupe_authorities(authorities: list[CodeAuthority]) -> list[CodeAuthority]:
    deduped: dict[str, CodeAuthority] = {}
    for authority in authorities:
        key = authority.source_url.rstrip("/")
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = authority
            continue
        if existing.confidence != "high" and authority.confidence == "high":
            deduped[key] = authority
    return list(deduped.values())


async def discover_code_authorities(
    *,
    county: str,
    state: str,
    include_web_fallback: bool = True,
) -> list[CodeAuthority]:
    """Discover code/ordinance providers for a county across known platforms."""

    authorities = await discover_openlegalcodes_authorities(county=county, state=state)
    if include_web_fallback:
        try:
            authorities.extend(await discover_web_code_sources(county=county, state=state))
        except Exception:
            if authorities:
                return _dedupe_authorities(authorities)
            raise
    return _dedupe_authorities(authorities)


async def search_openlegalcodes(
    *,
    jurisdiction_id: str,
    query: str,
    limit: int = 5,
) -> dict[str, Any]:
    """Search a legal-code jurisdiction through Open Legal Codes."""

    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.get(
            f"{OPEN_LEGAL_CODES_API}/jurisdictions/{jurisdiction_id}/search",
            params={"q": query},
        )

    if response.status_code in {202, 503}:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        return {
            "status": "pending_or_unavailable",
            "results": [],
            "message": payload.get("message") or response.text[:300],
            "retry_after": payload.get("retryAfter"),
        }

    if response.status_code == 404:
        return {
            "status": "not_found",
            "results": [],
            "message": f"Jurisdiction {jurisdiction_id!r} was not found",
        }

    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") if isinstance(payload, dict) else payload
    results = data.get("results") if isinstance(data, dict) else data
    if not isinstance(results, list):
        results = []

    return {"status": "success", "results": results[:limit], "message": None}
