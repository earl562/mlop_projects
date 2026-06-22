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
ZONE_CODE_PATTERN = re.compile(r"\b([A-Z]{1,4}[-\s]?\d{1,3}(?:\.\d{1,2})?(?:[-/][A-Z0-9]+)?)\b")


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


def _flatten_columns(columns) -> list[str]:
    """Flatten a (possibly MultiIndex) set of DataFrame columns to readable labels.

    Multi-row ordinance headers parse as tuples, e.g.
    ('Minimum Setbacks', 'Front') → "Minimum Setbacks Front". Repeated levels
    ("Zone", "Zone") collapse to "Zone"; pandas "Unnamed: N" placeholders drop out.
    """
    labels: list[str] = []
    for col in columns:
        parts = col if isinstance(col, tuple) else (col,)
        clean: list[str] = []
        for p in parts:
            s = str(p).strip()
            if not s or s.startswith("Unnamed"):
                continue
            if not clean or clean[-1] != s:  # drop duplicated header levels
                clean.append(s)
        labels.append(" ".join(clean))
    return labels


def _table_to_text(table_html: str) -> str | None:
    """Serialize an HTML table as labeled rows: ``RowLabel — Col: val; Col: val``.

    The old flattener joined cells with ``" | "`` and dropped the column headers,
    so a zone's standards row (``RO-2 | 20,000 s.f. | ... | 30 ft. | 15 ft.``)
    lost which value was the front setback vs. the side setback — the LLM then
    reported them as "not found". ``pandas.read_html`` resolves colspan/rowspan
    and multi-row headers into a clean grid; we re-emit each row with its column
    labels so every value stays attached to its meaning. Returns ``None`` (caller
    falls back to the pipe-join) when the table can't be parsed.
    """
    from io import StringIO

    import pandas as pd

    try:
        frames = pd.read_html(StringIO(table_html))
    except Exception:
        return None

    lines: list[str] = []
    for frame in frames:
        frame = frame.fillna("")
        cols = _flatten_columns(frame.columns)
        for row in frame.itertuples(index=False, name=None):
            cells = [str(v).strip() for v in row]
            if not any(cells):
                continue
            label = cells[0]
            pairs = [
                f"{cols[i]}: {cells[i]}" if i < len(cols) and cols[i] else cells[i]
                for i in range(1, len(cells))
                if cells[i]
            ]
            if pairs:
                lines.append(f"{label} — " + "; ".join(pairs) if label else "; ".join(pairs))
            elif label:
                lines.append(label)
    return "\n".join(lines) if lines else None


def _html_to_text(html: str) -> str:
    """Convert HTML to clean text, preserving table structure as labeled rows."""
    soup = BeautifulSoup(html, "html.parser")

    for table in soup.find_all("table"):
        labeled = _table_to_text(str(table))
        if labeled is None:
            # Fallback: pipe-join (header association is lost, but better than dropping).
            rows = []
            for tr in table.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                rows.append(" | ".join(cells))
            labeled = "\n".join(rows)
        table.replace_with("\n" + labeled + "\n")

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

        chapter, sec_num, title = _parse_chapter_section(section.heading, section.parent_heading)
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
