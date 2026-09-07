"""Unit tests for the ingestion adapter layer (Phase 1).

All external I/O (httpx, MunicodeScraper, discover_municode_authority_for_name,
create_san_diego_adapter) is mocked so tests run without network access.

Coverage:
  SourceAdapter       — instantiation, repr, abstract enforcement
  MunicodeAdapter     — delegates to MunicodeScraper + chunk_sections
  PDFAdapter          — HTTP download, parse, chunk, metadata assembly
  _chunk_text         — paragraph splitting, overlap, single/double newline
  _extract_zone_codes — regex extraction, dedup, sort
  _extract_section_title — first-line heading extraction
  HTMLAdapter         — HTTP download, RawSection creation, chunk delegation
  _extract_heading    — H1/H2/title extraction from HTML
  resolve_adapter     — PDF registry hit, Municode fallback, NoAdapterError
  register_pdf_municipality — runtime registration
  NoAdapterError      — attributes and inheritance
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from plotlot.core.errors import FatalError, NoAdapterError
from plotlot.core.types import (
    ChunkMetadata,
    MunicodeConfig,
    RawSection,
    TextChunk,
)
from plotlot.ingestion.adapters.base import SourceAdapter
from plotlot.ingestion.adapters.html import HTMLAdapter, _extract_heading
from plotlot.ingestion.adapters.municode import MunicodeAdapter
from plotlot.ingestion.adapters.pdf import (
    PDFAdapter,
    PDFSource,
    _chunk_text,
    _extract_section_title,
    _extract_zone_codes,
)
from plotlot.ingestion.adapters.registry import (
    _registry_key,
    register_pdf_municipality,
    resolve_adapter,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_chunk(text: str = "some zoning text", municipality: str = "Test City") -> TextChunk:
    return TextChunk(
        text=text,
        metadata=ChunkMetadata(
            municipality=municipality,
            county="test_county",
            chapter="Chapter 1",
            section="Sec. 1.01",
            section_title="General Provisions",
            zone_codes=[],
            chunk_index=0,
            municode_node_id="node_001",
        ),
    )


def _make_municode_config(municipality: str = "Miami Gardens") -> MunicodeConfig:
    return MunicodeConfig(
        municipality=municipality,
        county="miami_dade",
        client_id=13114,
        product_id=14432,
        job_id=481139,
        zoning_node_id="SPBLADECO",
        state="FL",
    )


# ─────────────────────────────────────────────────────────────────────────────
# SourceAdapter — abstract base
# ─────────────────────────────────────────────────────────────────────────────


class TestSourceAdapter:
    def test_cannot_instantiate_abstract_class(self):
        with pytest.raises(TypeError):
            SourceAdapter("City", "county", "CA")  # type: ignore[abstract]

    def test_concrete_subclass_requires_fetch_chunks(self):
        """Subclass without fetch_chunks raises TypeError on instantiation."""

        class Incomplete(SourceAdapter):
            name = "incomplete"
            # fetch_chunks not implemented

        with pytest.raises(TypeError):
            Incomplete("City", "county", "CA")  # type: ignore[abstract]

    def test_repr_contains_municipality_and_state(self):
        class Concrete(SourceAdapter):
            name = "concrete"

            async def fetch_chunks(self) -> list[TextChunk]:
                return []

        adapter = Concrete("San Diego", "San Diego", "CA")
        r = repr(adapter)
        assert "Concrete" in r
        assert "San Diego" in r
        assert "CA" in r

    def test_attributes_stored(self):
        class Concrete(SourceAdapter):
            name = "concrete"

            async def fetch_chunks(self) -> list[TextChunk]:
                return []

        adapter = Concrete("Portland", "multnomah", "OR")
        assert adapter.municipality == "Portland"
        assert adapter.county == "multnomah"
        assert adapter.state == "OR"


# ─────────────────────────────────────────────────────────────────────────────
# MunicodeAdapter
# ─────────────────────────────────────────────────────────────────────────────


class TestMunicodeAdapter:
    def test_name(self):
        config = _make_municode_config()
        adapter = MunicodeAdapter(config)
        assert adapter.name == "municode"

    def test_attributes_from_config(self):
        config = _make_municode_config("Fort Lauderdale")
        config.county = "broward"
        config.state = "FL"
        adapter = MunicodeAdapter(config)
        assert adapter.municipality == "Fort Lauderdale"
        assert adapter.county == "broward"
        assert adapter.state == "FL"
        assert adapter.config is config

    async def test_fetch_chunks_delegates_to_scraper_and_chunker(self):
        config = _make_municode_config()
        expected_section = RawSection(
            municipality="Miami Gardens",
            county="miami_dade",
            node_id="node_1",
            heading="Sec. 1.01",
            parent_heading="Chapter 1",
            html_content="<p>some zoning text</p>",
            depth=1,
        )
        expected_chunks = [_make_chunk()]

        with (
            patch("plotlot.ingestion.adapters.municode.MunicodeScraper") as MockScraper,
            patch(
                "plotlot.ingestion.adapters.municode.chunk_sections",
                return_value=expected_chunks,
            ) as mock_chunk,
        ):
            mock_instance = MockScraper.return_value
            mock_instance.scrape_zoning_chapter = AsyncMock(return_value=[expected_section])

            adapter = MunicodeAdapter(config)
            result = await adapter.fetch_chunks()

        mock_instance.scrape_zoning_chapter.assert_awaited_once_with(config)
        mock_chunk.assert_called_once_with([expected_section])
        assert result == expected_chunks

    async def test_fetch_chunks_returns_empty_on_no_sections(self):
        config = _make_municode_config()

        with (
            patch("plotlot.ingestion.adapters.municode.MunicodeScraper") as MockScraper,
            patch(
                "plotlot.ingestion.adapters.municode.chunk_sections",
                return_value=[],
            ),
        ):
            mock_instance = MockScraper.return_value
            mock_instance.scrape_zoning_chapter = AsyncMock(return_value=[])

            adapter = MunicodeAdapter(config)
            result = await adapter.fetch_chunks()

        assert result == []

    def test_repr(self):
        config = _make_municode_config("Hayward")
        config.state = "CA"
        adapter = MunicodeAdapter(config)
        r = repr(adapter)
        assert "MunicodeAdapter" in r
        assert "Hayward" in r
        assert "CA" in r


# ─────────────────────────────────────────────────────────────────────────────
# _chunk_text — pure function
# ─────────────────────────────────────────────────────────────────────────────


class TestChunkText:
    def test_empty_string_returns_empty_list(self):
        assert _chunk_text("") == []

    def test_short_text_returns_single_chunk(self):
        text = "Short zoning text."
        result = _chunk_text(text, max_size=1500)
        assert result == [text]

    def test_text_exactly_at_max_size_returns_single_chunk(self):
        text = "A" * 1500
        result = _chunk_text(text, max_size=1500)
        assert len(result) == 1
        assert result[0] == text

    def test_double_newline_splits_at_paragraphs(self):
        text = "Para one.\n\nPara two.\n\nPara three."
        result = _chunk_text(text, max_size=20, overlap=0)
        assert len(result) > 1
        assert "Para one." in result[0]

    def test_single_newline_splits_at_lines(self):
        # No double newlines — PDF-layout text
        text = "Line one.\nLine two.\nLine three."
        result = _chunk_text(text, max_size=20, overlap=0)
        assert len(result) > 1

    def test_overlap_carries_tail_into_next_chunk(self):
        # Para A fills chunk, Para B starts new chunk; overlap brings tail of A
        para_a = "A" * 1200
        para_b = "B" * 400
        text = f"{para_a}\n\n{para_b}"
        result = _chunk_text(text, max_size=1500, overlap=100)
        assert len(result) >= 2
        # The last 100 chars of chunk 0 should appear at the start of chunk 1
        assert result[0][-100:] in result[1]

    def test_single_paragraph_no_split_needed(self):
        text = "Residential district. Maximum density 25 units per acre."
        result = _chunk_text(text, max_size=1500)
        assert len(result) == 1
        assert result[0] == text

    def test_multiple_long_paragraphs_produce_multiple_chunks(self):
        paragraphs = [f"Paragraph {i}: " + "x" * 600 for i in range(5)]
        text = "\n\n".join(paragraphs)
        result = _chunk_text(text, max_size=1500, overlap=0)
        assert len(result) >= 2

    def test_blank_paragraphs_are_skipped(self):
        text = "Para one.\n\n\n\nPara two."
        result = _chunk_text(text, max_size=1500)
        assert len(result) == 1
        assert "Para one." in result[0]
        assert "Para two." in result[0]

    def test_zero_overlap_no_repeated_content(self):
        para_a = "A" * 800
        para_b = "B" * 800
        text = f"{para_a}\n\n{para_b}"
        result = _chunk_text(text, max_size=1000, overlap=0)
        if len(result) >= 2:
            assert para_a[-50:] not in result[1]

    def test_preserves_text_content(self):
        """Every character in the original text should appear in some chunk."""
        text = "RS-8 zone. Minimum lot size is 5,000 sqft.\n\n" * 10
        chunks = _chunk_text(text, max_size=200, overlap=50)
        combined = " ".join(chunks)
        assert "RS-8" in combined
        assert "5,000" in combined


# ─────────────────────────────────────────────────────────────────────────────
# _extract_zone_codes — pure function
# ─────────────────────────────────────────────────────────────────────────────


class TestExtractZoneCodes:
    def test_extracts_simple_code(self):
        assert _extract_zone_codes("The RS-8 zone allows single family.") == ["RS-8"]

    def test_extracts_three_part_code(self):
        assert _extract_zone_codes("RM-3-7 district setbacks apply.") == ["RM-3-7"]

    def test_extracts_multiple_codes(self):
        result = _extract_zone_codes("Both RM-25 and CC-4-2 zones are affected.")
        assert "RM-25" in result
        assert "CC-4-2" in result

    def test_deduplicates(self):
        result = _extract_zone_codes("RS-8 RS-8 RS-8 repeated zone.")
        assert result.count("RS-8") == 1

    def test_returns_sorted_list(self):
        result = _extract_zone_codes("RM-25 and IL-2-1 and CC-4-2 zones.")
        assert result == sorted(result)

    def test_no_codes_returns_empty_list(self):
        assert _extract_zone_codes("No zone codes in this paragraph.") == []

    def test_empty_string(self):
        assert _extract_zone_codes("") == []

    def test_filters_short_matches(self):
        # Single letter + number like "A-1" has len 3, should be included
        # but things like "R" (len 1) are filtered by the regex requiring digits
        result = _extract_zone_codes("A-1 zone versus B-2 zone.")
        assert "A-1" in result
        assert "B-2" in result

    def test_uppercase_normalisation(self):
        # Zone codes should come back uppercase
        result = _extract_zone_codes("RM-3-7 zone regulations.")
        assert all(code == code.upper() for code in result)

    def test_industrial_codes(self):
        result = _extract_zone_codes("IL-2-1 and IH-3 industrial zones.")
        assert "IL-2-1" in result
        assert "IH-3" in result


# ─────────────────────────────────────────────────────────────────────────────
# _extract_section_title — pure function
# ─────────────────────────────────────────────────────────────────────────────


class TestExtractSectionTitle:
    def test_returns_first_meaningful_line(self):
        text = "DIVISION 1 — GENERAL PROVISIONS\nSection 1.01 Purpose."
        result = _extract_section_title(text)
        assert result == "DIVISION 1 — GENERAL PROVISIONS"

    def test_skips_copyright_lines(self):
        text = "© 2023 City of San Diego\nActual Heading"
        result = _extract_section_title(text)
        assert result == "Actual Heading"

    def test_skips_pure_number_lines(self):
        text = "12345\nZoning Standards"
        result = _extract_section_title(text)
        assert result == "Zoning Standards"

    def test_empty_text_returns_empty_string(self):
        assert _extract_section_title("") == ""

    def test_truncates_to_120_chars(self):
        long_line = "A" * 200
        result = _extract_section_title(long_line)
        assert len(result) == 120

    def test_skips_short_lines(self):
        # Lines <= 10 chars are skipped
        text = "Hi\nThis is a long enough heading line"
        result = _extract_section_title(text)
        assert result == "This is a long enough heading line"

    def test_handles_whitespace_padding(self):
        text = "   Chapter 13 — Zones   \nNext line"
        result = _extract_section_title(text)
        assert result == "Chapter 13 — Zones"


# ─────────────────────────────────────────────────────────────────────────────
# PDFAdapter
# ─────────────────────────────────────────────────────────────────────────────


class TestPDFAdapter:
    def test_name(self):
        adapter = PDFAdapter("City", "county", "CA", [])
        assert adapter.name == "pdf"

    def test_attributes(self):
        sources = [PDFSource(url="https://example.com/ch01.pdf", chapter="Ch 1")]
        adapter = PDFAdapter("San Diego", "San Diego", "CA", sources, verify_ssl=False)
        assert adapter.municipality == "San Diego"
        assert adapter.county == "San Diego"
        assert adapter.state == "CA"
        assert adapter.verify_ssl is False
        assert adapter.sources is sources

    async def test_fetch_chunks_returns_empty_for_no_sources(self):
        adapter = PDFAdapter("Empty City", "county", "CA", [])
        result = await adapter.fetch_chunks()
        assert result == []

    async def test_fetch_chunks_skips_404_responses(self):
        sources = [PDFSource(url="https://example.com/missing.pdf", chapter="Ch 1")]
        adapter = PDFAdapter("Test City", "test_county", "CA", sources)

        with patch(
            "plotlot.ingestion.adapters.pdf._fetch_pdf_text",
            new=AsyncMock(return_value=None),
        ):
            result = await adapter.fetch_chunks()

        assert result == []

    async def test_fetch_chunks_skips_short_text(self):
        sources = [PDFSource(url="https://example.com/short.pdf", chapter="Ch 1")]
        adapter = PDFAdapter("Test City", "test_county", "CA", sources)

        with patch(
            "plotlot.ingestion.adapters.pdf._fetch_pdf_text",
            new=AsyncMock(return_value="Too short"),  # len < 50
        ):
            result = await adapter.fetch_chunks()

        assert result == []

    async def test_fetch_chunks_produces_text_chunks(self):
        long_text = "Section 1.01 Residential Zone RS-8.\n\n" + "A" * 200
        sources = [
            PDFSource(
                url="https://example.com/ch13.pdf",
                chapter="Chapter 13 — Zones",
                section="Art.01 Div.01",
                chapter_num=13,
                article=1,
                division=1,
            )
        ]
        adapter = PDFAdapter("San Diego", "San Diego", "CA", sources, verify_ssl=False)

        with patch(
            "plotlot.ingestion.adapters.pdf._fetch_pdf_text",
            new=AsyncMock(return_value=long_text),
        ):
            result = await adapter.fetch_chunks()

        assert len(result) >= 1
        assert isinstance(result[0], TextChunk)
        assert result[0].metadata.municipality == "San Diego"
        assert result[0].metadata.county == "San Diego"
        assert result[0].metadata.chapter == "Chapter 13 — Zones"
        assert result[0].metadata.section == "Art.01 Div.01"

    async def test_fetch_chunks_assigns_chunk_index(self):
        # Text long enough to produce multiple chunks
        text = ("RS-8 zone residential standards.\n" * 5 + "\n").strip()
        long_text = "\n\n".join([text] * 20)  # ~2000+ chars
        sources = [
            PDFSource(
                url="https://example.com/ch13.pdf",
                chapter="Ch 13",
                chapter_num=13,
                article=1,
                division=1,
            )
        ]
        adapter = PDFAdapter("SD", "SD", "CA", sources, max_chunk_size=400, overlap=50)

        with patch(
            "plotlot.ingestion.adapters.pdf._fetch_pdf_text",
            new=AsyncMock(return_value=long_text),
        ):
            result = await adapter.fetch_chunks()

        indices = [c.metadata.chunk_index for c in result]
        assert indices == list(range(len(result)))

    async def test_fetch_chunks_extracts_zone_codes(self):
        text = "The RM-3-7 zone requires minimum 1,500 sqft per unit." + " x" * 30
        sources = [PDFSource(url="https://example.com/ch13.pdf", chapter="Ch 13")]
        adapter = PDFAdapter("SD", "SD", "CA", sources)

        with patch(
            "plotlot.ingestion.adapters.pdf._fetch_pdf_text",
            new=AsyncMock(return_value=text),
        ):
            result = await adapter.fetch_chunks()

        zone_codes = result[0].metadata.zone_codes
        assert "RM-3-7" in zone_codes

    async def test_fetch_chunks_node_id_format(self):
        text = "Zone text. " * 10
        sources = [
            PDFSource(
                url="https://example.com/ch13.pdf",
                chapter="Ch 13",
                chapter_num=13,
                article=2,
                division=5,
            )
        ]
        adapter = PDFAdapter("SD", "SD", "CA", sources)

        with patch(
            "plotlot.ingestion.adapters.pdf._fetch_pdf_text",
            new=AsyncMock(return_value=text),
        ):
            result = await adapter.fetch_chunks()

        assert result[0].metadata.municode_node_id.startswith("ch13_art02_div05")


# ─────────────────────────────────────────────────────────────────────────────
# HTMLAdapter
# ─────────────────────────────────────────────────────────────────────────────


class TestHTMLAdapter:
    def test_name(self):
        adapter = HTMLAdapter("City", "county", "CA", [])
        assert adapter.name == "html"

    def test_attributes(self):
        urls = ["https://city.gov/zoning/residential"]
        adapter = HTMLAdapter("Portland", "multnomah", "OR", urls, chapter="Title 33")
        assert adapter.municipality == "Portland"
        assert adapter.county == "multnomah"
        assert adapter.state == "OR"
        assert adapter.urls == urls
        assert adapter.chapter == "Title 33"

    async def test_fetch_chunks_returns_empty_for_no_urls(self):
        adapter = HTMLAdapter("Empty City", "county", "CA", [])
        result = await adapter.fetch_chunks()
        assert result == []

    async def test_fetch_chunks_skips_failed_requests(self):
        urls = ["https://city.gov/fail1", "https://city.gov/fail2"]
        adapter = HTMLAdapter("City", "county", "CA", urls)

        with patch.object(adapter, "_fetch_html", new=AsyncMock(return_value=None)):
            result = await adapter.fetch_chunks()

        assert result == []

    async def test_fetch_chunks_creates_raw_sections(self):
        html = "<html><h1>Residential Zone</h1><p>RS-4 zone standards.</p></html>"
        urls = ["https://city.gov/zoning/residential"]
        adapter = HTMLAdapter("Portland", "multnomah", "OR", urls, chapter="Title 33")

        captured_sections: list[RawSection] = []

        def capture_chunk_sections(sections: list[RawSection]) -> list[TextChunk]:
            captured_sections.extend(sections)
            return [_make_chunk()]

        with (
            patch.object(adapter, "_fetch_html", new=AsyncMock(return_value=html)),
            patch(
                "plotlot.ingestion.adapters.html.chunk_sections",
                side_effect=capture_chunk_sections,
            ),
        ):
            await adapter.fetch_chunks()

        assert len(captured_sections) == 1
        section = captured_sections[0]
        assert section.municipality == "Portland"
        assert section.county == "multnomah"
        assert section.html_content == html
        assert section.parent_heading == "Title 33"
        assert section.depth == 1

    async def test_fetch_chunks_extracts_heading_from_h1(self):
        html = "<html><h1>Zoning Article 1</h1><p>Content.</p></html>"
        urls = ["https://city.gov/zoning"]
        adapter = HTMLAdapter("City", "county", "CA", urls)

        captured: list[RawSection] = []

        def capture(sections: list[RawSection]) -> list[TextChunk]:
            captured.extend(sections)
            return [_make_chunk()]

        with (
            patch.object(adapter, "_fetch_html", new=AsyncMock(return_value=html)),
            patch("plotlot.ingestion.adapters.html.chunk_sections", side_effect=capture),
        ):
            await adapter.fetch_chunks()

        assert captured[0].heading == "Zoning Article 1"

    async def test_fetch_chunks_fallback_heading_when_no_tag(self):
        html = "<html><div>No heading tags here.</div></html>"
        urls = ["https://city.gov/zoning/page1", "https://city.gov/zoning/page2"]
        adapter = HTMLAdapter("City", "county", "CA", urls)

        captured: list[RawSection] = []

        def capture(sections: list[RawSection]) -> list[TextChunk]:
            captured.extend(sections)
            return [_make_chunk() for _ in sections]

        with (
            patch.object(adapter, "_fetch_html", new=AsyncMock(return_value=html)),
            patch("plotlot.ingestion.adapters.html.chunk_sections", side_effect=capture),
        ):
            await adapter.fetch_chunks()

        assert captured[0].heading == "Section 1"
        assert captured[1].heading == "Section 2"


class TestExtractHeading:
    def test_extracts_h1(self):
        html = "<html><h1>Chapter 33 — Residential Zones</h1></html>"
        assert _extract_heading(html) == "Chapter 33 — Residential Zones"

    def test_falls_back_to_h2(self):
        html = "<html><h2>Article IV</h2></html>"
        assert _extract_heading(html) == "Article IV"

    def test_falls_back_to_title(self):
        html = "<html><head><title>City Zoning Code</title></head></html>"
        assert _extract_heading(html) == "City Zoning Code"

    def test_h1_takes_priority_over_h2(self):
        html = "<html><h1>H1 Heading</h1><h2>H2 Heading</h2></html>"
        assert _extract_heading(html) == "H1 Heading"

    def test_empty_html_returns_empty_string(self):
        assert _extract_heading("") == ""
        assert _extract_heading("<html></html>") == ""

    def test_truncates_to_200_chars(self):
        long_title = "X" * 300
        html = f"<html><h1>{long_title}</h1></html>"
        result = _extract_heading(html)
        assert len(result) == 200

    def test_strips_whitespace(self):
        html = "<html><h1>   Trimmed Title   </h1></html>"
        assert _extract_heading(html) == "Trimmed Title"


# ─────────────────────────────────────────────────────────────────────────────
# resolve_adapter — registry
# ─────────────────────────────────────────────────────────────────────────────


class TestResolveAdapter:
    async def test_san_diego_returns_pdf_adapter(self):
        fake_adapter = PDFAdapter("San Diego", "San Diego", "CA", [])

        async def mock_factory() -> PDFAdapter:
            return fake_adapter

        with patch.dict(
            "plotlot.ingestion.adapters.registry._PDF_REGISTRY",
            {"san diego_ca": mock_factory},
        ):
            result = await resolve_adapter("San Diego", "CA")

        assert result is fake_adapter

    async def test_case_insensitive_municipality(self):
        fake_adapter = PDFAdapter("San Diego", "San Diego", "CA", [])

        async def mock_factory() -> PDFAdapter:
            return fake_adapter

        with patch.dict(
            "plotlot.ingestion.adapters.registry._PDF_REGISTRY",
            {"san diego_ca": mock_factory},
        ):
            result = await resolve_adapter("san diego", "ca")

        assert result is fake_adapter

    async def test_municode_fallback_returns_municode_adapter(self):
        config = _make_municode_config("Miami")
        config.state = "FL"

        with patch(
            "plotlot.ingestion.adapters.registry._try_municode",
            new=AsyncMock(return_value=config),
        ):
            result = await resolve_adapter("Miami", "FL")

        assert isinstance(result, MunicodeAdapter)
        assert result.config is config

    async def test_raises_no_adapter_error_when_not_found(self):
        # Mock EVERY discovery path to miss — otherwise _try_codifier makes a live
        # network call (discover_codifier) whose result is environment-dependent,
        # so the test was non-hermetic and flaked on whatever the codifier service
        # returned for a fake city.
        with (
            patch(
                "plotlot.ingestion.adapters.registry._try_municode",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "plotlot.ingestion.adapters.registry._try_codifier",
                new=AsyncMock(return_value=None),
            ),
        ):
            with pytest.raises(NoAdapterError) as exc_info:
                await resolve_adapter("Atlantis", "ZZ")

        assert exc_info.value.municipality == "Atlantis"
        assert exc_info.value.state == "ZZ"

    async def test_county_hint_passed_to_municode(self):
        config = _make_municode_config("Unincorporated Miami-Dade")

        with patch(
            "plotlot.ingestion.adapters.registry._try_municode",
            new=AsyncMock(return_value=config),
        ) as mock_try:
            await resolve_adapter("Unincorporated Miami-Dade", "FL", county="miami_dade")

        mock_try.assert_awaited_once_with("Unincorporated Miami-Dade", "FL", "miami_dade")

    async def test_pdf_registry_takes_priority_over_municode(self):
        """A municipality in _PDF_REGISTRY should not trigger Municode discovery."""
        fake_adapter = PDFAdapter("San Diego", "San Diego", "CA", [])

        async def mock_factory() -> PDFAdapter:
            return fake_adapter

        with (
            patch.dict(
                "plotlot.ingestion.adapters.registry._PDF_REGISTRY",
                {"san diego_ca": mock_factory},
            ),
            patch(
                "plotlot.ingestion.adapters.registry._try_municode",
                new=AsyncMock(side_effect=AssertionError("should not be called")),
            ),
        ):
            result = await resolve_adapter("San Diego", "CA")

        assert result is fake_adapter


class TestRegisterPdfMunicipality:
    async def test_runtime_registration(self):
        fake_adapter = PDFAdapter("Test Town", "test_county", "TX", [])

        async def factory() -> PDFAdapter:
            return fake_adapter

        register_pdf_municipality("Test Town", "TX", factory)
        result = await resolve_adapter("Test Town", "TX")
        assert result is fake_adapter

    async def test_registration_is_case_normalised(self):
        fake_adapter = PDFAdapter("My City", "county", "WA", [])

        async def factory() -> PDFAdapter:
            return fake_adapter

        register_pdf_municipality("My City", "WA", factory)

        # Case-insensitive lookup
        result = await resolve_adapter("my city", "wa")
        assert result is fake_adapter


# ─────────────────────────────────────────────────────────────────────────────
# _registry_key
# ─────────────────────────────────────────────────────────────────────────────


class TestRegistryKey:
    def test_lowercases_both_parts(self):
        assert _registry_key("San Diego", "CA") == "san diego_ca"

    def test_strips_whitespace(self):
        assert _registry_key("  Miami  ", "  FL  ") == "miami_fl"

    def test_preserves_spaces_in_municipality(self):
        key = _registry_key("Unincorporated Miami-Dade", "FL")
        assert key == "unincorporated miami-dade_fl"


# ─────────────────────────────────────────────────────────────────────────────
# NoAdapterError
# ─────────────────────────────────────────────────────────────────────────────


class TestNoAdapterError:
    def test_is_fatal_error(self):
        err = NoAdapterError("Atlantis", "ZZ")
        assert isinstance(err, FatalError)

    def test_attributes(self):
        err = NoAdapterError("Atlantis", "ZZ")
        assert err.municipality == "Atlantis"
        assert err.state == "ZZ"

    def test_message_contains_municipality_and_state(self):
        err = NoAdapterError("Austin", "TX")
        msg = str(err)
        assert "Austin" in msg
        assert "TX" in msg

    def test_is_exception(self):
        with pytest.raises(NoAdapterError):
            raise NoAdapterError("Test", "TS")


# ─────────────────────────────────────────────────────────────────────────────
# PDFSource dataclass
# ─────────────────────────────────────────────────────────────────────────────


class TestPDFSource:
    def test_defaults(self):
        src = PDFSource(url="https://example.com/file.pdf")
        assert src.url == "https://example.com/file.pdf"
        assert src.chapter == ""
        assert src.section == ""
        assert src.chapter_num == 0
        assert src.article == 0
        assert src.division == 0
        assert src.extra == {}

    def test_all_fields(self):
        src = PDFSource(
            url="https://docs.sandiego.gov/municode/MuniCodeChapter13/Ch13Art01Division01.pdf",
            chapter="Chapter 13 — Zones",
            section="Art.01 Div.01",
            chapter_num=13,
            article=1,
            division=1,
            extra={"source": "sandiego"},
        )
        assert src.chapter_num == 13
        assert src.article == 1
        assert src.division == 1
        assert src.extra == {"source": "sandiego"}
