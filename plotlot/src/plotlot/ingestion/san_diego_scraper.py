"""San Diego Municipal Code scraper — PDF-based.

San Diego is not on Municode. They publish their Land Development Code as PDFs at:
  https://docs.sandiego.gov/municode/MuniCodeChapter{N}/Ch{N}Art{A}Division{D}.pdf

Zoning chapters targeted:
  Chapter 13 — Zones (residential, commercial, industrial, agricultural, open space)
  Chapter 15 — Planned District Ordinance Zones

Discovery strategy: iterate Art01–Art10, Division01–Division20 for each chapter.
Stop on 404. SSL verification is disabled — docs.sandiego.gov has a known cert issue.
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass

import httpx

from plotlot.core.types import ChunkMetadata, TextChunk

logger = logging.getLogger(__name__)

BASE_URL = "https://docs.sandiego.gov/municode"
MUNICIPALITY = "San Diego"
COUNTY = "San Diego"
STATE = "CA"

MAX_CHUNK_SIZE = 1500
OVERLAP = 200

# Chapters to scrape: (chapter_num, chapter_label)
TARGET_CHAPTERS: list[tuple[int, str]] = [
    (13, "Zones"),
    (15, "Planned District Ordinance Zones"),
]

MAX_ARTICLES = 12
MAX_DIVISIONS = 25


@dataclass
class PdfSection:
    chapter: int
    chapter_label: str
    article: int
    division: int
    url: str
    text: str


async def _fetch_pdf_text(client: httpx.AsyncClient, url: str) -> str | None:
    """Download a PDF and extract its text. Returns None on 404 or error."""
    try:
        resp = await client.get(url, follow_redirects=True)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
    except httpx.HTTPStatusError:
        return None
    except Exception as exc:
        logger.warning("fetch_error url=%s error=%s", url, exc)
        return None

    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(resp.content))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages).strip()
    except Exception as exc:
        logger.warning("pdf_parse_error url=%s error=%s", url, exc)
        return None


async def scrape_san_diego() -> list[PdfSection]:
    """Download all zoning PDF sections for San Diego Chapters 13 and 15."""
    sections: list[PdfSection] = []

    # SSL verification disabled — docs.sandiego.gov cert is self-signed
    async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
        for chapter_num, chapter_label in TARGET_CHAPTERS:
            ch = f"{chapter_num:02d}"
            found_any_article = False

            for art in range(1, MAX_ARTICLES + 1):
                art_str = f"{art:02d}"
                found_any_division = False

                for div in range(1, MAX_DIVISIONS + 1):
                    div_str = f"{div:02d}"
                    url = f"{BASE_URL}/MuniCodeChapter{ch}/Ch{ch}Art{art_str}Division{div_str}.pdf"
                    text = await _fetch_pdf_text(client, url)
                    if text is None:
                        if div == 1:
                            break  # no divisions in this article → article doesn't exist
                        break  # no more divisions in this article

                    if len(text) < 50:
                        continue  # empty or boilerplate-only page

                    sections.append(
                        PdfSection(
                            chapter=chapter_num,
                            chapter_label=chapter_label,
                            article=art,
                            division=div,
                            url=url,
                            text=text,
                        )
                    )
                    found_any_division = True
                    logger.info(
                        "scraped Ch%s Art%s Div%s — %d chars",
                        ch,
                        art_str,
                        div_str,
                        len(text),
                    )

                if found_any_division:
                    found_any_article = True
                elif not found_any_article and art > 2:
                    break  # no articles found after first two attempts → done

    logger.info("san_diego_scrape_done sections=%d", len(sections))
    return sections


def _chunk_text(text: str, max_size: int = MAX_CHUNK_SIZE, overlap: int = OVERLAP) -> list[str]:
    """Split text into overlapping chunks by paragraph boundaries."""
    paragraphs = re.split(r"\n{2,}", text)
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(current) + len(para) + 2 <= max_size:
            current = f"{current}\n\n{para}".strip() if current else para
        else:
            if current:
                chunks.append(current)
            # carry overlap from end of previous chunk
            tail = current[-overlap:] if len(current) > overlap else current
            current = f"{tail}\n\n{para}".strip() if tail else para

    if current:
        chunks.append(current)

    return chunks


def _extract_zone_codes(text: str) -> list[str]:
    """Extract SD zone code references (e.g. RS-8, RM-1-1, CC-4-2, IL-2-1)."""
    pattern = re.compile(r"\b([A-Z]{1,4}-\d{1,2}(?:-\d{1,2})?)\b")
    matches = pattern.findall(text)
    return sorted(set(m.upper() for m in matches if len(m) >= 3))


def _extract_section_title(text: str) -> str:
    """Extract the first meaningful heading from PDF text."""
    for line in text.splitlines():
        line = line.strip()
        if len(line) > 10 and not line.startswith("©") and not re.match(r"^\d+$", line):
            return line[:120]
    return ""


def sections_to_chunks(sections: list[PdfSection]) -> list[TextChunk]:
    """Convert scraped PDF sections into TextChunk objects for embedding."""
    chunks: list[TextChunk] = []

    for section in sections:
        raw_chunks = _chunk_text(section.text)
        section_title = _extract_section_title(section.text)
        chapter_label = f"Chapter {section.chapter} — {section.chapter_label}"

        for idx, chunk_text in enumerate(raw_chunks):
            node_id = f"ch{section.chapter:02d}_art{section.article:02d}_div{section.division:02d}"
            chunks.append(
                TextChunk(
                    text=chunk_text,
                    metadata=ChunkMetadata(
                        municipality=MUNICIPALITY,
                        county=COUNTY,
                        chapter=chapter_label,
                        section=f"Art.{section.article:02d} Div.{section.division:02d}",
                        section_title=section_title,
                        zone_codes=_extract_zone_codes(chunk_text),
                        chunk_index=idx,
                        municode_node_id=f"{node_id}_chunk{idx}",
                    ),
                )
            )

    logger.info("san_diego_chunks_created count=%d", len(chunks))
    return chunks
