"""Phase 4 TDD: ordinance table parser — preserves headers + row labels.

Master spec §4 (parsing) + §13 (test_ordinance_table_parser). The fix for the
Jina-mangled-chunks problem: tables must preserve header→cell association +
classify chunk_kind (dimensional_table / use_table / parking / definition).
Tests written BEFORE implementation.
"""

from __future__ import annotations


# Fails until tables.py exists (TDD).
from plotlot.ingestion.parsing.tables import (
    ParsedTable,
    classify_table,
    parse_html_table,
    parse_markdown_table,
    TableKind,
)


class TestHtmlTableParser:
    """Master spec §4: tables preserve headers + row labels."""

    def test_preserves_headers(self):
        html = """<table><tr><th>District</th><th>Min Lot</th><th>Setback</th></tr>
        <tr><td>RS-8</td><td>6000</td><td>25</td></tr></table>"""
        t = parse_html_table(html)
        assert t is not None
        assert t.headers == ["District", "Min Lot", "Setback"]
        assert t.rows[0] == ["RS-8", "6000", "25"]

    def test_handles_td_only_tables_no_th(self):
        # Municode uses <td> for everything (no <th>) — header is in first data row.
        html = """<table><tr><td>District</td><td>Density</td></tr>
        <tr><td>RS-8</td><td>8.0</td></tr></table>"""
        t = parse_html_table(html)
        assert t is not None
        assert t.headers == ["District", "Density"]
        assert t.rows[0] == ["RS-8", "8.0"]

    def test_returns_none_for_non_table_html(self):
        assert parse_html_table("<p>not a table</p>") is None

    def test_multiple_tables_returns_first(self):
        html = "<table><tr><td>A</td></tr></table><table><tr><td>B</td></tr></table>"
        t = parse_html_table(html)
        assert t.rows[0] == ["A"]


class TestMarkdownTableParser:
    """Master spec §4: markdown tables (from codifier/Jina path) — best-effort."""

    def test_parses_markdown_table_with_separator(self):
        md = """| District | Min Lot | Density |
|---|---|---|
| RS-8 | 6000 | 8.0 |
| RS-4.4 | 10000 | 4.4 |"""
        t = parse_markdown_table(md)
        assert t is not None
        assert t.headers == ["District", "Min Lot", "Density"]
        assert len(t.rows) == 2
        assert t.rows[0] == ["RS-8", "6000", "8.0"]

    def test_returns_none_for_prose(self):
        assert parse_markdown_table("This is just a paragraph, no table here.") is None


class TestTableClassification:
    """Master spec §4/§7: classify chunk_kind (dimensional_table / use_table / etc)."""

    def test_classifies_dimensional_table(self):
        t = ParsedTable(
            headers=["District", "Min Lot Area", "Front Setback", "Density"],
            rows=[["RS-8", "6000", "25", "8.0"]],
        )
        assert classify_table(t) is TableKind.DIMENSIONAL_TABLE

    def test_classifies_use_table(self):
        t = ParsedTable(
            headers=["Use", "Permitted", "Conditional"], rows=[["Single Family", "P", ""]]
        )
        assert classify_table(t) is TableKind.USE_TABLE

    def test_classifies_parking_table(self):
        t = ParsedTable(
            headers=["Use", "Parking Spaces Required"], rows=[["Retail", "5 per 1000sf"]]
        )
        assert classify_table(t) is TableKind.PARKING

    def test_classifies_definition_table_as_narrative(self):
        # A table that's really a definition list, not dimensional.
        t = ParsedTable(headers=["Term", "Definition"], rows=[["FAR", "Floor Area Ratio"]])
        assert classify_table(t) is not TableKind.DIMENSIONAL_TABLE

    def test_does_not_flatten_ambiguous_values(self):
        # A dimensional table with "None" / multi-value cells keeps them as strings.
        t = ParsedTable(headers=["District", "Max Height"], rows=[["CC", "150 ft / 12 stories"]])
        assert classify_table(t) is TableKind.DIMENSIONAL_TABLE
        assert t.rows[0][1] == "150 ft / 12 stories"  # not flattened/split
