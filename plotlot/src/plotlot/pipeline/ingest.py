"""Ingestion pipeline: scrape → chunk → embed → validate → store.

Orchestrates the full data pipeline for loading zoning ordinances
into pgvector for hybrid search. Network-bound steps (scrape, embed)
use retry with exponential backoff for resilience.
"""

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.core.types import MUNICODE_CONFIGS
from plotlot.ingestion.chunker import chunk_sections
from plotlot.ingestion.embedder import EMBEDDING_DIM, embed_texts
from plotlot.ingestion.scraper import MunicodeScraper
from plotlot.storage.db import get_session, init_db
from plotlot.storage.models import OrdinanceChunk

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Retry utility — replaces Prefect's task-level retry with working logic
# ---------------------------------------------------------------------------

async def retry_async(fn, *args, retries: int = 3, delay: float = 5.0, label: str = ""):
    """Retry an async function with exponential backoff.

    Used on network-bound pipeline steps (scrape, embed) where transient
    failures are expected. Simpler than Prefect for a single-service deploy.
    """
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            return await fn(*args)
        except Exception as e:
            last_exc = e
            if attempt < retries:
                wait = delay * (2 ** (attempt - 1))
                logger.warning(
                    "%s failed (attempt %d/%d): %s — retrying in %.0fs",
                    label or fn.__name__, attempt, retries, e, wait,
                )
                await asyncio.sleep(wait)
            else:
                logger.error("%s failed after %d attempts: %s", label or fn.__name__, retries, e)
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Config resolution — discovery with graceful fallback
# ---------------------------------------------------------------------------


async def _resolve_config(key: str):
    """Resolve a municipality config — try discovery first, fall back to static."""
    try:
        from plotlot.ingestion.discovery import get_municode_configs

        configs = await get_municode_configs()
        config = configs.get(key)
        if config:
            return config
    except Exception as e:
        logger.warning("Discovery unavailable, using fallback: %s", e)

    config = MUNICODE_CONFIGS.get(key)
    if not config:
        available = list(MUNICODE_CONFIGS.keys())
        raise ValueError(f"Unknown municipality key: {key!r}. Available fallback keys: {available}")
    return config


async def _resolve_all_configs() -> dict:
    """Get all municipality configs — discovery or fallback."""
    try:
        from plotlot.ingestion.discovery import get_municode_configs

        return await get_municode_configs()
    except Exception as e:
        logger.warning("Discovery unavailable, using fallback configs: %s", e)
        return dict(MUNICODE_CONFIGS)


# ---------------------------------------------------------------------------
# Data quality validation
# ---------------------------------------------------------------------------

MIN_CHUNK_TEXT_LENGTH = 50


def validate_chunks(chunks, embeddings):
    """Filter out chunks with quality issues before storage.

    Checks:
    - Embedding dimension matches expected (EMBEDDING_DIM)
    - No zero vectors (embedding API failure)
    - Chunk text meets minimum length

    Returns:
        Tuple of (valid_chunks, valid_embeddings).
    """
    valid_chunks, valid_embeddings = [], []
    issues = []

    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        if len(emb) != EMBEDDING_DIM:
            issues.append(f"Chunk {i}: wrong embedding dim {len(emb)}, expected {EMBEDDING_DIM}")
            continue
        if all(v == 0.0 for v in emb):
            issues.append(f"Chunk {i}: zero vector")
            continue
        if len(chunk.text.strip()) < MIN_CHUNK_TEXT_LENGTH:
            issues.append(f"Chunk {i}: text too short ({len(chunk.text.strip())} chars)")
            continue
        valid_chunks.append(chunk)
        valid_embeddings.append(emb)

    if issues:
        logger.warning(
            "Data quality: filtered %d/%d chunks",
            len(issues),
            len(chunks),
        )
        for issue in issues[:10]:
            logger.warning("  %s", issue)

    return valid_chunks, valid_embeddings


# ---------------------------------------------------------------------------
# Core pipeline functions
# ---------------------------------------------------------------------------


async def _scrape(config) -> list:
    """Scrape zoning sections — separated for retry wrapper."""
    scraper = MunicodeScraper()
    return await scraper.scrape_zoning_chapter(config)


async def ingest_municipality(key: str) -> int:
    """Run the full ingestion pipeline for a single municipality.

    Network-bound steps (scrape, embed) use retry with exponential backoff.

    Returns:
        Number of chunks stored.
    """
    config = await _resolve_config(key)

    logger.info("=== Ingesting %s ===", config.municipality)

    # Step 1: Scrape (with retry — Municode API can be flaky)
    sections = await retry_async(
        _scrape, config, retries=2, delay=30.0, label=f"scrape:{config.municipality}",
    )
    logger.info("Scraped %d sections", len(sections))

    if not sections:
        logger.warning("No sections found for %s — skipping", config.municipality)
        return 0

    # Step 2: Chunk (deterministic — no retry needed)
    chunks = chunk_sections(sections)
    logger.info("Created %d chunks from %d sections", len(chunks), len(sections))

    if not chunks:
        return 0

    # Step 3: Embed (with retry — HF API can rate-limit)
    texts = [c.text for c in chunks]
    logger.info("Embedding %d chunks...", len(texts))
    embeddings = await retry_async(
        embed_texts, texts, retries=3, delay=10.0, label=f"embed:{config.municipality}",
    )
    logger.info("Embedded %d chunks (%dd each)", len(embeddings), EMBEDDING_DIM)

    # Step 3.5: Validate (deterministic)
    chunks, embeddings = validate_chunks(chunks, embeddings)
    if not chunks:
        logger.warning("No valid chunks after validation — skipping store")
        return 0

    # Step 4: Store
    await init_db()
    session: AsyncSession = await get_session()

    try:
        rows = []
        for chunk, embedding in zip(chunks, embeddings):
            row = OrdinanceChunk(
                municipality=chunk.metadata.municipality,
                county=chunk.metadata.county,
                chapter=chunk.metadata.chapter,
                section=chunk.metadata.section,
                section_title=chunk.metadata.section_title,
                zone_codes=chunk.metadata.zone_codes,
                chunk_text=chunk.text,
                chunk_index=chunk.metadata.chunk_index,
                embedding=embedding,
                municode_node_id=chunk.metadata.municode_node_id,
            )
            rows.append(row)

        session.add_all(rows)
        await session.commit()
        logger.info("Stored %d chunks for %s", len(rows), config.municipality)
        return len(rows)

    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def ingest_all() -> dict[str, int]:
    """Ingest all discovered municipalities.

    Returns:
        Dict of {municipality_key: chunks_stored}.
    """
    configs = await _resolve_all_configs()
    logger.info("Ingesting %d municipalities", len(configs))

    results = {}
    for key in configs:
        try:
            count = await ingest_municipality(key)
            results[key] = count
        except Exception as e:
            logger.error("Failed to ingest %s: %s", key, e)
            results[key] = 0

    total = sum(results.values())
    logger.info("Ingestion complete: %d total chunks across %d municipalities", total, len(results))
    return results
