"""Tier-1 codifier platform discovery + generic web-code adapter.

Most US municipal codes that are NOT on Municode sit on a handful of codifier
platforms with predictable URL schemes:

  Code Publishing   https://www.codepublishing.com/{ST}/{CityName}/
  municipal.codes   https://{cityname}.municipal.codes/
  eCode360          https://resolve.ecode360.com/codes/{cityname}
  American Legal    https://codelibrary.amlegal.com/codes/{cityname}/latest/overview

``discover_codifier()`` probes those patterns for a (municipality, state) and
returns the first platform that actually hosts the city's code.  The generic
:class:`WebCodifierAdapter` then walks the code's table of contents, fetches the
zoning-related pages, and chunks them — one adapter for every platform, because
the walk only needs links + text, not platform-specific markup.

Transport note (load-bearing): these platforms sit behind Cloudflare and block
plain httpx (verified live: direct GET and curl both 403, including for cities
that don't exist — so the front door gives no existence signal at all). The
Jina Reader proxy (``r.jina.ai``) renders through the wall and returns clean
markdown, keyless at ~20 RPM or faster with ``JINA_API_KEY``. The transport
therefore tries direct HTTP first (works for unwalled sources and possibly
other egress networks) and falls back to Jina per run on the first block.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from plotlot.config import settings
from plotlot.core.types import ChunkMetadata, TextChunk
from plotlot.ingestion.adapters.base import SourceAdapter
from plotlot.ingestion.adapters.pdf import _chunk_text, _extract_zone_codes

logger = logging.getLogger(__name__)

JINA_READER_URL = "https://r.jina.ai/"

# Keyless Jina Reader allows ~20 requests/min; keyed plans are much higher.
_JINA_PACING_KEYLESS = 3.5
_JINA_PACING_KEYED = 1.0
_JINA_RATE_LIMIT_RETRIES = 3

# Hard cap on pages fetched per municipality — bounds both runtime and the
# (free-tier) Jina quota. 60 pages ≈ a full zoning title on these platforms.
MAX_PAGES_DEFAULT = 60

# Minimum extracted characters for a page to be worth chunking (filters
# nav-only / stub pages).
_MIN_PAGE_TEXT = 200

# Tight keyword list for selecting TOC links worth ingesting. Deliberately
# narrower than discovery.ZONING_KEYWORDS — TOC link labels are short, so broad
# words like "noise" or "utility" would drag in unrelated titles.
_ZONING_LINK_KEYWORDS = (
    "zoning",
    "land use",
    "land development",
    "development code",
    "subdivision",
    "planning",
)

# Child links on a zoning title page: numbered sections/chapters.
_SECTION_LABEL_RE = re.compile(
    r"(\d+\.\d+|^chapter\b|^article\b|^division\b|^part\b|^§|^sec\b)", re.IGNORECASE
)

_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_SKIP_HREF_RE = re.compile(r"\.(css|js|png|jpe?g|gif|svg|ico|zip)(\?|$)", re.IGNORECASE)

# Code Publishing migrated to a numeric SPA whose Title/Chapter links render as
# empty shells through Jina; the real content stays at the legacy static path
# html/{City}{TitleNum}/{City}{TitleChapter}.html  (10.22 → Sausalito1022.html).
_CP_TITLE_RE = re.compile(r"\bTitle\s+(\d+)", re.IGNORECASE)
_CP_CHAPTER_RE = re.compile(r"\bChapter\s+(\d+\.\d+)\b", re.IGNORECASE)


def _codepublishing_static_base(root_url: str) -> tuple[str, str] | None:
    """Return ``(base_url, city_slug)`` for a codepublishing root, else ``None``.

    ``https://www.codepublishing.com/CA/Sausalito/…`` → ``(".../CA/Sausalito/", "Sausalito")``
    """
    parsed = urlparse(root_url)
    if "codepublishing.com" not in parsed.netloc:
        return None
    parts = [seg for seg in parsed.path.split("/") if seg]
    if len(parts) < 2:
        return None
    return f"{parsed.scheme}://{parsed.netloc}/{parts[0]}/{parts[1]}/", parts[1]


# ── Models ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CodifierHit:
    """A codifier platform confirmed to host a municipality's code."""

    platform: str  # "codepublishing" | "municipal.codes" | "ecode360" | "amlegal"
    url: str  # the probed root URL
    final_url: str  # post-redirect URL (differs for ecode360 resolve links)
    title: str  # page title, e.g. "Chula Vista Municipal Code"


@dataclass
class PageContent:
    """Normalized result of fetching one page through the transport."""

    target_status: int  # the TARGET site's status (404 ≠ transport failure)
    text: str  # readable text / markdown of the page
    title: str
    final_url: str
    links: list[tuple[str, str]] = field(default_factory=list)  # (label, abs URL)
    blocked: bool = False  # a bot challenge leaked through — content unusable


# ── Transport ────────────────────────────────────────────────────────────────


class CodifierTransport:
    """Direct-first page fetcher with per-run Jina Reader fallback.

    The first hard block (403/anti-bot challenge) flips the run to Jina for all
    subsequent fetches — no point re-hitting a wall page by page.
    """

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client
        self._use_jina = False
        self._jina_key = (settings.jina_api_key or "").strip()

    async def fetch(self, url: str) -> PageContent:
        if not self._use_jina:
            page = await self._fetch_direct(url)
            if page is not None and not page.blocked:
                return page
            logger.info("codifier_transport direct blocked/failed, switching to jina url=%s", url)
            self._use_jina = True
        return await self._fetch_jina(url)

    async def _fetch_direct(self, url: str) -> PageContent | None:
        try:
            resp = await self._client.get(url, follow_redirects=True)
        except Exception as exc:  # noqa: BLE001 — any transport error → try jina
            logger.debug("codifier_direct_error url=%s error=%s", url, exc)
            return None
        body = resp.text
        if resp.status_code in (403, 503) or _looks_like_challenge(body):
            return PageContent(
                target_status=resp.status_code,
                text="",
                title="",
                final_url=str(resp.url),
                blocked=True,
            )
        return _parse_html_page(body, str(resp.url), resp.status_code)

    async def _fetch_jina(self, url: str) -> PageContent:
        headers = {"X-Retain-Images": "none"}
        if self._jina_key:
            headers["Authorization"] = f"Bearer {self._jina_key}"
        pacing = _JINA_PACING_KEYED if self._jina_key else _JINA_PACING_KEYLESS

        for attempt in range(_JINA_RATE_LIMIT_RETRIES + 1):
            try:
                resp = await self._client.get(f"{JINA_READER_URL}{url}", headers=headers)
            except Exception as exc:  # noqa: BLE001
                logger.warning("codifier_jina_error url=%s error=%s", url, exc)
                return PageContent(target_status=0, text="", title="", final_url=url, blocked=True)
            if resp.status_code == 429 and attempt < _JINA_RATE_LIMIT_RETRIES:
                await asyncio.sleep(15.0 * (attempt + 1))
                continue
            await asyncio.sleep(pacing)
            if resp.status_code != 200:
                return PageContent(target_status=0, text="", title="", final_url=url, blocked=True)
            return _parse_jina_page(resp.text, url)
        return PageContent(target_status=0, text="", title="", final_url=url, blocked=True)


def _looks_like_challenge(body: str) -> bool:
    head = body[:3000]
    return "Just a moment" in head or "Verifying you are human" in head


def _parse_html_page(body: str, final_url: str, status: int) -> PageContent:
    soup = BeautifulSoup(body, "html.parser")
    title_el = soup.find("title")
    title = title_el.get_text(strip=True) if title_el else ""
    links: list[tuple[str, str]] = []
    for a in soup.find_all("a", href=True):
        href = str(a["href"]).strip()
        if href.startswith(("mailto:", "javascript:", "#")) or _SKIP_HREF_RE.search(href):
            continue
        label = a.get_text(" ", strip=True)
        if label:
            links.append((label, urljoin(final_url, href)))
    text = soup.get_text(" ", strip=True)
    return PageContent(
        target_status=status, text=text, title=title, final_url=final_url, links=links
    )


def _parse_jina_page(body: str, requested_url: str) -> PageContent:
    """Parse Jina Reader's markdown envelope into a PageContent."""
    warn = re.search(r"Warning: Target URL returned error (\d+)", body[:2000])
    target_status = int(warn.group(1)) if warn else 200

    title_m = re.search(r"^Title: (.+)$", body[:2000], re.MULTILINE)
    title = title_m.group(1).strip() if title_m else ""
    final_m = re.search(r"^URL Source: (\S+)$", body[:2000], re.MULTILINE)
    final_url = final_m.group(1) if final_m else requested_url

    marker = "Markdown Content:"
    idx = body.find(marker)
    text = body[idx + len(marker) :].strip() if idx >= 0 else body

    links: list[tuple[str, str]] = []
    for label, href in _MD_LINK_RE.findall(text):
        if _SKIP_HREF_RE.search(href):
            continue
        label_clean = re.sub(r"\s+", " ", label).strip()
        if label_clean:
            links.append((label_clean, href))

    blocked = _looks_like_challenge(text)
    return PageContent(
        target_status=target_status,
        text=text,
        title=title,
        final_url=final_url,
        links=links,
        blocked=blocked,
    )


# ── Discovery ────────────────────────────────────────────────────────────────


def codifier_url_patterns(municipality: str, state: str) -> list[tuple[str, str]]:
    """Return (platform, url) probe candidates for a municipality."""
    nospace = municipality.strip().replace(" ", "")
    lower = nospace.lower()
    underscore = municipality.strip().replace(" ", "_").lower()
    state_up = state.strip().upper()

    patterns = [
        ("codepublishing", f"https://www.codepublishing.com/{state_up}/{nospace}/"),
        ("municipal.codes", f"https://{lower}.municipal.codes/"),
        ("ecode360", f"https://resolve.ecode360.com/codes/{lower}"),
        ("amlegal", f"https://codelibrary.amlegal.com/codes/{lower}/latest/overview"),
    ]
    if underscore != lower:
        patterns.append(
            ("amlegal", f"https://codelibrary.amlegal.com/codes/{underscore}/latest/overview")
        )
    return patterns


def _confirms_city(page: PageContent, municipality: str) -> bool:
    """The page must actually mention the city — guards against soft-404s."""
    city_l = municipality.strip().lower()
    haystack = f"{page.title} {page.text[:4000]} {page.final_url}".lower()
    return city_l in haystack or city_l.replace(" ", "") in haystack


async def discover_codifier(
    municipality: str,
    state: str,
    *,
    transport: CodifierTransport | None = None,
) -> CodifierHit | None:
    """Probe known codifier platforms for a municipality's code. First hit wins.

    Returns None when every platform genuinely 404s (or the transport is fully
    blocked) — the caller falls through to NoAdapterError as before, so this
    tier only ever ADDS coverage.
    """
    if not municipality.strip() or not state.strip():
        return None

    own_client: httpx.AsyncClient | None = None
    if transport is None:
        own_client = httpx.AsyncClient(timeout=60.0)
        transport = CodifierTransport(own_client)

    try:
        for platform, url in codifier_url_patterns(municipality, state):
            page = await transport.fetch(url)
            if page.blocked or page.target_status != 200:
                continue
            if not _confirms_city(page, municipality):
                continue
            logger.info(
                "codifier_discovered municipality=%s platform=%s url=%s title=%s",
                municipality,
                platform,
                page.final_url,
                page.title,
            )
            return CodifierHit(
                platform=platform, url=url, final_url=page.final_url, title=page.title
            )
        return None
    finally:
        if own_client is not None:
            await own_client.aclose()


# ── Adapter ──────────────────────────────────────────────────────────────────


class WebCodifierAdapter(SourceAdapter):
    """Generic ingestion adapter for any discovered codifier platform.

    Walk: root TOC → links whose label matches zoning keywords → their pages
    → numbered child sections, up to ``max_pages`` total. Every fetched page
    with substantive text becomes chunks; node IDs are stable URL slugs so
    re-ingestion upserts instead of duplicating.
    """

    name = "codifier"

    def __init__(
        self,
        municipality: str,
        county: str,
        state: str,
        hit: CodifierHit,
        max_pages: int = MAX_PAGES_DEFAULT,
    ) -> None:
        super().__init__(municipality, county, state)
        self.hit = hit
        self.max_pages = max_pages

    async def _expand_codepublishing(
        self,
        transport: CodifierTransport,
        root_url: str,
        title_links: list[tuple[str, str]],
    ) -> list[tuple[str, str]]:
        """Expand codepublishing Title links → legacy static chapter content URLs.

        The numeric SPA Title link (``/CA/Sausalito/47134195``) renders empty;
        the real content lives at ``html/{City}{T}/{City}{TC}.html``. Fetch each
        Title's static index, read its chapter list, and derive the chapter URL
        from the chapter number (10.22 → ``Sausalito1022.html``). Title links that
        are already static ``.html`` pages pass through unchanged.
        """
        base_info = _codepublishing_static_base(root_url)
        if base_info is None:
            return title_links
        base, city = base_info

        expanded: list[tuple[str, str]] = []
        seen: set[str] = set()
        for label, url in title_links:
            if url.endswith(".html"):
                expanded.append((label, url))
                continue
            tmatch = _CP_TITLE_RE.search(label)
            if tmatch is None:
                expanded.append((label, url))
                continue
            tnum = tmatch.group(1)
            index = await transport.fetch(f"{base}html/{city}{tnum}/{city}{tnum}.html")
            if index.blocked or index.target_status != 200:
                expanded.append((label, url))  # fall back to the original link
                continue
            for clabel, _ in index.links:
                cmatch = _CP_CHAPTER_RE.search(clabel)
                if cmatch is None or not cmatch.group(1).startswith(tnum + "."):
                    continue
                chapter = cmatch.group(1)
                content_url = f"{base}html/{city}{tnum}/{city}{chapter.replace('.', '')}.html"
                if content_url in seen:
                    continue
                seen.add(content_url)
                expanded.append((clabel.strip(), content_url))
        return expanded

    async def fetch_chunks(self) -> list[TextChunk]:
        chunks: list[TextChunk] = []
        async with httpx.AsyncClient(timeout=60.0) as client:
            transport = CodifierTransport(client)

            root = await transport.fetch(self.hit.url)
            if root.blocked or root.target_status != 200:
                logger.warning(
                    "codifier_root_unreachable municipality=%s url=%s",
                    self.municipality,
                    self.hit.url,
                )
                return []

            allowed_hosts = {
                urlparse(root.final_url).netloc,
                urlparse(self.hit.url).netloc,
            }
            zoning_links = _select_links(
                root.links, allowed_hosts, keyword_match=True, section_match=False
            )
            if not zoning_links:
                # Some TOCs label everything by number ("Title 19") — fall back
                # to numbered links so we still get the code rather than nothing.
                zoning_links = _select_links(
                    root.links, allowed_hosts, keyword_match=False, section_match=True
                )

            if self.hit.platform == "codepublishing":
                # Code Publishing migrated to a numeric SPA whose Title links are
                # empty shells; expand each to its legacy static chapter pages.
                # Zoning-named titles first so the page budget covers them before
                # subdivisions/planning if the code is large.
                zoning_links.sort(key=lambda lu: 0 if "zoning" in lu[0].lower() else 1)
                zoning_links = await self._expand_codepublishing(
                    transport, root.final_url or self.hit.url, zoning_links
                )

            logger.info(
                "codifier_walk_start municipality=%s platform=%s zoning_links=%d",
                self.municipality,
                self.hit.platform,
                len(zoning_links),
            )

            visited: set[str] = {self.hit.url, root.final_url}
            # SPA shells (codepublishing) serve the landing page for every
            # fragment URL — content hashing makes those repeats inert instead
            # of letting them poison the index with duplicate help-page text.
            seen_text: set[str] = {_text_hash(_strip_markdown_noise(root.text))}
            used_node_ids: set[str] = set()
            fetch_budget = [self.max_pages]

            async def fetch_page(url: str) -> tuple[PageContent, str]:
                """Fetch with one re-rooted retry on 404 (new-layout SPA links
                drop the jurisdiction prefix: /CVMC/19 404s server-side but
                /CA/ChulaVista/CVMC/19 serves the real page — verified live).
                Every attempt counts against the page budget."""
                fetch_budget[0] -= 1
                page = await transport.fetch(url)
                if page.target_status == 404 and fetch_budget[0] > 0:
                    alt = _reroot_candidate(url, root.final_url or self.hit.url)
                    if alt and alt not in visited:
                        visited.add(alt)
                        fetch_budget[0] -= 1
                        alt_page = await transport.fetch(alt)
                        if alt_page.target_status == 200 and not alt_page.blocked:
                            return alt_page, alt
                return page, url

            for chapter_label, chapter_url in zoning_links:
                if fetch_budget[0] <= 0:
                    break
                if chapter_url in visited:
                    continue
                visited.add(chapter_url)
                page, served_url = await fetch_page(chapter_url)
                if page.blocked or page.target_status != 200:
                    continue

                chunks.extend(
                    self._page_to_chunks(
                        page,
                        requested_url=served_url,
                        chapter=chapter_label,
                        section=chapter_label,
                        seen_text=seen_text,
                        used_node_ids=used_node_ids,
                    )
                )

                for sec_label, sec_url in _select_links(
                    page.links, allowed_hosts, keyword_match=False, section_match=True
                ):
                    if fetch_budget[0] <= 0:
                        break
                    if sec_url in visited:
                        continue
                    # In-page anchors (…page.html#17.08.010) are the same
                    # document — fetching them would burn quota for repeats.
                    if _strip_fragment(sec_url) in {
                        _strip_fragment(chapter_url),
                        _strip_fragment(served_url),
                        _strip_fragment(page.final_url),
                    }:
                        continue
                    visited.add(sec_url)
                    sec_page, sec_served = await fetch_page(sec_url)
                    if sec_page.blocked or sec_page.target_status != 200:
                        continue
                    chunks.extend(
                        self._page_to_chunks(
                            sec_page,
                            requested_url=sec_served,
                            chapter=chapter_label,
                            section=sec_label,
                            seen_text=seen_text,
                            used_node_ids=used_node_ids,
                        )
                    )

        logger.info(
            "codifier_adapter_done municipality=%s platform=%s pages=%d chunks=%d",
            self.municipality,
            self.hit.platform,
            len({c.metadata.municode_node_id for c in chunks}),
            len(chunks),
        )
        return chunks

    def _page_to_chunks(
        self,
        page: PageContent,
        *,
        requested_url: str,
        chapter: str,
        section: str,
        seen_text: set[str],
        used_node_ids: set[str],
    ) -> list[TextChunk]:
        text = _normalize_zone_tables(_strip_markdown_noise(page.text))
        if len(text) < _MIN_PAGE_TEXT:
            return []
        text_hash = _text_hash(text)
        if text_hash in seen_text:
            logger.debug("codifier_duplicate_content url=%s", requested_url)
            return []
        seen_text.add(text_hash)

        # Node ID from the REQUESTED URL — Jina strips fragments from its
        # reported final URL, which collapsed distinct SPA pages to one ID.
        node_id = _page_node_id(requested_url)
        if node_id in used_node_ids:
            node_id = f"{node_id}_{text_hash[:8]}"
        used_node_ids.add(node_id)

        return [
            TextChunk(
                text=chunk,
                metadata=ChunkMetadata(
                    municipality=self.municipality,
                    county=self.county,
                    chapter=chapter[:200],
                    section=section[:200],
                    section_title=(page.title or section)[:200],
                    zone_codes=_extract_zone_codes(chunk),
                    chunk_index=idx,
                    municode_node_id=node_id,
                ),
            )
            for idx, chunk in enumerate(_chunk_text(text))
        ]


def _select_links(
    links: list[tuple[str, str]],
    allowed_hosts: set[str],
    *,
    keyword_match: bool,
    section_match: bool,
) -> list[tuple[str, str]]:
    """Filter TOC links to same-host candidates worth following."""
    selected: list[tuple[str, str]] = []
    seen: set[str] = set()
    for label, raw_url in links:
        url = _resolve_spa_fragment(raw_url)
        if url in seen:
            continue
        host = urlparse(url).netloc
        if host not in allowed_hosts:
            continue
        label_l = label.lower()
        keyword_ok = keyword_match and any(kw in label_l for kw in _ZONING_LINK_KEYWORDS)
        section_ok = section_match and bool(_SECTION_LABEL_RE.search(label.strip()))
        if keyword_ok or section_ok:
            seen.add(url)
            selected.append((label, url))
    return selected


def _resolve_spa_fragment(url: str) -> str:
    """Rewrite Code-Publishing-style SPA fragments to their real content paths.

    The TOC links ``…/CA/Poway/#!/Poway17/Poway17.html``, but the fragment never
    reaches the server — every fetch returns the landing shell. The actual
    content is served from an ``html/`` subfolder (verified live):
    ``…/CA/Poway/html/Poway17/Poway17.html``.
    """
    parsed = urlparse(url)
    if not parsed.fragment.startswith("!/"):
        return url
    base = parsed.path if parsed.path.endswith("/") else parsed.path.rsplit("/", 1)[0] + "/"
    return parsed._replace(path=f"{base}html/{parsed.fragment[2:]}", fragment="").geturl()


def _reroot_candidate(url: str, root_url: str) -> str | None:
    """Re-root a prefix-dropping SPA link under the code's base path.

    Code Publishing's new layout emits TOC hrefs like
    ``https://www.codepublishing.com/CVMC/19`` which 404 server-side; the real
    route keeps the jurisdiction prefix: ``…/CA/ChulaVista/CVMC/19``. Returns
    None when the link is off-host or already under the base path.
    """
    p, r = urlparse(url), urlparse(root_url)
    if p.netloc != r.netloc:
        return None
    base = r.path if r.path.endswith("/") else f"{r.path}/"
    if not p.path or p.path.startswith(base):
        return None
    return p._replace(path=f"{base.rstrip('/')}{p.path}").geturl()


def _strip_fragment(url: str) -> str:
    return url.split("#", 1)[0]


def _text_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip().lower()
    return hashlib.sha1(normalized.encode("utf-8", errors="replace")).hexdigest()


def _strip_markdown_noise(text: str) -> str:
    """Drop markdown link syntax (keep labels) and image refs before chunking."""
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = _MD_LINK_RE.sub(r"\1", text)
    return text.strip()


# Zone-code cell: "R-1", "R-1-6", "R-2-2.5", "PR", "H", "A" (1-2 letter standalone
# districts or letter+number with optional sub-segments). Excludes plain words.
_ZONE_CELL_RE = re.compile(r"^[A-Z]{1,3}(?:-[0-9][A-Z0-9.]*)+$|^[A-Z]{1,2}$")
_FOOTNOTE_TAIL_RE = re.compile(r"\s+\d+(?:\s*,\s*\d+)*$")  # "Minimum lot width 2, 3" → drop


def _md_cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_zone_cell(c: str) -> bool:
    return bool(_ZONE_CELL_RE.match(c)) and c not in ("SMC", "SF", "DU")


def _normalize_zone_tables(text: str) -> str:
    """Rewrite codifier markdown standards tables into per-zone labeled rows.

    Codifier sources (Code Publishing/amlegal via Jina) emit standards tables as
    markdown that lost the HTML colspan, so the column header is split across two
    rows — parent districts (``R-1 | R-2 | R-3 | PR``) then sub-districts
    (``R-1-6 | R-1-8 | R-2-2.5 …``) — and the data rows carry one value per
    sub-district. A raw dump leaves "R-2-2.5"'s front setback ambiguous. We
    reconstruct the sub-district column order (a parent expands to the
    sub-districts that carry its prefix) and re-emit each district's standards:

        R-2-2.5 — Minimum parcel size: 5,000 sf; Minimum lot width: 50 feet; …

    Only zone-keyed numeric standards tables are rewritten; everything else
    (prose, non-zone tables) is left untouched.
    """
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        if lines[i].lstrip().startswith("|"):
            j = i
            while j < n and lines[j].lstrip().startswith("|"):
                j += 1
            rewritten = _rewrite_zone_table(lines[i:j])
            out.append(rewritten if rewritten is not None else "\n".join(lines[i:j]))
            i = j
        else:
            out.append(lines[i])
            i += 1
    return "\n".join(out)


def _rewrite_zone_table(block: list[str]) -> str | None:
    """Return per-zone labeled text for a zone-keyed standards table, else None."""
    rows = [_md_cells(ln) for ln in block]
    # Drop separator rows ("| --- |") and single-cell title rows; keep title text.
    title = ""
    body: list[list[str]] = []
    for r in rows:
        if len(r) == 1:
            if r[0] and set(r[0]) > set("-"):
                title = r[0]
            continue
        if all(set(c) <= set("- ") for c in r):
            continue
        body.append(r)

    zone_rows = [r for r in body if sum(_is_zone_cell(c) for c in r) >= 2]
    data_rows = [
        r for r in body if r not in zone_rows and sum(1 for c in r[1:] if re.search(r"\d", c)) >= 2
    ]
    if not zone_rows or not data_rows:
        return None

    zone_lists = [[c for c in r if _is_zone_cell(c)] for r in zone_rows]
    parents = zone_lists[0]
    children = zone_lists[1] if len(zone_lists) > 1 else []
    order: list[str] = []
    for p in parents:
        kids = [c for c in children if c.startswith(p + "-")]
        order.extend(kids if kids else [p])
    if not order:
        return None

    lines_out: list[str] = []
    if title:
        lines_out.append(title)
    for zi, zone in enumerate(order):
        pairs = []
        for dr in data_rows:
            req = _FOOTNOTE_TAIL_RE.sub("", dr[0]).strip()
            vals = dr[1:]
            if req and zi < len(vals) and vals[zi]:
                pairs.append(f"{req}: {vals[zi]}")
        if pairs:
            lines_out.append(f"{zone} — " + "; ".join(pairs))
    return "\n".join(lines_out) if len(lines_out) > (1 if title else 0) else None


def _page_node_id(url: str) -> str:
    """Stable, readable node ID from a page URL (drives idempotent upserts)."""
    parsed = urlparse(url)
    raw = f"{parsed.path}#{parsed.fragment}" if parsed.fragment else parsed.path
    slug = re.sub(r"[^A-Za-z0-9]+", "_", raw).strip("_")
    return f"web_{slug[-180:]}" if slug else "web_root"
