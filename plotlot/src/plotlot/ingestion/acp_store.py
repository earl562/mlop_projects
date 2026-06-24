from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass

import anyio
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError

from plotlot.core.types import TextChunk
from plotlot.ingestion.acp_evidence import (
    IngestionEvidenceContext,
    persist_ingestion_source_records,
)
from plotlot.ingestion.acp_models import IngestProgress
from plotlot.ingestion.acp_store_rows import (
    OrdinanceChunkStoreBatch,
    build_ordinance_chunk_values,
    scraped_at_from_result,
)
from plotlot.ingestion.adapters.result import IngestionAdapterResult
from plotlot.ingestion.embedder import MODEL_ID as EMBEDDING_MODEL_ID
from plotlot.storage.db import get_session, init_db
from plotlot.storage.models import OrdinanceChunk

_STORE_BATCH = 100


@dataclass(frozen=True, slots=True)
class IngestionStoreRequest:
    chunks: list[TextChunk]
    embeddings: list[list[float]]
    ingestion_result: IngestionAdapterResult
    state: str
    evidence_context: IngestionEvidenceContext | None = None


async def store_ingestion_result(
    request: IngestionStoreRequest,
) -> AsyncGenerator[IngestProgress, None]:
    await init_db()
    session = await get_session()
    stored = 0
    scraped_at = scraped_at_from_result(request.ingestion_result)

    try:
        for batch_start in range(0, len(request.chunks), _STORE_BATCH):
            batch_chunks = request.chunks[batch_start : batch_start + _STORE_BATCH]
            batch_embs = request.embeddings[batch_start : batch_start + _STORE_BATCH]
            row_dicts = build_ordinance_chunk_values(
                OrdinanceChunkStoreBatch(
                    chunks=batch_chunks,
                    embeddings=batch_embs,
                    ingestion_result=request.ingestion_result,
                    scraped_at=scraped_at,
                    embedding_model=EMBEDDING_MODEL_ID,
                    state=request.state,
                )
            )
            stmt = pg_insert(OrdinanceChunk).values(row_dicts)
            stmt = stmt.on_conflict_do_update(
                index_elements=["municipality", "municode_node_id", "chunk_index"],
                set_={
                    "chunk_text": stmt.excluded.chunk_text,
                    "embedding": stmt.excluded.embedding,
                    "section": stmt.excluded.section,
                    "section_title": stmt.excluded.section_title,
                    "zone_codes": stmt.excluded.zone_codes,
                    "chapter": stmt.excluded.chapter,
                    "county": stmt.excluded.county,
                    "source_url": stmt.excluded.source_url,
                    "scraped_at": stmt.excluded.scraped_at,
                    "embedding_model": stmt.excluded.embedding_model,
                    "state": stmt.excluded.state,
                },
            )
            await session.execute(stmt)
            await session.commit()
            stored += len(row_dicts)
            yield IngestProgress(
                stage="storing",
                message=f"Saved {stored}/{len(request.chunks)} chunks",
                chunks_done=stored,
                chunks_total=len(request.chunks),
            )
            await anyio.sleep(0)

        if request.evidence_context is not None:
            evidence_ids = await persist_ingestion_source_records(
                session,
                request.evidence_context,
                request.ingestion_result,
            )
            if evidence_ids:
                await session.commit()
                yield IngestProgress(
                    stage="evidence",
                    message=f"Recorded {len(evidence_ids)} ingestion source evidence item(s)",
                    chunks_done=stored,
                    chunks_total=len(request.chunks),
                    complete=True,
                    evidence_ids=evidence_ids,
                    quality_flags=request.ingestion_result.quality_flags,
                    source_record_count=len(request.ingestion_result.source_records),
                )

    except SQLAlchemyError:
        await session.rollback()
        raise
    finally:
        await session.close()
