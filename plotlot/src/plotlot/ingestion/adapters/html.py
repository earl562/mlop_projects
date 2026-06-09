"""Generic HTML adapter for municipalities with web-based zoning ordinances.

For municipalities whose zoning code lives on a custom CMS (not Municode,
not PDF) — pass a list of HTML page URLs and an optional chapter label.
The adapter downloads each page, wraps it in a RawSection, and delegates
to the existing chunk_sections() for HTML-to-text and splitting.

Typical use:
    adapter = HTMLAdapter(
        municipality="Some City",
        county="some_county",
        state="CA",
        urls=[
            "https://city.gov/planning/zoning/residential",
            "https://city.gov/planning/zoning/commercial",
        ],
        chapter="Title 17 — Zoning",
    )
    chunks = await adapter.fetch_chunks()
"""

from __future__ import annotations

import logging

import httpx
from bs4 import BeautifulSoup

from plotlot.core.types import RawSection, TextChunk
from plotlot.ingestion.adapters.base import SourceAdapter
from plotlot.ingestion.chunker import chunk_sections

logger = logging.getLogger(__name__)


class HTMLAdapter(SourceAdapter):
    """Fetches zoning ordinances from a list of raw HTML page URLs.

    Each URL is treated as one ordinance section.  Section headings are
    auto-extracted from H1/H2/title tags; if none is found the adapter
    falls back to "Section N" where N is the URL's index in the list.
    """

    name = "html"

    def __init__(
        self,
        municipality: str,
        county: str,
        state: str,
        urls: list[str],
        chapter: str = "",
    ) -> None:
        super().__init__(municipality, county, state)
        self.urls = urls
        self.chapter = chapter

    async def fetch_chunks(self) -> list[TextChunk]:
        sections: list[RawSection] = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            for i, url in enumerate(self.urls):
                html = await self._fetch_html(client, url)
                if not html:
                    continue
                heading = _extract_heading(html) or f"Section {i + 1}"
                sections.append(
                    RawSection(
                        municipality=self.municipality,
                        county=self.county,
                        node_id=f"html_{i}",
                        heading=heading,
                        parent_heading=self.chapter or None,
                        html_content=html,
                        depth=1,
                    )
                )

        chunks = chunk_sections(sections)
        logger.info(
            "html_adapter_done municipality=%s chunks=%d",
            self.municipality,
            len(chunks),
        )
        return chunks

    async def _fetch_html(self, client: httpx.AsyncClient, url: str) -> str | None:
        """Fetch a single HTML page. Returns None on any error."""
        try:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            logger.warning("html_fetch_error url=%s error=%s", url, exc)
            return None


def _extract_heading(html: str) -> str:
    """Extract the first H1, H2, or <title> text from an HTML page."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in ("h1", "h2", "title"):
        el = soup.find(tag)
        if el:
            text = el.get_text(strip=True)
            if text:
                return text[:200]
    return ""
