"""Ingest Sausalito and Tiburon via codifier adapter (bypasses Municode API)."""
import asyncio
import logging
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/Users/aaliyahmatthews/Desktop/plotlot/plotlot-v2/plotlot")

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from plotlot.ingestion.adapters.registry import resolve_adapter
from plotlot.ingestion.embedder import embed_texts
from plotlot.pipeline.ingest import validate_chunks
from plotlot.storage.db import get_session, init_db
from plotlot.storage.models import OrdinanceChunk

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("codifier_ingest")

COMMIT_BATCH_SIZE = 100
EMBEDDING_MODEL_ID = "nvidia/nv-embed-qa-4"  # matches existing pipeline

MUNICIPALITIES = [
    ("Sausalito", "marin", "CA"),
    ("Tiburon", "marin", "CA"),
]

async def ingest_one(name, county, state):
    logger.info("=== Resolving adapter for %s ===", name)
    adapter = await resolve_adapter(name, state, county=county)
    logger.info("Adapter: %s (%s)", type(adapter).__name__, getattr(adapter, "name", "?"))

    logger.info("=== Fetching chunks for %s ===", name)
    chunks = await adapter.fetch_chunks()
    logger.info("Fetched %d raw chunks", len(chunks))

    if not chunks:
        logger.warning("No chunks for %s — skipping", name)
        return 0

    # Embed
    texts = [c.text for c in chunks]
    logger.info("Embedding %d chunks...", len(texts))
    embeddings = await embed_texts(texts)
    logger.info("Embedded %d chunks", len(embeddings))

    # Validate
    original = len(chunks)
    chunks, embeddings = validate_chunks(chunks, embeddings)
    filtered = original - len(chunks)
    if filtered:
        logger.info("Filtered %d invalid chunks", filtered)
    if not chunks:
        logger.warning("No valid chunks after validation")
        return 0

    # Store
    await init_db()
    session = await get_session()
    try:
        stored = 0
        now = datetime.now(timezone.utc)
        for batch_start in range(0, len(chunks), COMMIT_BATCH_SIZE):
            batch_end = batch_start + COMMIT_BATCH_SIZE
            batch_chunks = chunks[batch_start:batch_end]
            batch_embeddings = embeddings[batch_start:batch_end]

            row_dicts = []
            for chunk, emb in zip(batch_chunks, batch_embeddings):
                meta = chunk.metadata
                row_dicts.append({
                    "municipality": meta.municipality,
                    "county": meta.county,
                    "chapter": meta.chapter,
                    "section": meta.section,
                    "section_title": meta.section_title,
                    "zone_codes": meta.zone_codes,
                    "chunk_text": chunk.text,
                    "chunk_index": meta.chunk_index,
                    "embedding": emb,
                    "municode_node_id": meta.municode_node_id,
                    "source_url": "",
                    "scraped_at": now,
                    "embedding_model": EMBEDDING_MODEL_ID,
                    "state": state.upper(),
                })

            stmt = pg_insert(OrdinanceChunk).values(row_dicts)
            stmt = stmt.on_conflict_do_update(
                index_elements=["municipality", "municode_node_id", "chunk_index"],
                set_={
                    "chunk_text": stmt.excluded.chunk_text,
                    "embedding": stmt.excluded.embedding,
                    "zone_codes": stmt.excluded.zone_codes,
                    "section_title": stmt.excluded.section_title,
                    "scraped_at": stmt.excluded.scraped_at,
                    "embedding_model": stmt.excluded.embedding_model,
                    "state": stmt.excluded.state,
                },
            )
            await session.execute(stmt)
            await session.commit()
            stored += len(row_dicts)
            logger.info("Batch %d-%d: stored %d chunks", batch_start, batch_end, len(row_dicts))

        logger.info("=== %s complete: %d chunks stored ===", name, stored)
        return stored
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()

async def main():
    total = 0
    for name, county, state in MUNICIPALITIES:
        count = await ingest_one(name, county, state)
        total += count
        print(f"\n  {name}: {count} chunks")

    print(f"\n{'='*50}")
    print(f"  TOTAL: {total} chunks stored")
    print(f"{'='*50}")

asyncio.run(main())
