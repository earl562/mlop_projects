from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from plotlot.core.types import TextChunk
from plotlot.ingestion.adapters.base import SourceAdapter
from plotlot.ingestion.adapters.result import (
    INGESTION_ADAPTER_SCHEMA_VERSION,
    IngestionAdapterResult,
)


class LegacyChunkAdapter(Protocol):
    name: str

    async def fetch_chunks(self) -> list[TextChunk]: ...


@dataclass(frozen=True, slots=True)
class AdapterResultContext:
    municipality: str
    county: str
    state: str


async def fetch_adapter_ingestion_result(
    adapter: SourceAdapter | LegacyChunkAdapter,
    context: AdapterResultContext,
) -> IngestionAdapterResult:
    match adapter:
        case SourceAdapter():
            return await adapter.fetch_ingestion_result()
        case _:
            chunks = tuple(await adapter.fetch_chunks())
            return IngestionAdapterResult(
                adapter_name=adapter.name,
                municipality=context.municipality,
                county=context.county,
                state=context.state,
                chunks=chunks,
                source_records=(),
                quality_score=0.0,
                quality_flags=("missing_source_url",),
                retrieved_at=datetime.now(UTC).isoformat(),
                parser_version=f"{adapter.name}.legacy_chunks",
                schema_version=INGESTION_ADAPTER_SCHEMA_VERSION,
            )
