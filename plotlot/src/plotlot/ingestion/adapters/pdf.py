"""Generic PDF adapter for municipalities that publish zoning as PDF files.

Generalizes the San Diego-specific san_diego_scraper.py into a reusable
adapter that works for any municipality whose ordinance is a PDF (or set of
PDFs) at known URLs.

Two entry points:
  PDFAdapter(municipality, county, state, sources)   — use when URLs are known
  create_san_diego_adapter()                          — factory that probes SD's
                                                        chapter/article/division
                                                        URL grid before returning
                                                        a configured PDFAdapter
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass, field

import httpx

from plotlot.core.types import ChunkMetadata, TextChunk
from plotlot.ingestion.adapters.base import SourceAdapter

logger = logging.getLogger(__name__)

# ── Chunking constants ───────────────────────────────────────────────────────

MAX_CHUNK_SIZE = 1500
OVERLAP = 200

# ── San Diego URL grid ───────────────────────────────────────────────────────

_SD_BASE_URL = "https://docs.sandiego.gov/municode"
_SD_CHAPTERS: list[tuple[int, str]] = [
    (11, "Subdivisions"),
    (12, "Signs"),
    (13, "Zones"),
    (14, "Development Regulations"),
    (15, "Planned District Ordinance Zones"),
]
_SD_MAX_ARTICLES = 30
_SD_MAX_DIVISIONS = 25


# ── Data types ───────────────────────────────────────────────────────────────


@dataclass
class PDFSource:
    """A single PDF URL to download with its section metadata."""

    url: str
    chapter: str = ""
    section: str = ""
    chapter_num: int = 0
    article: int = 0
    division: int = 0
    extra: dict[str, str] = field(default_factory=dict)


# ── Adapter ──────────────────────────────────────────────────────────────────


class PDFAdapter(SourceAdapter):
    """Fetches zoning ordinances from a list of PDF URLs.

    For each PDFSource: downloads the PDF, extracts text with pypdf,
    splits into overlapping chunks at paragraph boundaries (with single-newline
    fallback for PDFs that lack paragraph breaks), and attaches metadata.
    """

    name = "pdf"

    def __init__(
        self,
        municipality: str,
        county: str,
        state: str,
        sources: list[PDFSource],
        verify_ssl: bool = True,
        max_chunk_size: int = MAX_CHUNK_SIZE,
        overlap: int = OVERLAP,
    ) -> None:
        super().__init__(municipality, county, state)
        self.sources = sources
        self.verify_ssl = verify_ssl
        self.max_chunk_size = max_chunk_size
        self.overlap = overlap

    async def fetch_chunks(self) -> list[TextChunk]:
        chunks: list[TextChunk] = []

        async with httpx.AsyncClient(timeout=30.0, verify=self.verify_ssl) as client:
            for source in self.sources:
                text = await _fetch_pdf_text(client, source.url)
                if text is None or len(text) < 50:
                    continue

                raw_chunks = _chunk_text(text, self.max_chunk_size, self.overlap)
                section_title = _extract_section_title(text)

                for idx, chunk_text_str in enumerate(raw_chunks):
                    node_id = (
                        f"ch{source.chapter_num:02d}"
                        f"_art{source.article:02d}"
                        f"_div{source.division:02d}"
                    )
                    chunks.append(
                        TextChunk(
                            text=chunk_text_str,
                            metadata=ChunkMetadata(
                                municipality=self.municipality,
                                county=self.county,
                                chapter=source.chapter,
                                section=source.section,
                                section_title=section_title,
                                zone_codes=_extract_zone_codes(chunk_text_str),
                                chunk_index=idx,
                                municode_node_id=f"{node_id}_chunk{idx}",
                            ),
                        )
                    )

        logger.info(
            "pdf_adapter_done municipality=%s chunks=%d",
            self.municipality,
            len(chunks),
        )
        return chunks


# ── HTTP helpers ─────────────────────────────────────────────────────────────


async def _fetch_pdf_text(client: httpx.AsyncClient, url: str) -> str | None:
    """Download a PDF and extract its text. Returns None on 404 or parse error."""
    try:
        resp = await client.get(url, follow_redirects=True)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
    except httpx.HTTPStatusError:
        return None
    except Exception as exc:
        logger.warning("pdf_fetch_error url=%s error=%s", url, exc)
        return None

    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(resp.content))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages).strip()
    except Exception as exc:
        logger.warning("pdf_parse_error url=%s error=%s", url, exc)
        return None


async def _probe_url(client: httpx.AsyncClient, url: str) -> bool:
    """Return True if the URL exists.  Uses HEAD; falls back to GET on 405."""
    try:
        resp = await client.head(url, follow_redirects=True)
        if resp.status_code == 405:
            resp = await client.get(url, follow_redirects=True)
        return resp.status_code not in (400, 403, 404, 410)
    except Exception:
        return False


# ── Text processing ──────────────────────────────────────────────────────────


def _chunk_text(
    text: str,
    max_size: int = MAX_CHUNK_SIZE,
    overlap: int = OVERLAP,
) -> list[str]:
    """Split text into overlapping chunks at paragraph boundaries.

    PDF text from docs.sandiego.gov (and many others) uses single newlines
    instead of double newlines.  Detects which separator is present and
    uses it consistently so the entire document does not collapse to one chunk.
    """
    if not text:
        return []

    if len(text) <= max_size:
        return [text]

    if "\n\n" in text:
        paragraphs = re.split(r"\n{2,}", text)
        separator = "\n\n"
    else:
        paragraphs = text.splitlines()
        separator = "\n"

    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        candidate = f"{current}{separator}{para}".strip() if current else para
        if len(candidate) <= max_size:
            current = candidate
        else:
            if current:
                chunks.append(current)
            tail = (
                current[-overlap:]
                if (overlap > 0 and len(current) > overlap)
                else (current if overlap > 0 else "")
            )
            current = f"{tail}{separator}{para}".strip() if tail else para

    if current:
        chunks.append(current)

    return chunks


def _extract_zone_codes(text: str) -> list[str]:
    """Extract zone code references from text (e.g. RS-8, RM-3-7, CC-4-2)."""
    pattern = re.compile(r"\b([A-Z]{1,4}-\d{1,2}(?:-\d{1,2})?)\b")
    matches = pattern.findall(text)
    return sorted({m.upper() for m in matches if len(m) >= 3})


def _extract_section_title(text: str) -> str:
    """Extract the first meaningful heading line from text."""
    for line in text.splitlines():
        line = line.strip()
        if len(line) > 10 and not line.startswith("©") and not re.match(r"^\d+$", line):
            return line[:120]
    return ""


# ── San Diego factory ────────────────────────────────────────────────────────


async def discover_san_diego_sources(
    max_articles: int = _SD_MAX_ARTICLES,
    max_divisions: int = _SD_MAX_DIVISIONS,
) -> list[PDFSource]:
    """Probe the docs.sandiego.gov URL grid to build the list of PDF sources.

    Iterates chapter → article → division with the same early-exit logic as
    the original san_diego_scraper.py — stops probing an article when division
    1 is missing (article doesn't exist) and stops probing a chapter after two
    consecutive articleless attempts at the start.

    Uses HEAD requests to check existence without downloading content.
    """
    sources: list[PDFSource] = []

    # SSL verification disabled — docs.sandiego.gov has a known cert issue.
    async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
        for chapter_num, chapter_label in _SD_CHAPTERS:
            ch = f"{chapter_num:02d}"
            chapter_name = f"Chapter {chapter_num} — {chapter_label}"
            found_any_article = False

            for art in range(1, max_articles + 1):
                art_str = f"{art:02d}"
                found_any_division = False

                for div in range(1, max_divisions + 1):
                    div_str = f"{div:02d}"
                    url = (
                        f"{_SD_BASE_URL}/MuniCodeChapter{ch}"
                        f"/Ch{ch}Art{art_str}Division{div_str}.pdf"
                    )
                    exists = await _probe_url(client, url)
                    if not exists:
                        if div == 1:
                            break  # article doesn't exist — skip to next
                        break  # no more divisions in this article

                    sources.append(
                        PDFSource(
                            url=url,
                            chapter=chapter_name,
                            section=f"Art.{art_str} Div.{div_str}",
                            chapter_num=chapter_num,
                            article=art,
                            division=div,
                        )
                    )
                    found_any_division = True

                if found_any_division:
                    found_any_article = True
                elif not found_any_article and art > 2:
                    break  # no articles after first two tries — chapter done

    logger.info("san_diego_discovery_done sources=%d", len(sources))
    return sources


async def create_san_diego_adapter() -> PDFAdapter:
    """Discover available San Diego PDF sections and return a PDFAdapter."""
    sources = await discover_san_diego_sources()
    return PDFAdapter(
        municipality="San Diego",
        county="San Diego",
        state="CA",
        sources=sources,
        verify_ssl=False,
    )
