"""ACP Ingestion Coordinator — on-demand inline ingestion triggered by a search miss.

Agent Communication Protocol design:
- IngestRequest  : message sent TO the coordinator (trigger + context)
- IngestProgress : message stream FROM the coordinator (stage-by-stage progress)

Flow when search returns 0 results for a municipality:
  1. Caller constructs IngestRequest and passes it to run_on_demand_ingestion()
  2. Coordinator yields IngestProgress events as each stage completes
  3. Caller streams those events as SSE to the frontend
  4. After the generator exhausts, caller re-runs the search with the newly stored data

The coordinator uses the Phase 1 source adapter layer so that any municipality
covered by Municode, a PDF registry, or a custom HTML list can be ingested
without writing a new file.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import AsyncGenerator

from pydantic import BaseModel
from sqlalchemy.dialects.postgresql import insert as pg_insert

from plotlot.core.errors import NoAdapterError
from plotlot.ingestion.adapters import resolve_adapter
from plotlot.ingestion.embedder import MODEL_ID as EMBEDDING_MODEL_ID
from plotlot.ingestion.embedder import embed_texts
from plotlot.pipeline.ingest import validate_chunks
from plotlot.storage.db import get_session, init_db
from plotlot.storage.models import OrdinanceChunk

logger = logging.getLogger(__name__)

# Batch size for embed+store operations (matches pipeline/ingest.py)
_EMBED_BATCH = 50
_STORE_BATCH = 100


# ── ACP message models ────────────────────────────────────────────────────────


class IngestRequest(BaseModel):
    """Message sent TO the coordinator — describes what to ingest and why."""

    municipality: str
    state: str
    county: str | None = None
    trigger: str = "search_miss"  # why ingestion was triggered


class IngestProgress(BaseModel):
    """Message FROM the coordinator — one SSE progress frame."""

    stage: str  # "resolving", "fetching", "embedding", "storing", "complete", "error"
    message: str
    chunks_done: int = 0
    chunks_total: int = 0
    complete: bool = False
    error: str | None = None


# ── Public entry point ────────────────────────────────────────────────────────


async def run_on_demand_ingestion(
    request: IngestRequest,
) -> AsyncGenerator[IngestProgress, None]:
    """Run on-demand ingestion for a municipality and yield SSE progress frames.

    Designed to be awaited inline inside an SSE event generator so progress is
    streamed to the user in real time. Yields at least one IngestProgress event
    per pipeline stage, and always yields a terminal event (complete or error).

    Never raises — all errors are surfaced as IngestProgress(stage="error").

    Yields:
        IngestProgress events describing each stage.

    Example::

        async for prog in run_on_demand_ingestion(IngestRequest(municipality="Fremont", state="CA")):
            yield _sse_event("ingestion_progress", prog.model_dump())
    """
    municipality = request.municipality.strip()
    state = request.state.strip().upper()
    county = request.county

    logger.info(
        "acp_trigger municipality=%s state=%s trigger=%s",
        municipality,
        state,
        request.trigger,
    )

    # ── Stage 1: Resolve adapter ──────────────────────────────────────────────
    yield IngestProgress(
        stage="resolving",
        message=f"Finding data source for {municipality}, {state}…",
    )

    try:
        adapter = await resolve_adapter(municipality, state, county)
    except NoAdapterError as exc:
        logger.warning("acp_no_adapter municipality=%s state=%s", municipality, state)
        yield IngestProgress(
            stage="error",
            message=str(exc),
            error="no_adapter",
            complete=True,
        )
        return
    except Exception as exc:
        logger.warning("acp_resolve_failed municipality=%s error=%s", municipality, exc)
        yield IngestProgress(
            stage="error",
            message=f"Could not find data source: {exc}",
            error="resolve_error",
            complete=True,
        )
        return

    yield IngestProgress(
        stage="resolving",
        message=f"Using {adapter.name} adapter for {municipality}",
        complete=True,
    )

    # ── Stage 2: Fetch chunks ─────────────────────────────────────────────────
    yield IngestProgress(
        stage="fetching",
        message=f"Downloading {municipality} zoning ordinances…",
    )

    try:
        chunks = await adapter.fetch_chunks()
    except Exception as exc:
        logger.error("acp_fetch_failed municipality=%s error=%s", municipality, exc)
        yield IngestProgress(
            stage="error",
            message=f"Download failed: {exc}",
            error="fetch_error",
            complete=True,
        )
        return

    if not chunks:
        yield IngestProgress(
            stage="error",
            message=f"No zoning text found for {municipality}",
            error="empty_source",
            complete=True,
        )
        return

    yield IngestProgress(
        stage="fetching",
        message=f"Downloaded {len(chunks)} text chunks",
        chunks_total=len(chunks),
        complete=True,
    )

    # ── Stage 3: Embed ────────────────────────────────────────────────────────
    total = len(chunks)
    texts = [c.text for c in chunks]
    all_embeddings: list[list[float]] = []

    yield IngestProgress(
        stage="embedding",
        message=f"Embedding {total} chunks…",
        chunks_total=total,
    )

    try:
        for batch_start in range(0, total, _EMBED_BATCH):
            batch_texts = texts[batch_start : batch_start + _EMBED_BATCH]
            batch_embs = await embed_texts(batch_texts, input_type="passage")
            all_embeddings.extend(batch_embs)
            done = min(batch_start + _EMBED_BATCH, total)
            yield IngestProgress(
                stage="embedding",
                message=f"Embedded {done}/{total} chunks",
                chunks_done=done,
                chunks_total=total,
            )
            await asyncio.sleep(0)  # yield event loop between batches
    except Exception as exc:
        logger.error("acp_embed_failed municipality=%s error=%s", municipality, exc)
        yield IngestProgress(
            stage="error",
            message=f"Embedding failed: {exc}",
            error="embed_error",
            complete=True,
        )
        return

    # Validate quality (filters zero vectors, wrong dims, short text)
    chunks, all_embeddings = validate_chunks(chunks, all_embeddings)
    if not chunks:
        yield IngestProgress(
            stage="error",
            message="All chunks failed quality validation — ingestion aborted",
            error="validation_error",
            complete=True,
        )
        return

    yield IngestProgress(
        stage="embedding",
        message=f"Embeddings ready ({len(chunks)} valid chunks)",
        chunks_done=len(chunks),
        chunks_total=len(chunks),
        complete=True,
    )

    # ── Stage 4: Store ────────────────────────────────────────────────────────
    yield IngestProgress(
        stage="storing",
        message=f"Saving {len(chunks)} chunks to database…",
        chunks_total=len(chunks),
    )

    try:
        await init_db()
        session = await get_session()
        stored = 0
        now = datetime.now(timezone.utc)

        try:
            for batch_start in range(0, len(chunks), _STORE_BATCH):
                batch_chunks = chunks[batch_start : batch_start + _STORE_BATCH]
                batch_embs = all_embeddings[batch_start : batch_start + _STORE_BATCH]

                row_dicts = [
                    {
                        "municipality": c.metadata.municipality,
                        "county": c.metadata.county,
                        "chapter": c.metadata.chapter,
                        "section": c.metadata.section,
                        "section_title": c.metadata.section_title,
                        "zone_codes": c.metadata.zone_codes,
                        "chunk_text": c.text,
                        "chunk_index": c.metadata.chunk_index,
                        "embedding": emb,
                        "municode_node_id": c.metadata.municode_node_id,
                        "source_url": None,
                        "scraped_at": now,
                        "embedding_model": EMBEDDING_MODEL_ID,
                        "state": state,
                    }
                    for c, emb in zip(batch_chunks, batch_embs)
                ]

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
                    message=f"Saved {stored}/{len(chunks)} chunks",
                    chunks_done=stored,
                    chunks_total=len(chunks),
                )
                await asyncio.sleep(0)

        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    except Exception as exc:
        logger.error("acp_store_failed municipality=%s error=%s", municipality, exc)
        yield IngestProgress(
            stage="error",
            message=f"Database write failed: {exc}",
            error="store_error",
            complete=True,
        )
        return

    logger.info(
        "acp_complete municipality=%s state=%s chunks_stored=%d trigger=%s",
        municipality,
        state,
        stored,
        request.trigger,
    )

    yield IngestProgress(
        stage="complete",
        message=f"Ingested {stored} chunks for {municipality} — retrying search",
        chunks_done=stored,
        chunks_total=stored,
        complete=True,
    )
