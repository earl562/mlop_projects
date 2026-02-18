"""HTML → text chunker for zoning ordinance sections.

Parses scraped HTML into semantically meaningful text chunks with
metadata for downstream embedding and search.
"""

import logging
import re

from bs4 import BeautifulSoup

from plotlot.core.types import ChunkMetadata, RawSection, TextChunk

logger = logging.getLogger(__name__)

MAX_CHUNK_SIZE = 1500
OVERLAP = 200

# Common zone code patterns in South Florida ordinances
ZONE_CODE_PATTERN = re.compile(
    r"\b([A-Z]{1,4}[-\s]?\d{1,3}(?:\.\d{1,2})?(?:[-/][A-Z0-9]+)?)\b"
)


def _extract_zone_codes(text: str) -> list[str]:
    """Extract zone code references from text (e.g., RS-8, RMM-25, T6-80)."""
    matches = ZONE_CODE_PATTERN.findall(text)
    filtered = []
    for m in matches:
        upper = m.upper().replace(" ", "-")
        if len(upper) >= 3 and not upper.startswith("SEC"):
            filtered.append(upper)
    return sorted(set(filtered))


def _parse_chapter_section(heading: str, parent_heading: str | None) -> tuple[str, str, str]:
    """Extract chapter, section number, and section title from headings."""
    chapter = parent_heading or ""
    section = ""
    title = heading

    sec_match = re.match(r"(Sec\.\s*[\d\-.]+)\s*[-—.]\s*(.*)", heading, re.IGNORECASE)
    if sec_match:
        section = sec_match.group(1).strip()
        title = sec_match.group(2).strip()

    return chapter, section, title


def _html_to_text(html: str) -> str:
    """Convert HTML to clean text, preserving table structure."""
    soup = BeautifulSoup(html, "html.parser")

    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            rows.append(" | ".join(cells))
        table.replace_with("\n".join(rows) + "\n")

    text = soup.get_text(separator="\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _split_text(text: str, max_size: int = MAX_CHUNK_SIZE, overlap: int = OVERLAP) -> list[str]:
    """Split text into overlapping chunks at paragraph boundaries."""
    if len(text) <= max_size:
        return [text]

    chunks = []
    paragraphs = text.split("\n\n")
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 > max_size and current:
            chunks.append(current.strip())
            if overlap > 0:
                current = current[-overlap:] + "\n\n" + para
            else:
                current = para
        else:
            current = current + "\n\n" + para if current else para

    if current.strip():
        chunks.append(current.strip())

    return chunks


def chunk_sections(sections: list[RawSection]) -> list[TextChunk]:
    """Convert raw HTML sections into text chunks with metadata."""
    all_chunks: list[TextChunk] = []

    for section in sections:
        text = _html_to_text(section.html_content)
        if not text or len(text) < 50:
            continue

        chapter, sec_num, title = _parse_chapter_section(
            section.heading, section.parent_heading
        )
        zone_codes = _extract_zone_codes(text)

        text_parts = _split_text(text)
        for i, part in enumerate(text_parts):
            chunk = TextChunk(
                text=part,
                metadata=ChunkMetadata(
                    municipality=section.municipality,
                    county=section.county,
                    chapter=chapter,
                    section=sec_num,
                    section_title=title,
                    zone_codes=zone_codes,
                    chunk_index=i,
                    municode_node_id=section.node_id,
                ),
            )
            all_chunks.append(chunk)

    logger.info("Chunked %d sections into %d chunks", len(sections), len(all_chunks))
    return all_chunks
