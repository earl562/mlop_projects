from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from plotlot.core.types import TextChunk

INGESTION_ADAPTER_SCHEMA_VERSION: Final = "ingestion_adapter_result.v1"


@dataclass(frozen=True, slots=True)
class IngestionSourceRecord:
    source_type: str
    source_authority: str
    source_url: str
    source_title: str
    publisher: str
    retrieved_at: str
    effective_date: str
    parser_version: str
    schema_version: str
    query_parameters: tuple[tuple[str, str], ...]
    raw_artifact_ref: str
    lineage: tuple[str, ...]
    confidence: float
    quality_score: float
    quality_flags: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class IngestionAdapterResult:
    adapter_name: str
    municipality: str
    county: str
    state: str
    chunks: tuple[TextChunk, ...]
    source_records: tuple[IngestionSourceRecord, ...]
    quality_score: float
    quality_flags: tuple[str, ...]
    retrieved_at: str
    parser_version: str
    schema_version: str
