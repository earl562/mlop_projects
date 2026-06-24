from __future__ import annotations

from datetime import UTC, datetime

from plotlot.core.types import ChunkMetadata, TextChunk
from plotlot.ingestion.acp_store_rows import (
    OrdinanceChunkStoreBatch,
    build_ordinance_chunk_values,
)
from plotlot.ingestion.adapters.result import IngestionAdapterResult, IngestionSourceRecord


def _chunk(node_id: str) -> TextChunk:
    return TextChunk(
        text="Section 12.3 - Residential density limit is 25 units per acre.",
        metadata=ChunkMetadata(
            municipality="Fremont",
            county="Alameda",
            chapter="Chapter 12",
            section="12.3",
            section_title="Residential Density",
            zone_codes=["RM-25"],
            chunk_index=0,
            municode_node_id=node_id,
        ),
    )


def _source_record(
    url: str,
    query_parameters: tuple[tuple[str, str], ...] = (),
) -> IngestionSourceRecord:
    return IngestionSourceRecord(
        source_type="official_web_text",
        source_authority="municipal_web_page",
        source_url=url,
        source_title="Fremont zoning",
        publisher="Fremont",
        retrieved_at="2026-01-02T03:04:05+00:00",
        effective_date="",
        parser_version="html.v1",
        schema_version="ingestion_adapter_result.v1",
        query_parameters=query_parameters,
        raw_artifact_ref=url,
        lineage=("source", "raw_artifact", "parsed_chunks"),
        confidence=1.0,
        quality_score=0.5,
        quality_flags=("missing_effective_date",),
        warnings=("missing_effective_date",),
    )


def _result(
    chunk: TextChunk,
    records: tuple[IngestionSourceRecord, ...],
) -> IngestionAdapterResult:
    return IngestionAdapterResult(
        adapter_name="html",
        municipality="Fremont",
        county="Alameda",
        state="CA",
        chunks=(chunk,),
        source_records=records,
        quality_score=0.5,
        quality_flags=("missing_effective_date",),
        retrieved_at="2026-01-02T03:04:05+00:00",
        parser_version="html.v1",
        schema_version="ingestion_adapter_result.v1",
    )


def _values(result: IngestionAdapterResult, chunk: TextChunk):
    return build_ordinance_chunk_values(
        OrdinanceChunkStoreBatch(
            chunks=[chunk],
            embeddings=[[0.1] * 1024],
            ingestion_result=result,
            scraped_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
            embedding_model="test-embedding",
            state="CA",
        )
    )


def test_single_source_adapter_record_applies_to_each_chunk() -> None:
    # Given: a single-source adapter result.
    chunk = _chunk("node_0001")
    result = _result(chunk, (_source_record("https://municode.example/code"),))

    # When: store rows are built for the chunk.
    values = _values(result, chunk)

    # Then: the row keeps that source URL.
    assert values[0]["source_url"] == "https://municode.example/code"


def test_pdf_source_record_matches_chunk_node_prefix() -> None:
    # Given: a PDF chunk whose node id encodes chapter, article, and division.
    chunk = _chunk("ch13_art01_div02_chunk0")
    result = _result(
        chunk,
        (
            _source_record(
                "https://docs.example/chapter-13.pdf",
                (
                    ("chapterNum", "13"),
                    ("article", "1"),
                    ("division", "2"),
                ),
            ),
            _source_record(
                "https://docs.example/chapter-14.pdf",
                (
                    ("chapterNum", "14"),
                    ("article", "1"),
                    ("division", "1"),
                ),
            ),
        ),
    )

    # When: store rows are built for the PDF chunk.
    values = _values(result, chunk)

    # Then: the row keeps the matching PDF URL.
    assert values[0]["source_url"] == "https://docs.example/chapter-13.pdf"


def test_ambiguous_multi_source_chunk_does_not_guess_source_url() -> None:
    # Given: multiple source records but no deterministic chunk-to-source key.
    chunk = _chunk("unmapped_node")
    result = _result(
        chunk,
        (
            _source_record("https://fremont.gov/zoning-a", (("urlIndex", "0"),)),
            _source_record("https://fremont.gov/zoning-b", (("urlIndex", "1"),)),
        ),
    )

    # When: store rows are built for the ambiguous chunk.
    values = _values(result, chunk)

    # Then: the row stores unknown instead of inventing lineage.
    assert values[0]["source_url"] is None


def test_malformed_pdf_source_parameters_do_not_crash_or_guess_source_url() -> None:
    # Given: multiple PDF source records with one malformed chapter/article/division descriptor.
    chunk = _chunk("ch13_art01_div02_chunk0")
    result = _result(
        chunk,
        (
            _source_record(
                "https://docs.example/malformed.pdf",
                (
                    ("chapterNum", "thirteen"),
                    ("article", "1"),
                    ("division", "2"),
                ),
            ),
            _source_record(
                "https://docs.example/chapter-14.pdf",
                (
                    ("chapterNum", "14"),
                    ("article", "1"),
                    ("division", "1"),
                ),
            ),
        ),
    )

    # When: store rows are built for the PDF chunk.
    values = _values(result, chunk)

    # Then: the row keeps source lineage unknown instead of crashing or guessing.
    assert values[0]["source_url"] is None
