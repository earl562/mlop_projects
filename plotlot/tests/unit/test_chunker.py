"""Tests for the HTML chunker module."""


from plotlot.core.types import RawSection
from plotlot.ingestion.chunker import (
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

    def test_empty_html(self):
        assert _html_to_text("") == ""


class TestSplitText:
    def test_short_text_no_split(self):
        parts = _split_text("Short text", max_size=100)
        assert len(parts) == 1

    def test_long_text_splits(self):
        text = "\n\n".join(f"Paragraph {i} with enough content to be meaningful." for i in range(50))
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
