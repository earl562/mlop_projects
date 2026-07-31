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

# Outbound cross-reference patterns in ordinance prose. Ordinances cite other
# sections many ways: "§47-5.60", "Sec. 47-24.3", "Section 47-5.601", "pursuant
# to § 33-49". We capture the section-number token (digits, hyphens, dots) and
# normalize to a bare "47-5.60"-style key so traversal can match it against the
# OrdinanceSection.section_number index.
_CROSS_REF_RE = re.compile(
    r"(?:\u00a7|Sec\.?|Section|\xc2\xa7)\s*([\d][\d\-.]+[\d])",
    re.IGNORECASE,
)

# Section-type classification heuristics keyed off the heading + title. The
# types drive the AgenticRAG fast-path (dimensional tables skip the LLM) and
# the report's evidence provenance. Ordered: most-specific first.
_SECTION_TYPE_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "dimensional_table",
        re.compile(
            r"\b(schedule of (district )?regulations|dimensional (standards|table)|density regulations)\b",
            re.I,
        ),
    ),
    ("schedule", re.compile(r"\b(schedule|table of (permitted )?uses|fee schedule)\b", re.I)),
    ("definition", re.compile(r"\b(definitions|defined terms?)\b", re.I)),
    (
        "use_regulation",
        re.compile(
            r"\b(permitted uses?|use regulations?|use (standards|tables?)|principal uses?|accessory uses?)\b",
            re.I,
        ),
    ),
]


def _extract_cross_refs(text: str) -> list[str]:
    """Extract outbound section-number cross-references from ordinance text.

    Returns de-duplicated, sorted bare section numbers (e.g. ["47-24.3",
    "47-5.601"]). A section's own number is NOT self-referenced; callers that
    want self-exclusion can drop the section's own number afterwards.
    """
    refs: set[str] = set()
    for m in _CROSS_REF_RE.finditer(text):
        token = m.group(1).strip().rstrip(".")
        if len(token) >= 2:
            refs.add(token)
    return sorted(refs)


def _classify_section_type(heading: str, title: str, text: str) -> str:
    """Classify a section by its role in the ordinance structure.

    Heuristic over heading + title (+ first chunk of text). Returns one of:
    dimensional_table | schedule | definition | use_regulation | regulation.
    `regulation` is the catch-all default for narrative regulatory sections.
    """
    haystack = f"{heading} {title}".strip()
    if not haystack:
        haystack = text[:200]
    for type_name, pattern in _SECTION_TYPE_RULES:
        if pattern.search(haystack):
            return type_name
    return "regulation"


def _build_section_path(section: RawSection, sec_num: str, title: str) -> list[str]:
    """Build the hierarchical breadcrumb path for a section.

    Prefers an explicit `section.path` (full ancestor chain, root-first) when
    the scraper supplied one; otherwise synthesizes a 1–2 level breadcrumb from
    `parent_heading` (chapter) + the section's own heading. Empty/whitespace
    segments are dropped so the path never carries placeholder blanks.
    """
    if section.path:
        return [p.strip() for p in section.path if p and p.strip()]
    path: list[str] = []
    if section.parent_heading and section.parent_heading.strip():
        path.append(section.parent_heading.strip())
    # Use the parsed section number when available ("Sec. 47-5.60") so the path
    # leaf is a stable, matchable identifier rather than free-form prose.
    leaf = sec_num.strip() if sec_num.strip() else section.heading.strip()
    if leaf:
        path.append(leaf)
    return path


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


def _detect_header_row(records: list[list[str]]) -> int | None:
    """Find the column-header row inside a headerless table's data.

    Municode standards tables put the column names ("Minimum Lot Area", "Front",
    "Sides", "Rear", "Maximum Density") in leading <td> rows. The best header row
    is the one with the most *distinct* word labels — e.g. the "Front | Sides |
    Rear" row beats the colspan parent ("Minimum Setback Requirements" repeated)
    and the data rows (which hold values/zone codes, not words). Searches only the
    first few rows so a data row full of text descriptions isn't mistaken for it.
    """
    best_idx: int | None = None
    best_score = 1  # require at least 2 distinct word labels to count as a header
    for i, row in enumerate(records[:4]):
        labels = {c for c in row[1:] if re.search(r"[A-Za-z]{3,}", c)}
        if len(labels) > best_score:
            best_score = len(labels)
            best_idx = i
    return best_idx


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
        records = [
            [str(v).strip() for v in row] for row in frame.itertuples(index=False, name=None)
        ]

        # Municode standards tables use <td> for everything (no <th>), so pandas
        # can't detect the header and yields integer column labels (0, 1, 2…).
        # Recover the real column names ("Front", "Sides", "Minimum Lot Area") from
        # the header row embedded in the data — otherwise values get labeled "4:"
        # instead of "Front:" and the front-vs-side setback is still ambiguous.
        if cols and all(c.isdigit() for c in cols if c):
            hdr = _detect_header_row(records)
            if hdr is not None:
                cols = records[hdr]
                records = records[hdr + 1 :]

        for cells in records:
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
        path = _build_section_path(section, sec_num, title)
        cross_refs = _extract_cross_refs(text)
        section_type = _classify_section_type(section.heading, title, text)

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
                    path=path,
                    cross_refs=cross_refs,
                    section_type=section_type,
                ),
            )
            all_chunks.append(chunk)

    logger.info("Chunked %d sections into %d chunks", len(sections), len(all_chunks))
    return all_chunks
