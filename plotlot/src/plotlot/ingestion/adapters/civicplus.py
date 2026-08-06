"""CivicPlus document-portal adapter for cities that self-host zoning PDFs.

Many California cities run their website on CivicPlus, which serves uploaded
documents from a stable, guessable path::

    /home/showpublisheddocument/{document_id}/{revision_ticks}

Unlike the codifier platforms (Municode, QCode, eCode360), there is no API and
no per-city client ID — but there is something better: the city's own zoning
page enumerates every article of the ordinance as a plain ``<a href>``.  So
discovery is a single fetch plus a regex, with no URL-grid probing of the kind
:func:`plotlot.ingestion.adapters.pdf.discover_san_diego_sources` needs.

The documents themselves are ordinary PDFs, so once discovered they feed the
existing :class:`~plotlot.ingestion.adapters.pdf.PDFAdapter` unchanged.

Adding a CivicPlus city = one :data:`CivicPlusSite` entry in
:data:`_CIVICPLUS_SITES` plus a registry line in
:mod:`plotlot.ingestion.adapters.registry`.  No new file required.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx

from plotlot.ingestion.adapters.pdf import PDFAdapter, PDFSource, _extract_zone_codes

logger = logging.getLogger(__name__)

# CivicPlus portals reject the default httpx agent on some deployments.
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PlotLot/1.0"

_FETCH_TIMEOUT_S = 45.0

# Matches the CivicPlus published-document path and its adjacent link text.
# The anchor may carry attributes (title=, target=, class=) before the text.
_DOC_LINK_RE = re.compile(
    r'href="(?P<href>(?:https?://[^"]+)?/home/showpublisheddocument/\d+/\d+)"'
    r"[^>]*>\s*(?P<label>[^<]{3,120})",
    re.IGNORECASE,
)

# "Article 10ː Residential Districts" / "Article 4A: Downtown Use Classifications"
# CivicPlus pages frequently use U+02D0 (MODIFIER LETTER TRIANGULAR COLON, "ː")
# rather than an ASCII colon, so both are accepted.
_ARTICLE_RE = re.compile(
    r"^(?P<kind>Article|Chapter|Division|Title|Part)\s+"
    r"(?P<num>\d{1,3})(?P<suffix>[A-Z]?)\s*[:ː\-–—]?\s*(?P<title>.*)$",
    re.IGNORECASE,
)

# Index entries that are navigation rather than ordinance text.
_SKIP_LABEL_RE = re.compile(
    r"^(table of contents|contents|index|cover|errata|summary of amendments)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CivicPlusSite:
    """A CivicPlus-hosted city and the page that indexes its zoning ordinance."""

    municipality: str
    county: str
    state: str
    index_url: str
    #: Human label for the ordinance as a whole, used as the chapter fallback.
    code_name: str = "Zoning Ordinance"
    #: District codes that carry no digit ("RM", "CS-HO") and so are invisible to
    #: the default San Diego-style extractor.  Empty tuple = default only.
    district_codes: tuple[str, ...] = ()


# ── Known CivicPlus zoning portals ───────────────────────────────────────────

# Oceanside's base and overlay districts, transcribed from the designator tables
# in Article 2 §B/§C (the ordinance's own authority, not inferred from prose).
#
# Both forms are listed deliberately: the zoning map and parcel records carry the
# density-suffixed designator ("RM-B"), while the ordinance text discusses the
# family in bare form ("the RS, RM, RH, and RT Districts"), and retrieval needs
# to match either.  Single-letter districts (A, D, H) are omitted — they collide
# with ordinary prose too often to work as retrieval metadata.
_OCEANSIDE_DISTRICTS: tuple[str, ...] = (
    # Residential — Articles 10 / 10C
    "RE",
    "RE-A",
    "RE-B",
    "RS",
    "R-1/CZ",
    "RM",
    "RM-A",
    "RM-B",
    "RM-C",
    "RH",
    "RH-U",
    "R-3/CZ",
    "RT",
    "R-T/CZ",
    # Commercial — Articles 11 / 11C
    "CN",
    "C-1",
    "CC",
    "CG",
    "C-2/CZ",
    "CL",
    "CR",
    "CV",
    "VC/CZ",
    "CS",
    "CS-HO",
    "CS-L",
    "CP",
    "OP/CZ",
    # Industrial — Articles 13 / 13C
    "IL",
    "M-1/CZ",
    "IG",
    "IP",
    # Open space, public, and special base districts — Articles 15-19
    "OS",
    "O/CZ",
    "PS",
    "PUT/CZ",
    "PD",
    "MR-P",
    "MHP",
    # Overlays — Articles 21-28
    "SP",
    "NC",
    "PBD",
    "IS",
    "MP",
    "EQ",
)

_CIVICPLUS_SITES: dict[str, CivicPlusSite] = {
    "oceanside_ca": CivicPlusSite(
        municipality="Oceanside",
        county="San Diego",
        state="CA",
        index_url=(
            "https://www.ci.oceanside.ca.us/government/development-services"
            "/planning/codes-regulations-maps/zoning-ordinance"
        ),
        code_name="Comprehensive Zoning Ordinance",
        district_codes=_OCEANSIDE_DISTRICTS,
    ),
}


def civicplus_site(municipality: str, state: str) -> CivicPlusSite | None:
    """Return the configured CivicPlus site for a municipality, if any."""
    return _CIVICPLUS_SITES.get(f"{municipality.strip().lower()}_{state.strip().lower()}")


def civicplus_municipalities() -> frozenset[str]:
    """Lowercased municipality names served by a CivicPlus adapter."""
    return frozenset(site.municipality.lower() for site in _CIVICPLUS_SITES.values())


# ── Discovery ────────────────────────────────────────────────────────────────


async def discover_civicplus_sources(
    index_url: str,
    *,
    code_name: str = "Zoning Ordinance",
    client: httpx.AsyncClient | None = None,
) -> list[PDFSource]:
    """Scrape a CivicPlus index page for the ordinance's article PDFs.

    Args:
        index_url: The city page that lists the ordinance articles.
        code_name: Ordinance name, used when a label has no parseable article.
        client:    Optional shared client (tests inject a mock transport).

    Returns:
        One :class:`PDFSource` per ordinance document, in page order.  Returns
        an empty list if the page is unreachable or lists no documents — the
        caller decides whether that is fatal.
    """
    owns_client = client is None
    client = client or httpx.AsyncClient(
        timeout=_FETCH_TIMEOUT_S,
        headers={"User-Agent": _USER_AGENT},
        follow_redirects=True,
    )
    try:
        resp = await client.get(index_url)
        resp.raise_for_status()
        html = resp.text
    except Exception as exc:
        logger.warning("civicplus_index_fetch_failed url=%s error=%s", index_url, exc)
        return []
    finally:
        if owns_client:
            await client.aclose()

    sources: list[PDFSource] = []
    seen: set[str] = set()

    for match in _DOC_LINK_RE.finditer(html):
        href = match.group("href")
        label = " ".join(match.group("label").split())

        url = urljoin(index_url, href)
        if url in seen:
            continue
        seen.add(url)

        if _SKIP_LABEL_RE.match(label):
            continue

        sources.append(_build_source(url, label, code_name))

    logger.info(
        "civicplus_discovery_done url=%s sources=%d",
        urlparse(index_url).netloc,
        len(sources),
    )
    return sources


def _build_source(url: str, label: str, code_name: str) -> PDFSource:
    """Turn one index link into a PDFSource with section metadata.

    ``PDFAdapter`` derives its chunk node id from ``chapter_num``/``article``/
    ``division``.  Articles that differ only by a trailing letter ("Article 10"
    vs "Article 10C") would otherwise collide, so the suffix letter is encoded
    into ``division`` (A→1, C→3) to keep node ids unique.
    """
    parsed = _ARTICLE_RE.match(label)
    if parsed is None:
        # Unrecognised label — keep the document, but with flat metadata.
        return PDFSource(url=url, chapter=code_name, section=label[:80], extra={"label": label})

    kind = parsed.group("kind").title()
    number = int(parsed.group("num"))
    suffix = (parsed.group("suffix") or "").upper()
    title = parsed.group("title").strip(" -–—:ː")

    designation = f"{number}{suffix}"
    chapter = f"{kind} {designation} — {title}" if title else f"{kind} {designation}"

    return PDFSource(
        url=url,
        chapter=chapter,
        section=f"{kind[:3]}.{designation}",
        chapter_num=number,
        article=number,
        division=(ord(suffix) - ord("A") + 1) if suffix else 0,
        extra={"label": label, "designation": designation, "title": title},
    )


# ── Zone-code extraction ─────────────────────────────────────────────────────


def make_zone_code_extractor(district_codes: tuple[str, ...]) -> Callable[[str], list[str]]:
    """Build an extractor that finds bare district codes alongside numbered ones.

    The default extractor requires a digit ("RS-8"), so cities whose districts
    are plain letters ("RM", "CS-HO") would index no zone codes at all and lose
    the retrieval boost in :mod:`plotlot.retrieval.search`.  Matching is
    case-sensitive — lowercase "is" and "as" are ordinary prose, uppercase "IS"
    is the Interim Study overlay.
    """
    if not district_codes:
        return _extract_zone_codes

    # Longest first so "CS-HO" wins over "CS" at the same position.
    ordered = sorted(district_codes, key=len, reverse=True)
    pattern = re.compile(
        r"(?<![A-Za-z0-9-])(" + "|".join(re.escape(c) for c in ordered) + r")(?![A-Za-z0-9-])"
    )

    allowed = set(district_codes)

    def extract(text: str) -> list[str]:
        found = set(pattern.findall(text))
        # Keep numbered variants of real districts ("RM-2") but drop the table
        # footnote markers ("L-7", "L-33") the generic pattern also matches.
        for code in _extract_zone_codes(text):
            if code in allowed or code.split("-")[0] in allowed:
                found.add(code)
        return sorted(found)

    return extract


# ── Factories ────────────────────────────────────────────────────────────────


async def create_civicplus_adapter(site: CivicPlusSite) -> PDFAdapter:
    """Discover a CivicPlus city's ordinance PDFs and return a ready adapter."""
    sources = await discover_civicplus_sources(site.index_url, code_name=site.code_name)
    if not sources:
        logger.warning(
            "civicplus_no_sources municipality=%s url=%s",
            site.municipality,
            site.index_url,
        )
    return PDFAdapter(
        municipality=site.municipality,
        county=site.county,
        state=site.state,
        sources=sources,
        headers={"User-Agent": _USER_AGENT},
        zone_code_extractor=make_zone_code_extractor(site.district_codes),
    )


async def create_oceanside_adapter() -> PDFAdapter:
    """Adapter for Oceanside, CA — 44 articles of the Comprehensive Zoning Ordinance."""
    return await create_civicplus_adapter(_CIVICPLUS_SITES["oceanside_ca"])
