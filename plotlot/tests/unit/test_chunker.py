"""Tests for the HTML chunker module."""

from plotlot.core.types import RawSection
from plotlot.ingestion.chunker import (
    _build_section_path,
    _classify_section_type,
    _extract_cross_refs,
    _extract_zone_codes,
    _html_to_text,
    _parse_chapter_section,
    _split_text,
    chunk_sections,
)


class TestExtractZoneCodes:
    def test_common_codes(self):
        codes = _extract_zone_codes("RS-8, RD-15, and RM-25 districts")
        assert "RS-8" in codes
        assert "RD-15" in codes
        assert "RM-25" in codes

    def test_miami_t_codes(self):
        codes = _extract_zone_codes("T6-80 and T5-O zones")
        assert "T6-80" in codes
        assert "T5-O" in codes

    def test_no_codes(self):
        codes = _extract_zone_codes("This section has no zone codes.")
        assert codes == []


class TestParseChapterSection:
    def test_standard_section(self):
        chapter, section, title = _parse_chapter_section(
            "Sec. 33-49. - Minimum lot requirements", "Chapter 33 - ZONING"
        )
        assert chapter == "Chapter 33 - ZONING"
        assert section == "Sec. 33-49."
        assert title == "Minimum lot requirements"

    def test_no_parent(self):
        chapter, section, title = _parse_chapter_section("General provisions", None)
        assert chapter == ""
        assert title == "General provisions"


class TestHtmlToText:
    def test_basic_html(self):
        text = _html_to_text("<p>Hello <b>world</b></p>")
        assert "Hello" in text
        assert "world" in text

    def test_table_conversion(self):
        html = "<table><tr><th>Zone</th><th>Setback</th></tr><tr><td>RS-8</td><td>25ft</td></tr></table>"
        text = _html_to_text(html)
        assert "RS-8" in text
        assert "25ft" in text

    def test_table_rows_are_header_labeled(self):
        """Each value must carry its column label, not just a bare pipe-joined cell."""
        html = (
            "<table>"
            "<tr><th>Zone</th><th>Min Lot Area</th><th>Front Setback</th></tr>"
            "<tr><td>R-1</td><td>10,000 s.f.</td><td>15 ft.</td></tr>"
            "</table>"
        )
        text = _html_to_text(html)
        assert "R-1 —" in text
        assert "Min Lot Area: 10,000 s.f." in text
        assert "Front Setback: 15 ft." in text

    def test_multirow_header_with_colspan_keeps_setback_columns(self):
        """The real failure: a multi-row header (colspan setbacks) must keep
        Front/Sides distinct so RO-2's 30 ft front setback is extractable."""
        html = (
            "<table>"
            "<tr><th rowspan='2'>Zone</th><th rowspan='2'>Minimum Lot Area</th>"
            "<th colspan='2'>Minimum Setback Requirements</th></tr>"
            "<tr><th>Front</th><th>Sides</th></tr>"
            "<tr><td>RO-2</td><td>20,000 s.f.</td><td>30 ft.</td><td>15 ft.</td></tr>"
            "</table>"
        )
        text = _html_to_text(html)
        assert "RO-2 —" in text
        assert "Minimum Lot Area: 20,000 s.f." in text
        assert "Front: 30 ft." in text
        assert "Sides: 15 ft." in text

    def test_td_only_header_recovered(self):
        """Municode tables use <td> for headers too (no <th>) — pandas can't detect
        the header, so the column names must be recovered from the embedded header
        row. Otherwise RO-2's values get labeled '4:' instead of 'Front:'."""
        html = (
            "<table>"
            "<tr><td>Zone</td><td>Minimum Lot Area</td><td>Front</td><td>Sides</td></tr>"
            "<tr><td>RO-2</td><td>20,000 s.f.</td><td>30 ft.</td><td>15 ft.</td></tr>"
            "<tr><td>R-2</td><td>7,500 s.f.</td><td>15 ft.</td><td>8 ft.</td></tr>"
            "</table>"
        )
        text = _html_to_text(html)
        assert "RO-2 — Minimum Lot Area: 20,000 s.f." in text
        assert "Front: 30 ft." in text
        assert "Sides: 15 ft." in text
        # The header row itself must not be emitted as a data row.
        assert "Zone — Minimum Lot Area: Front" not in text

    def test_malformed_table_falls_back(self):
        """A table pandas can't parse still yields its cell text (no crash)."""
        text = _html_to_text("<table><tr><td>R-1</td><td>data</td></tr></table>")
        assert "R-1" in text and "data" in text

    def test_empty_html(self):
        assert _html_to_text("") == ""


class TestSplitText:
    def test_short_text_no_split(self):
        parts = _split_text("Short text", max_size=100)
        assert len(parts) == 1

    def test_long_text_splits(self):
        text = "\n\n".join(
            f"Paragraph {i} with enough content to be meaningful." for i in range(50)
        )
        parts = _split_text(text, max_size=200, overlap=50)
        assert len(parts) > 1


class TestChunkSections:
    def test_basic_chunking(self):
        sections = [
            RawSection(
                municipality="Fort Lauderdale",
                county="broward",
                node_id="NODE1",
                heading="Sec. 47-5. - District regulations",
                parent_heading="Chapter 47 - ZONING",
                html_content="<p>The RS-8 district requires a minimum lot width of 75 feet and minimum lot area of 6,000 square feet.</p>",
                depth=2,
            )
        ]
        chunks = chunk_sections(sections)
        assert len(chunks) >= 1
        assert chunks[0].metadata.municipality == "Fort Lauderdale"
        assert chunks[0].metadata.county == "broward"
        assert "RS-8" in chunks[0].metadata.zone_codes

    def test_empty_sections(self):
        assert chunk_sections([]) == []

    def test_short_content_skipped(self):
        sections = [
            RawSection(
                municipality="Test",
                county="test",
                node_id="N",
                heading="Sec. 1",
                parent_heading=None,
                html_content="<p>Hi</p>",
                depth=1,
            )
        ]
        chunks = chunk_sections(sections)
        assert len(chunks) == 0


class TestExtractCrossRefs:
    """Slice 3.1: outbound section-number references power cross-ref traversal."""

    def test_section_symbol_and_sec_prefix(self):
        # \u00a7 and "Sec." both yield the same bare section number.
        refs = _extract_cross_refs("Pursuant to \u00a747-5.60 and Sec. 47-24.3.")
        assert "47-5.60" in refs
        assert "47-24.3" in refs

    def test_section_word(self):
        refs = _extract_cross_refs("see Section 33-49 for details")
        assert "33-49" in refs

    def test_dedup_and_sort(self):
        refs = _extract_cross_refs("\u00a747-5.60 and \u00a747-5.60 again")
        assert refs == ["47-5.60"]

    def test_no_refs(self):
        assert _extract_cross_refs("No references here at all.") == []

    def test_trailing_period_stripped(self):
        refs = _extract_cross_refs("per Sec. 47-5.601.")
        assert refs == ["47-5.601"]


class TestClassifySectionType:
    """Slice 3.1: section_type drives the AgenticRAG dimensional-table fast-path."""

    def test_dimensional_table_from_title(self):
        assert (
            _classify_section_type("", "Schedule of District Regulations", "")
            == "dimensional_table"
        )

    def test_dimensional_table_from_heading(self):
        assert _classify_section_type("Dimensional standards table", "", "") == "dimensional_table"

    def test_definition(self):
        assert _classify_section_type("Sec. 33-1", "Definitions", "") == "definition"

    def test_use_regulation(self):
        assert _classify_section_type("", "Permitted uses", "") == "use_regulation"

    def test_schedule(self):
        assert _classify_section_type("", "Fee schedule", "") == "schedule"

    def test_default_regulation(self):
        # Narrative regulatory section with no specific marker.
        assert _classify_section_type("Sec. 33-49", "Minimum lot requirements", "") == "regulation"


class TestBuildSectionPath:
    """Slice 3.1: path breadcrumb resolves against explicit path OR parent+heading."""

    def test_explicit_path_wins(self):
        section = RawSection(
            municipality="M",
            county="c",
            node_id="N",
            heading="Sec. 47-5.60",
            parent_heading="ignored",
            html_content="",
            depth=1,
            path=["Chapter 47", "Division 3", "Sec. 47-5.60"],
        )
        assert _build_section_path(section, "Sec. 47-5.60", "Density") == [
            "Chapter 47",
            "Division 3",
            "Sec. 47-5.60",
        ]

    def test_synthesized_from_parent_and_section(self):
        section = RawSection(
            municipality="M",
            county="c",
            node_id="N",
            heading="Sec. 33-49. - Minimum lot requirements",
            parent_heading="Chapter 33 - ZONING",
            html_content="",
            depth=2,
        )
        # sec_num (parsed) is preferred over the raw heading.
        path = _build_section_path(section, "Sec. 33-49.", "Minimum lot requirements")
        assert path == ["Chapter 33 - ZONING", "Sec. 33-49."]

    def test_no_parent(self):
        section = RawSection(
            municipality="M",
            county="c",
            node_id="N",
            heading="Sec. 1",
            parent_heading=None,
            html_content="",
            depth=1,
        )
        assert _build_section_path(section, "Sec. 1", "") == ["Sec. 1"]

    def test_blanks_dropped(self):
        section = RawSection(
            municipality="M",
            county="c",
            node_id="N",
            heading="",
            parent_heading="   ",
            html_content="",
            depth=1,
            path=["Chapter 47", "", "  ", "Sec. 47-5.60"],
        )
        assert _build_section_path(section, "Sec. 47-5.60", "") == ["Chapter 47", "Sec. 47-5.60"]


class TestChunkSectionsSlice31:
    """Slice 3.1: chunker now emits path/cross_refs/section_type per chunk."""

    def test_chunk_carries_path_and_cross_refs(self):
        sections = [
            RawSection(
                municipality="Fort Lauderdale",
                county="broward",
                node_id="NODE_DT",
                heading="Sec. 47-5.60. - Schedule of District Regulations",
                parent_heading="Chapter 47 - ZONING",
                html_content=(
                    "<p>For RS-8 districts, see \u00a747-24.3 for uses. "
                    "Minimum lot area 6,000 sq ft.</p>"
                ),
                depth=2,
            )
        ]
        chunks = chunk_sections(sections)
        assert len(chunks) == 1
        meta = chunks[0].metadata
        assert meta.section_type == "dimensional_table"
        assert "47-24.3" in meta.cross_refs
        assert meta.path[:1] == ["Chapter 47 - ZONING"]

    def test_all_chunks_of_a_section_share_section_metadata(self):
        # A section whose text exceeds MAX_CHUNK_SIZE fans out to >1 chunk; all
        # share path/cross_refs/section_type (the section is the structural unit).
        # Use two <p> paragraphs separated by a blank line so the splitter
        # splits at the paragraph boundary (single-paragraph text stays one chunk).
        sentence = "See \u00a747-24.3 for permitted uses in RS-8 districts. " * 100
        long_body = f"<p>{sentence}</p>\n<p>{sentence}</p>"
        sections = [
            RawSection(
                municipality="M",
                county="c",
                node_id="N",
                heading="Sec. 47-5.60. - Schedule of District Regulations",
                parent_heading="Chapter 47",
                html_content=long_body,
                depth=2,
            )
        ]
        chunks = chunk_sections(sections)
        assert len(chunks) > 1
        for c in chunks:
            assert c.metadata.section_type == "dimensional_table"
            assert c.metadata.path == chunks[0].metadata.path
            assert c.metadata.cross_refs == chunks[0].metadata.cross_refs
