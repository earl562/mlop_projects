from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from plotlot.core.types import ChunkMetadata, MunicodeConfig, TextChunk
from plotlot.ingestion.adapters.base import SourceAdapter
from plotlot.ingestion.adapters.html import HTMLAdapter
from plotlot.ingestion.adapters.municode import MunicodeAdapter
from plotlot.ingestion.adapters.pdf import PDFAdapter, PDFSource
from plotlot.pipeline.lookup_snapshot_source_quality import (
    SourceMetadataQualityInput,
    score_source_metadata,
)


def _chunk(text: str = "zoning text") -> TextChunk:
    return TextChunk(
        text=text,
        metadata=ChunkMetadata(
            municipality="Miramar",
            county="broward",
            chapter="Chapter 1",
            section="Sec. 1",
            section_title="Dimensional Standards",
            zone_codes=[],
            chunk_index=0,
            municode_node_id="node_1",
        ),
    )


class _MinimalAdapter(SourceAdapter):
    name = "minimal"

    async def fetch_chunks(self) -> list[TextChunk]:
        return [_chunk()]


async def test_source_adapter_result_flags_missing_source_url() -> None:
    # Given: an adapter that can produce chunks but has no source descriptor.
    adapter = _MinimalAdapter("Miramar", "broward", "FL")

    # When: the adapter is asked for a replayable ingestion result.
    result = await adapter.fetch_ingestion_result()

    # Then: chunks are preserved and source quality is explicitly blocked.
    assert result.adapter_name == "minimal"
    assert result.chunks == (_chunk(),)
    assert result.quality_score == 0.0
    assert result.source_records[0].quality_flags == (
        "unaccepted_source_authority",
        "missing_source_url",
        "missing_effective_date",
    )


async def test_source_adapter_result_blocks_unknown_authority() -> None:
    # Given: a custom adapter cannot classify its source authority.
    adapter = _MinimalAdapter("Miramar", "broward", "FL")

    # When: the adapter is asked for a replayable ingestion result.
    result = await adapter.fetch_ingestion_result()

    # Then: unknown authority keeps the source below display-ready quality.
    record = result.source_records[0]
    assert record.source_authority == "unknown"
    assert "unaccepted_source_authority" in record.quality_flags
    assert record.quality_score == 0.0


def test_source_quality_blocks_unknown_authority_even_with_complete_metadata() -> None:
    # Given: source metadata is complete except for accepted authority classification.
    metadata_quality = score_source_metadata(
        SourceMetadataQualityInput(
            source_url="https://example.com/zoning",
            source_authority="unknown",
            retrieved_at="2026-06-01T00:00:00+00:00",
            effective_date="2026-01-01",
            parser_version="custom.v1",
            schema_version="ingestion_adapter_result.v1",
            confidence=1.0,
        )
    )

    # When: the source is scored for display readiness.
    quality_flags = metadata_quality.flags

    # Then: unknown authority blocks display-ready quality.
    assert quality_flags == ("unaccepted_source_authority",)
    assert metadata_quality.score == 0.0


def test_source_quality_distinguishes_user_upload_as_evidence_candidate() -> None:
    # Given: a user-uploaded document has complete metadata but is not verified as official.
    metadata_quality = score_source_metadata(
        SourceMetadataQualityInput(
            source_url="https://storage.example.test/user/zoning-letter.pdf",
            source_authority="user_upload",
            retrieved_at="2026-06-01T00:00:00+00:00",
            effective_date="2026-01-01",
            parser_version="upload_pdf.v1",
            schema_version="ingestion_adapter_result.v1",
            confidence=0.92,
            source_type="user_uploaded_document",
        )
    )

    # When: the source is scored for display readiness.
    quality_flags = metadata_quality.flags

    # Then: it is traceable evidence candidate material, not an authoritative fact.
    assert quality_flags == ("user_uploaded_document_source",)
    assert metadata_quality.score == 0.4


@pytest.mark.parametrize(
    ("source_type", "source_authority", "expected_flag"),
    (
        ("third_party_aggregator", "third_party_aggregator", "third_party_aggregator_source"),
        ("scraped_web_text", "scraped_web_text", "scraped_web_text_source"),
    ),
)
def test_source_quality_distinguishes_external_evidence_candidates(
    source_type: str,
    source_authority: str,
    expected_flag: str,
) -> None:
    # Given: an external non-authoritative source has complete metadata.
    metadata_quality = score_source_metadata(
        SourceMetadataQualityInput(
            source_url="https://example.test/source",
            source_authority=source_authority,
            retrieved_at="2026-06-01T00:00:00+00:00",
            effective_date="2026-01-01",
            parser_version="external.v1",
            schema_version="ingestion_adapter_result.v1",
            confidence=0.9,
            source_type=source_type,
        )
    )

    # When: the source is scored for display readiness.
    quality_flags = metadata_quality.flags

    # Then: it remains a named evidence candidate and cannot become authoritative.
    assert quality_flags == (expected_flag,)
    assert metadata_quality.score == 0.4


def test_source_quality_distinguishes_assumptions_from_evidence_candidates() -> None:
    # Given: underwriting assumptions and model summaries are complete but non-authoritative.
    assumption_quality = score_source_metadata(
        SourceMetadataQualityInput(
            source_url="plotlot://assumptions/rent",
            source_authority="underwriting_assumption",
            retrieved_at="2026-06-01T00:00:00+00:00",
            effective_date="2026-06-01",
            parser_version="assumption.v1",
            schema_version="ingestion_adapter_result.v1",
            confidence=0.8,
            source_type="underwriting_assumption",
        )
    )
    summary_quality = score_source_metadata(
        SourceMetadataQualityInput(
            source_url="plotlot://model-summary/run-123",
            source_authority="model_generated_summary",
            retrieved_at="2026-06-01T00:00:00+00:00",
            effective_date="2026-06-01",
            parser_version="summary.v1",
            schema_version="ingestion_adapter_result.v1",
            confidence=0.8,
            source_type="model_generated_summary",
        )
    )

    # When: the sources are scored for display readiness.
    assumption_flags = assumption_quality.flags
    summary_flags = summary_quality.flags

    # Then: assumptions and model summaries keep distinct warning categories.
    assert assumption_flags == ("underwriting_assumption_source",)
    assert assumption_quality.score == 0.35
    assert summary_flags == ("model_generated_summary_source",)
    assert summary_quality.score == 0.2


def test_source_quality_caps_stale_effective_date_before_display() -> None:
    # Given: an accepted official source was retrieved years after its effective date.
    metadata_quality = score_source_metadata(
        SourceMetadataQualityInput(
            source_url="https://example.com/zoning",
            source_authority="official_zoning_ordinance",
            retrieved_at="2026-06-01T00:00:00+00:00",
            effective_date="2020-01-01",
            parser_version="custom.v1",
            schema_version="ingestion_adapter_result.v1",
            confidence=0.92,
        )
    )

    # When: the source is scored for display readiness.
    quality_flags = metadata_quality.flags

    # Then: the source is surfaced as stale and cannot remain high confidence.
    assert quality_flags == ("stale_source",)
    assert metadata_quality.score == 0.5


async def test_html_adapter_result_preserves_each_source_url() -> None:
    # Given: an HTML adapter configured with two official source pages.
    adapter = HTMLAdapter(
        municipality="Miramar",
        county="broward",
        state="FL",
        urls=[
            "https://www.miramarfl.gov/zoning-a",
            "https://www.miramarfl.gov/zoning-b",
        ],
        chapter="Land Development Code",
    )

    # When: the adapter emits its typed ingestion result.
    with patch.object(HTMLAdapter, "fetch_chunks", AsyncMock(return_value=[_chunk()])):
        result = await adapter.fetch_ingestion_result()

    # Then: source URLs, parser/schema versions, and freshness warning survive.
    assert [record.source_url for record in result.source_records] == [
        "https://www.miramarfl.gov/zoning-a",
        "https://www.miramarfl.gov/zoning-b",
    ]
    assert result.source_records[0].parser_version == "html.v1"
    assert result.source_records[0].schema_version == "ingestion_adapter_result.v1"
    assert result.quality_flags == ("missing_effective_date",)
    assert result.quality_score == 0.5


async def test_municode_adapter_result_records_query_parameters() -> None:
    # Given: a Municode adapter with official public API identifiers.
    config = MunicodeConfig(
        municipality="Miramar",
        county="broward",
        client_id=3289,
        product_id=13202,
        job_id=479943,
        zoning_node_id="APXAFESC",
        state="FL",
    )
    adapter = MunicodeAdapter(config)

    # When: the adapter emits its typed ingestion result.
    with patch.object(MunicodeAdapter, "fetch_chunks", AsyncMock(return_value=[_chunk()])):
        result = await adapter.fetch_ingestion_result()

    # Then: replay has the exact source endpoint and query parameters.
    record = result.source_records[0]
    assert record.source_url == "https://api.municode.com/CodesContent"
    assert ("jobId", "479943") in record.query_parameters
    assert ("productId", "13202") in record.query_parameters
    assert ("nodeId", "APXAFESC") in record.query_parameters
    assert record.quality_flags == ("missing_effective_date",)


async def test_pdf_adapter_result_uses_pdf_source_effective_date() -> None:
    # Given: a PDF adapter with a dated official planning PDF source.
    adapter = PDFAdapter(
        municipality="San Diego",
        county="San Diego",
        state="CA",
        sources=[
            PDFSource(
                url="https://docs.sandiego.gov/municode/MuniCodeChapter13.pdf",
                chapter="Zones",
                section="Chapter 13",
                chapter_num=13,
                article=1,
                division=1,
                extra={"effective_date": "2026-01-01"},
            )
        ],
    )

    # When: the adapter emits its typed ingestion result.
    with patch.object(PDFAdapter, "fetch_chunks", AsyncMock(return_value=[_chunk()])):
        result = await adapter.fetch_ingestion_result()

    # Then: the dated PDF source is display-ready from an ingestion-quality view.
    record = result.source_records[0]
    assert record.source_url == "https://docs.sandiego.gov/municode/MuniCodeChapter13.pdf"
    assert record.effective_date == "2026-01-01"
    assert record.quality_flags == ()
    assert record.quality_score == 1.0


async def test_pdf_adapter_result_flags_stale_effective_date() -> None:
    # Given: a PDF adapter with an official source whose effective date is stale.
    adapter = PDFAdapter(
        municipality="San Diego",
        county="San Diego",
        state="CA",
        sources=[
            PDFSource(
                url="https://docs.sandiego.gov/municode/MuniCodeChapter13.pdf",
                chapter="Zones",
                section="Chapter 13",
                chapter_num=13,
                article=1,
                division=1,
                extra={"effective_date": "2020-01-01"},
            )
        ],
    )

    # When: the adapter emits its typed ingestion result.
    with patch.object(PDFAdapter, "fetch_chunks", AsyncMock(return_value=[_chunk()])):
        result = await adapter.fetch_ingestion_result()

    # Then: stale source freshness is preserved on the source and aggregate result.
    record = result.source_records[0]
    assert record.quality_flags == ("stale_source",)
    assert record.quality_score == 0.5
    assert result.quality_flags == ("stale_source",)
    assert result.quality_score == 0.5
