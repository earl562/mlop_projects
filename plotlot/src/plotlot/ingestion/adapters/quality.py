from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import ClassVar, Protocol

from plotlot.core.types import TextChunk
from plotlot.ingestion.adapters.codifier import WebCodifierAdapter
from plotlot.ingestion.adapters.html import HTMLAdapter
from plotlot.ingestion.adapters.municode import MunicodeAdapter
from plotlot.ingestion.adapters.pdf import PDFAdapter, PDFSource
from plotlot.ingestion.adapters.result import (
    INGESTION_ADAPTER_SCHEMA_VERSION,
    IngestionAdapterResult,
    IngestionSourceRecord,
)
from plotlot.pipeline.lookup_snapshot_source_quality import (
    SourceMetadataQualityInput,
    score_source_metadata,
)


class _AdapterLike(Protocol):
    name: ClassVar[str]
    municipality: str
    county: str
    state: str


@dataclass(frozen=True, slots=True)
class _SourceDescriptor:
    source_type: str
    source_authority: str
    source_url: str
    source_title: str
    publisher: str
    effective_date: str
    query_parameters: tuple[tuple[str, str], ...]


def build_ingestion_adapter_result(
    adapter: _AdapterLike,
    chunks: tuple[TextChunk, ...],
) -> IngestionAdapterResult:
    parser_version = f"{adapter.name}.v1"
    retrieved_at = datetime.now(UTC).isoformat()
    descriptors = _source_descriptors(adapter)
    source_records = tuple(
        _source_record(
            descriptor,
            retrieved_at=retrieved_at,
            parser_version=parser_version,
        )
        for descriptor in descriptors
    )
    return IngestionAdapterResult(
        adapter_name=adapter.name,
        municipality=adapter.municipality,
        county=adapter.county,
        state=adapter.state,
        chunks=chunks,
        source_records=source_records,
        quality_score=_aggregate_quality_score(source_records),
        quality_flags=_unique_flags(source_records),
        retrieved_at=retrieved_at,
        parser_version=parser_version,
        schema_version=INGESTION_ADAPTER_SCHEMA_VERSION,
    )


def _source_descriptors(adapter: _AdapterLike) -> tuple[_SourceDescriptor, ...]:
    if isinstance(adapter, HTMLAdapter):
        return _html_descriptors(adapter, adapter.urls, adapter.chapter)
    if isinstance(adapter, MunicodeAdapter):
        config = adapter.config
        return (
            _SourceDescriptor(
                source_type="official_code_publisher_api",
                source_authority="municode_adopted_code_publisher",
                source_url="https://api.municode.com/CodesContent",
                source_title=f"{config.municipality} zoning code",
                publisher="Municode",
                effective_date="",
                query_parameters=(
                    ("clientId", str(config.client_id)),
                    ("jobId", str(config.job_id)),
                    ("productId", str(config.product_id)),
                    ("nodeId", config.zoning_node_id),
                ),
            ),
        )
    if isinstance(adapter, PDFAdapter):
        return _pdf_descriptors(adapter, adapter.sources)
    if isinstance(adapter, WebCodifierAdapter):
        source_url = adapter.hit.final_url or adapter.hit.url
        return (
            _SourceDescriptor(
                source_type="official_code_publisher_web",
                source_authority=f"codifier:{adapter.hit.platform}",
                source_url=source_url,
                source_title=adapter.hit.title,
                publisher=adapter.hit.platform,
                effective_date="",
                query_parameters=(
                    ("platform", adapter.hit.platform),
                    ("maxPages", str(adapter.max_pages)),
                ),
            ),
        )
    return (
        _SourceDescriptor(
            source_type="unclassified_adapter_source",
            source_authority="unknown",
            source_url="",
            source_title=adapter.name,
            publisher=adapter.municipality,
            effective_date="",
            query_parameters=(),
        ),
    )


def _html_descriptors(
    adapter: HTMLAdapter,
    urls: Sequence[str],
    chapter: str,
) -> tuple[_SourceDescriptor, ...]:
    return tuple(
        _SourceDescriptor(
            source_type="official_web_text",
            source_authority="municipal_web_page",
            source_url=url,
            source_title=chapter or f"{adapter.municipality} zoning web page",
            publisher=adapter.municipality,
            effective_date="",
            query_parameters=(("urlIndex", str(index)),),
        )
        for index, url in enumerate(urls)
    )


def _pdf_descriptors(
    adapter: PDFAdapter,
    sources: Sequence[PDFSource],
) -> tuple[_SourceDescriptor, ...]:
    return tuple(
        _SourceDescriptor(
            source_type="official_planning_pdf",
            source_authority="municipal_pdf",
            source_url=source.url,
            source_title=source.chapter or source.section or f"{adapter.municipality} PDF source",
            publisher=adapter.municipality,
            effective_date=source.extra.get("effective_date", ""),
            query_parameters=(
                ("chapter", source.chapter),
                ("section", source.section),
                ("chapterNum", str(source.chapter_num)),
                ("article", str(source.article)),
                ("division", str(source.division)),
            ),
        )
        for source in sources
    )


def _source_record(
    descriptor: _SourceDescriptor,
    *,
    retrieved_at: str,
    parser_version: str,
) -> IngestionSourceRecord:
    quality = score_source_metadata(
        SourceMetadataQualityInput(
            source_url=descriptor.source_url,
            source_authority=descriptor.source_authority,
            retrieved_at=retrieved_at,
            effective_date=descriptor.effective_date,
            parser_version=parser_version,
            schema_version=INGESTION_ADAPTER_SCHEMA_VERSION,
            confidence=1.0,
        )
    )
    raw_artifact_ref = descriptor.source_url or f"{descriptor.source_type}:unrecorded_source"
    return IngestionSourceRecord(
        source_type=descriptor.source_type,
        source_authority=descriptor.source_authority,
        source_url=descriptor.source_url,
        source_title=descriptor.source_title,
        publisher=descriptor.publisher,
        retrieved_at=retrieved_at,
        effective_date=descriptor.effective_date,
        parser_version=parser_version,
        schema_version=INGESTION_ADAPTER_SCHEMA_VERSION,
        query_parameters=descriptor.query_parameters,
        raw_artifact_ref=raw_artifact_ref,
        lineage=(
            "source",
            "raw_artifact",
            "parsed_chunks",
            "normalized_ingestion_source_record",
        ),
        confidence=1.0,
        quality_score=quality.score,
        quality_flags=quality.flags,
        warnings=quality.flags,
    )


def _aggregate_quality_score(source_records: tuple[IngestionSourceRecord, ...]) -> float:
    if not source_records:
        return 0.0
    return min(record.quality_score for record in source_records)


def _unique_flags(source_records: tuple[IngestionSourceRecord, ...]) -> tuple[str, ...]:
    flags: list[str] = []
    for record in source_records:
        for flag in record.quality_flags:
            if flag not in flags:
                flags.append(flag)
    return tuple(flags)
