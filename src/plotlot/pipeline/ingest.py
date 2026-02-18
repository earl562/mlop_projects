"""Ingestion pipeline: scrape → chunk → embed → validate → store.

Orchestrates the full data pipeline for loading zoning ordinances
into pgvector for hybrid search. Supports both direct async execution
and Prefect-decorated flows for scheduled runs.

Uses auto-discovery to find all municipalities, with fallback to
hardcoded configs when the Library API is unavailable.
"""

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
# Optional Prefect decorators — graceful no-op when prefect isn't installed.
# ---------------------------------------------------------------------------
try:
    from prefect import flow, task
except ImportError:

    def flow(**kwargs):  # type: ignore[misc]
        def wrapper(fn):
            fn._is_flow = True
            return fn

        return wrapper

    def task(**kwargs):  # type: ignore[misc]
        def wrapper(fn):
            fn._is_task = True
            return fn

        return wrapper


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


async def ingest_municipality(key: str) -> int:
    """Run the full ingestion pipeline for a single municipality.

    Returns:
        Number of chunks stored.
    """
    config = await _resolve_config(key)

    logger.info("=== Ingesting %s ===", config.municipality)

    # Step 1: Scrape
    scraper = MunicodeScraper()
    sections = await scraper.scrape_zoning_chapter(config)
    logger.info("Scraped %d sections", len(sections))

    if not sections:
        logger.warning("No sections found for %s — skipping", config.municipality)
        return 0

    # Step 2: Chunk
    chunks = chunk_sections(sections)
    logger.info("Created %d chunks from %d sections", len(chunks), len(sections))

    if not chunks:
        return 0

    # Step 3: Embed
    texts = [c.text for c in chunks]
    logger.info("Embedding %d chunks...", len(texts))
    embeddings = await embed_texts(texts)
    logger.info("Embedded %d chunks (%dd each)", len(embeddings), EMBEDDING_DIM)

    # Step 3.5: Validate
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


# ---------------------------------------------------------------------------
# Prefect flows — for scheduled/observable execution
# ---------------------------------------------------------------------------


@task(name="scrape-municipality", retries=2, retry_delay_seconds=30)
async def scrape_municipality_task(key: str):
    """Prefect task: scrape zoning sections from Municode."""
    config = await _resolve_config(key)
    scraper = MunicodeScraper()
    sections = await scraper.scrape_zoning_chapter(config)
    logger.info("Scraped %d sections for %s", len(sections), config.municipality)
    return sections


@task(name="chunk-sections")
async def chunk_sections_task(sections):
    """Prefect task: parse HTML into text chunks."""
    chunks = chunk_sections(sections)
    logger.info("Created %d chunks", len(chunks))
    return chunks


@task(name="embed-chunks", retries=3, retry_delay_seconds=10)
async def embed_chunks_task(chunks):
    """Prefect task: generate embeddings via HF Inference API."""
    texts = [c.text for c in chunks]
    embeddings = await embed_texts(texts)
    logger.info("Embedded %d chunks", len(embeddings))
    return embeddings


@task(name="validate-chunks")
async def validate_chunks_task(chunks, embeddings):
    """Prefect task: filter out bad embeddings and short chunks."""
    valid_chunks, valid_embeddings = validate_chunks(chunks, embeddings)
    logger.info("Validated: %d/%d chunks passed", len(valid_chunks), len(chunks))
    return valid_chunks, valid_embeddings


@task(name="store-chunks")
async def store_chunks_task(chunks, embeddings):
    """Prefect task: write chunks + embeddings to pgvector."""
    await init_db()
    session = await get_session()
    try:
        rows = []
        for chunk, embedding in zip(chunks, embeddings):
            rows.append(
                OrdinanceChunk(
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
            )
        session.add_all(rows)
        await session.commit()
        logger.info("Stored %d chunks", len(rows))
        return len(rows)
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


@flow(name="ingest-municipality", log_prints=True)
async def ingest_municipality_flow(key: str) -> int:
    """Prefect flow: full pipeline for a single municipality."""
    sections = await scrape_municipality_task(key)
    if not sections:
        return 0
    chunks = await chunk_sections_task(sections)
    if not chunks:
        return 0
    embeddings = await embed_chunks_task(chunks)
    chunks, embeddings = await validate_chunks_task(chunks, embeddings)
    if not chunks:
        return 0
    count = await store_chunks_task(chunks, embeddings)
    return count


@flow(name="ingest-all", log_prints=True)
async def ingest_all_flow() -> dict[str, int]:
    """Prefect flow: ingest all discovered municipalities."""
    configs = await _resolve_all_configs()

    results = {}
    for key in configs:
        try:
            count = await ingest_municipality_flow(key)
            results[key] = count
        except Exception as e:
            logger.error("Failed to ingest %s: %s", key, e)
            results[key] = 0

    total = sum(results.values())
    logger.info("Ingestion complete: %d total chunks across %d municipalities", total, len(results))
    return results
