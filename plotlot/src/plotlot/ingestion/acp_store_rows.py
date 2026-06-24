from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TypedDict

from plotlot.core.types import TextChunk
from plotlot.ingestion.adapters.result import IngestionAdapterResult, IngestionSourceRecord


class OrdinanceChunkValue(TypedDict):
    municipality: str
    county: str
    chapter: str
    section: str
    section_title: str
    zone_codes: list[str]
    chunk_text: str
    chunk_index: int
    embedding: list[float]
    municode_node_id: str
    source_url: str | None
    scraped_at: datetime
    embedding_model: str
    state: str


@dataclass(frozen=True, slots=True)
class OrdinanceChunkStoreBatch:
    chunks: list[TextChunk]
    embeddings: list[list[float]]
    ingestion_result: IngestionAdapterResult
    scraped_at: datetime
    embedding_model: str
    state: str


def scraped_at_from_result(result: IngestionAdapterResult) -> datetime:
    return datetime.fromisoformat(result.retrieved_at)


def build_ordinance_chunk_values(batch: OrdinanceChunkStoreBatch) -> list[OrdinanceChunkValue]:
    return [
        {
            "municipality": chunk.metadata.municipality,
            "county": chunk.metadata.county,
            "chapter": chunk.metadata.chapter,
            "section": chunk.metadata.section,
            "section_title": chunk.metadata.section_title,
            "zone_codes": chunk.metadata.zone_codes,
            "chunk_text": chunk.text,
            "chunk_index": chunk.metadata.chunk_index,
            "embedding": embedding,
            "municode_node_id": chunk.metadata.municode_node_id,
            "source_url": _source_url_for_chunk(batch.ingestion_result, chunk),
            "scraped_at": batch.scraped_at,
            "embedding_model": batch.embedding_model,
            "state": batch.state,
        }
        for chunk, embedding in zip(batch.chunks, batch.embeddings)
    ]


def _source_url_for_chunk(result: IngestionAdapterResult, chunk: TextChunk) -> str | None:
    record = _source_record_for_chunk(result, chunk)
    if record is None:
        return None
    return record.source_url or None


def _source_record_for_chunk(
    result: IngestionAdapterResult,
    chunk: TextChunk,
) -> IngestionSourceRecord | None:
    if len(result.source_records) == 1:
        return result.source_records[0]
    html_record = _html_source_record(result, chunk)
    if html_record is not None:
        return html_record
    pdf_record = _pdf_source_record(result, chunk)
    if pdf_record is not None:
        return pdf_record
    return None


def _html_source_record(
    result: IngestionAdapterResult,
    chunk: TextChunk,
) -> IngestionSourceRecord | None:
    index = _html_index(chunk.metadata.municode_node_id)
    if index is None:
        return None
    for record in result.source_records:
        if ("urlIndex", str(index)) in record.query_parameters:
            return record
    return None


def _html_index(node_id: str) -> int | None:
    if not node_id.startswith("html_"):
        return None
    raw_index = node_id.removeprefix("html_").split("_", maxsplit=1)[0]
    try:
        return int(raw_index)
    except ValueError:
        return None


def _pdf_source_record(
    result: IngestionAdapterResult,
    chunk: TextChunk,
) -> IngestionSourceRecord | None:
    node_id = chunk.metadata.municode_node_id
    for record in result.source_records:
        prefix = _pdf_node_prefix(record.query_parameters)
        if prefix and node_id.startswith(prefix):
            return record
    return None


def _pdf_node_prefix(query_parameters: tuple[tuple[str, str], ...]) -> str:
    parameters = dict(query_parameters)
    chapter_num = _int_parameter(parameters.get("chapterNum"))
    article = _int_parameter(parameters.get("article"))
    division = _int_parameter(parameters.get("division"))
    if chapter_num is None or article is None or division is None:
        return ""
    return f"ch{chapter_num:02d}_art{article:02d}_div{division:02d}"


def _int_parameter(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None
