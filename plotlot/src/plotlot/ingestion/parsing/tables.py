"""Ordinance table parser — preserves headers + row labels (Phase 4, master spec §4).

The fix for the Jina-mangled-chunks problem: tables preserve header→cell
association (no flattening) + classify chunk_kind (dimensional_table / use_table /
parking / definition / narrative). Works on both HTML tables (from native scraper)
and markdown tables (from codifier/Jina path — best-effort recovery).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from bs4 import BeautifulSoup


class TableKind(str, Enum):
    """Master spec §7 chunk_kind classification."""

    DIMENSIONAL_TABLE = "dimensional_table"
    USE_TABLE = "use_table"
    PARKING = "parking"
    DEFINITION = "definition"
    NARRATIVE = "narrative"  # not a table at all
    UNKNOWN = "unknown"


@dataclass
class ParsedTable:
    headers: list[str]
    rows: list[list[str]]
    kind: TableKind | None = None
    metadata: dict = field(default_factory=dict)


# ── HTML table parsing ──────────────────────────────────────────────────────


def parse_html_table(html: str) -> ParsedTable | None:
    """Parse the first <table> in HTML, preserving headers + rows.

    Handles Municode's <td>-only tables (no <th>) by treating the first row
    with word-labels as the header. Returns None if no table present.
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table is None:
        return None
    rows_raw = table.find_all("tr")
    if not rows_raw:
        return None
    parsed_rows: list[list[str]] = []
    for tr in rows_raw:
        cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
        if any(cells):  # skip empty rows
            parsed_rows.append(cells)

    if not parsed_rows:
        return None

    # Determine header: first row if it's all word-labels (non-numeric).
    first = parsed_rows[0]
    looks_like_header = any(re.search(r"[A-Za-z]{3,}", c) for c in first) and len(first) >= 2
    if looks_like_header:
        headers = first
        rows = parsed_rows[1:]
    else:
        # No header row (data starts immediately) — synthesize column labels.
        headers = [f"col_{i}" for i in range(len(first))]
        rows = parsed_rows
    return ParsedTable(headers=headers, rows=rows)


# ── Markdown table parsing (codifier/Jina path — best-effort recovery) ──────

_MD_SEP_RE = re.compile(r"^\s*\|?[\s:|-]+\|?\s*$")


def parse_markdown_table(text: str) -> ParsedTable | None:
    """Best-effort parse of a markdown table (| col | col | with |---| separator).

    Returns None if the text isn't a markdown table (prose, no separator, etc.).
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # find a header row + separator pair
    for i, ln in enumerate(lines):
        if "|" not in ln:
            continue
        if i + 1 < len(lines) and _MD_SEP_RE.match(lines[i + 1]):
            headers = [c.strip() for c in ln.strip("|").split("|")]
            rows: list[list[str]] = []
            for rl in lines[i + 2 :]:
                if "|" not in rl:
                    break
                cells = [c.strip() for c in rl.strip("|").split("|")]
                if any(cells):
                    rows.append(cells)
            if headers and rows:
                return ParsedTable(headers=headers, rows=rows)
    return None


# ── Table classification (master spec §7 chunk_kind) ────────────────────────

_DIMENSIONAL_KEYWORDS = (
    "setback",
    "yard",
    "lot area",
    "lot size",
    "lot width",
    "density",
    "height",
    "floor area",
    "far",
    "coverage",
    "stories",
)
_USE_KEYWORDS = (
    "permitted use",
    "conditional use",
    "principal use",
    "accessory use",
    "use regulations",
    "prohibited",
    "permitted",
    "conditional",
)
_PARKING_KEYWORDS = ("parking", "loading", "spaces required", "vehicle")
_DEFINITION_KEYWORDS = ("definition", "defined terms", "term", "meaning")


def classify_table(table: ParsedTable) -> TableKind:
    """Classify a table by its headers + content (master spec §7 chunk_kind)."""
    header_blob = " ".join(h.lower() for h in table.headers)
    sample = " ".join(table.rows[0]).lower() if table.rows else ""

    # Dimensional: has setback/lot/density/FAR/height/coverage headers.
    if any(k in header_blob for k in _DIMENSIONAL_KEYWORDS):
        return TableKind.DIMENSIONAL_TABLE
    # Parking.
    if any(k in header_blob for k in _PARKING_KEYWORDS):
        return TableKind.PARKING
    # Use table.
    if any(k in header_blob for k in _USE_KEYWORDS):
        return TableKind.USE_TABLE
    # Definition.
    if any(k in header_blob for k in _DEFINITION_KEYWORDS):
        return TableKind.DEFINITION
    # Fall back: scan a sample data row for dimensional content.
    if any(k in sample for k in _DIMENSIONAL_KEYWORDS):
        return TableKind.DIMENSIONAL_TABLE
    return TableKind.UNKNOWN


__all__ = ["ParsedTable", "TableKind", "classify_table", "parse_html_table", "parse_markdown_table"]
