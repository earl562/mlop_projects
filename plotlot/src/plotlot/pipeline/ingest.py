"""Ingestion pipeline: scrape → chunk → embed → validate → store.

Orchestrates the full data pipeline for loading zoning ordinances
into pgvector for hybrid search. Network-bound steps (scrape, embed)
use retry with exponential backoff for resilience.

DDIA patterns applied:
- Partitioned processing: each municipality is an independent partition
- Checkpoint-based resumability: progress persisted per-municipality
- Idempotent writes: upsert on natural key (municipality, node_id, chunk_index)
- Bounded resources: connection pool sized to Neon free tier limits
- Error isolation: one municipality failing doesn't stop the batch
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.core.types import MUNICODE_CONFIGS
from plotlot.ingestion.chunker import chunk_sections
from plotlot.ingestion.embedder import EMBEDDING_DIM
from plotlot.ingestion.embedder import MODEL_ID as EMBEDDING_MODEL_ID
from plotlot.ingestion.embedder import embed_texts
from plotlot.ingestion.scraper import MunicodeScraper
from plotlot.observability.tracing import log_metrics, start_span
from plotlot.storage.db import get_session, init_db
from plotlot.storage.models import IngestionCheckpoint, OrdinanceChunk, OrdinanceSection

logger = logging.getLogger(__name__)


def _safe_log_metrics(metrics: dict) -> None:
    """Log metrics to MLflow, swallowing any errors.

    MLflow failures must never break the ingestion pipeline.
    """
    try:
        log_metrics(metrics)
    except Exception:
        logger.debug("MLflow metric logging failed (non-fatal)", exc_info=True)


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
                    label or fn.__name__,
                    attempt,
                    retries,
                    e,
                    wait,
                )
                await asyncio.sleep(wait)
            else:
                logger.error("%s failed after %d attempts: %s", label or fn.__name__, retries, e)
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Config resolution — discovery with graceful fallback
# ---------------------------------------------------------------------------


async def _resolve_config(key: str, state: str | None = None):
    """Resolve a municipality config — warm cache, static fallback, then live discovery.

    The warm cache (``get_municode_configs``) is a curated subset; cities ingested
    via a county batch (e.g. Marin → Tiburon) may not be keyed there. When a state
    is supplied we fall back to a *targeted* single-name Municode lookup so
    ``plotlot-ingest tiburon --state CA`` re-ingests without a full re-discovery
    (which hammers the Library API into 429s).
    """
    try:
        from plotlot.ingestion.discovery import get_municode_configs

        configs = await get_municode_configs()
        config = configs.get(key)
        if config:
            return config
    except Exception as e:
        logger.warning("Discovery cache unavailable, using fallback: %s", e)

    config = MUNICODE_CONFIGS.get(key)
    if config:
        return config

    if state:
        from plotlot.ingestion.discovery import discover_municode_authority_for_name

        name = key.replace("_", " ").title()
        logger.info("Key %r not cached — discovering %r in %s live", key, name, state)
        config = await discover_municode_authority_for_name(name, state)
        if config:
            return config
        raise ValueError(
            f"Could not discover {name!r} on Municode for state {state!r}. "
            "It may use a non-Municode codifier (ingest via the county/ACP path)."
        )

    available = list(MUNICODE_CONFIGS.keys())
    raise ValueError(
        f"Unknown municipality key: {key!r}. Pass --state XX to discover it live "
        f"(e.g. 'plotlot-ingest {key} --state CA'). Available fallback keys: {available}"
    )


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
COMMIT_BATCH_SIZE = 100


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


async def _store_ordinance_sections(session: AsyncSession, chunks: list, config) -> int:
    """Upsert one OrdinanceSection row per unique municode node_id.

    Slice 3.1's structural index: a section fans out to many chunks, but each
    carries the same path/cross_refs/section_type (computed once per section in
    `chunk_sections`). We dedup by node_id and upsert a single structural row.
    `referenced_by` is left untouched here (empty by default); the reverse index
    is built by the Slice 3.5 backfill that scans every section's cross_refs.

    Idempotent: upsert on the (municipality, node_id) natural key, so re-ingestion
    refreshes path/cross_refs/section_type without duplicating rows.
    """
    now = datetime.now(timezone.utc)
    seen: dict[tuple[str, str], dict] = {}
    for chunk in chunks:
        meta = chunk.metadata
        node_id = meta.municode_node_id
        if not node_id:
            # PDF-only sources without a node_id can't satisfy the natural key;
            # skip here (Slice 3.5 backfill handles synthetic node_ids).
            continue
        key = (meta.municipality, node_id)
        if key in seen:
            # Union cross_refs in case a section's chunks split the text such that
            # different refs landed in different chunks (defensive — chunk_sections
            # computes cross_refs once per section, so this is usually a no-op).
            existing = seen[key]
            existing_set = set(existing["cross_refs"]) | set(meta.cross_refs)
            existing["cross_refs"] = sorted(existing_set)
            continue
        source_url = (
            f"https://library.municode.com/search?clientId={config.client_id}&nodeId={node_id}"
        )
        seen[key] = {
            "municipality": meta.municipality,
            "county": meta.county,
            "state": config.state,
            "node_id": node_id,
            "heading": (meta.section_title or None),
            "section_number": (meta.section or None),
            "section_title": (meta.section_title or None),
            "section_type": meta.section_type,
            "path": meta.path,
            "cross_refs": meta.cross_refs,
            "source_url": source_url,
            "scraped_at": now,
        }
    if not seen:
        return 0
    row_dicts = list(seen.values())
    stmt = pg_insert(OrdinanceSection).values(row_dicts)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_section_natural_key",
        set_={
            "heading": stmt.excluded.heading,
            "section_number": stmt.excluded.section_number,
            "section_title": stmt.excluded.section_title,
            "section_type": stmt.excluded.section_type,
            "path": stmt.excluded.path,
            "cross_refs": stmt.excluded.cross_refs,
            "county": stmt.excluded.county,
            "state": stmt.excluded.state,
            "source_url": stmt.excluded.source_url,
            "scraped_at": stmt.excluded.scraped_at,
            # referenced_by intentionally NOT overwritten — the backfill-built
            # reverse index must survive a re-ingestion refresh.
        },
    )
    await session.execute(stmt)
    await session.commit()
    return len(row_dicts)


async def ingest_municipality(key: str, state: str | None = None) -> int:
    """Run the full ingestion pipeline for a single municipality.

    Network-bound steps (scrape, embed) use retry with exponential backoff.
    Each stage logs metrics to MLflow for observability (non-fatal on failure).

    Args:
        key: Municipality key (warm-cache or static-fallback key).
        state: Optional state code; enables live single-name discovery when the
            key isn't cached (e.g. re-ingesting a county-batch city like Tiburon).

    Returns:
        Number of chunks stored.
    """
    config = await _resolve_config(key, state=state)

    logger.info("=== Ingesting %s ===", config.municipality)

    with start_span(name="ingest_municipality") as span:
        if span:
            span.set_inputs({"key": key, "municipality": config.municipality})

        # Step 1: Scrape (with retry — Municode API can be flaky)
        sections = await retry_async(
            _scrape,
            config,
            retries=2,
            delay=30.0,
            label=f"scrape:{config.municipality}",
        )
        logger.info("Scraped %d sections", len(sections))
        _safe_log_metrics({"ingest.sections_scraped": len(sections)})
        await asyncio.sleep(0)  # yield to event loop between stages

        if not sections:
            logger.warning("No sections found for %s — skipping", config.municipality)
            if span:
                span.set_outputs({"chunks_stored": 0, "reason": "no_sections"})
            return 0

        # Step 2: Chunk (CPU-bound BeautifulSoup — run in thread pool to free event loop)
        chunks = await asyncio.to_thread(chunk_sections, sections)
        logger.info("Created %d chunks from %d sections", len(chunks), len(sections))
        _safe_log_metrics({"ingest.chunks_created": len(chunks)})
        await asyncio.sleep(0)  # yield to event loop between stages

        if not chunks:
            if span:
                span.set_outputs({"chunks_stored": 0, "reason": "no_chunks"})
            return 0

        # Step 3: Embed (with retry — HF API can rate-limit)
        texts = [c.text for c in chunks]
        logger.info("Embedding %d chunks...", len(texts))
        embeddings = await retry_async(
            embed_texts,
            texts,
            retries=3,
            delay=10.0,
            label=f"embed:{config.municipality}",
        )
        logger.info("Embedded %d chunks (%dd each)", len(embeddings), EMBEDDING_DIM)
        _safe_log_metrics({"ingest.chunks_embedded": len(embeddings)})
        await asyncio.sleep(0)  # yield to event loop between stages

        # Step 3.5: Validate (deterministic)
        original_count = len(chunks)
        chunks, embeddings = validate_chunks(chunks, embeddings)
        _safe_log_metrics(
            {
                "ingest.chunks_valid": len(chunks),
                "ingest.chunks_filtered": original_count - len(chunks),
            }
        )
        await asyncio.sleep(0)  # yield to event loop between stages
        if not chunks:
            logger.warning("No valid chunks after validation — skipping store")
            if span:
                span.set_outputs({"chunks_stored": 0, "reason": "all_filtered"})
            return 0

        # Step 4: Store
        await init_db()
        session: AsyncSession = await get_session()

        try:
            stored = 0
            for batch_start in range(0, len(chunks), COMMIT_BATCH_SIZE):
                batch_chunks = chunks[batch_start : batch_start + COMMIT_BATCH_SIZE]
                batch_embeddings = embeddings[batch_start : batch_start + COMMIT_BATCH_SIZE]
                now = datetime.now(timezone.utc)
                row_dicts = []
                for chunk, emb in zip(batch_chunks, batch_embeddings):
                    node_id = chunk.metadata.municode_node_id
                    source_url = (
                        f"https://library.municode.com/search?"
                        f"clientId={config.client_id}&nodeId={node_id}"
                    )
                    row_dicts.append(
                        {
                            "municipality": chunk.metadata.municipality,
                            "county": chunk.metadata.county,
                            "chapter": chunk.metadata.chapter,
                            "section": chunk.metadata.section,
                            "section_title": chunk.metadata.section_title,
                            "zone_codes": chunk.metadata.zone_codes,
                            "chunk_text": chunk.text,
                            "chunk_index": chunk.metadata.chunk_index,
                            "embedding": emb,
                            "municode_node_id": node_id,
                            # Lineage fields (B2)
                            "source_url": source_url,
                            "scraped_at": now,
                            "embedding_model": EMBEDDING_MODEL_ID,
                            # State field (B6)
                            "state": config.state,
                        }
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
                        # Lineage fields (B2) — update on re-ingestion
                        "source_url": stmt.excluded.source_url,
                        "scraped_at": stmt.excluded.scraped_at,
                        "embedding_model": stmt.excluded.embedding_model,
                        # State field (B6)
                        "state": stmt.excluded.state,
                    },
                )
                await session.execute(stmt)
                await session.commit()
                stored += len(row_dicts)
                await asyncio.sleep(0)  # yield between DB batches
            logger.info("Stored %d chunks for %s (upsert)", stored, config.municipality)
            _safe_log_metrics({"ingest.chunks_stored": stored})

            # Step 4b: Index sections (Slice 3.1) — one OrdinanceSection row per
            # unique node_id, populated from the chunker's path/cross_refs/section_type.
            sections_indexed = await _store_ordinance_sections(session, chunks, config)
            logger.info(
                "Indexed %d sections for %s (upsert)",
                sections_indexed,
                config.municipality,
            )
            _safe_log_metrics({"ingest.sections_indexed": sections_indexed})

            if span:
                span.set_outputs(
                    {
                        "chunks_stored": stored,
                        "municipality": config.municipality,
                    }
                )
            return stored

        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def ingest_san_diego() -> int:
    """Ingest San Diego zoning code from city-hosted PDFs (not on Municode).

    Scrapes Chapters 13 (Zones) and 15 (Planned Districts) from
    docs.sandiego.gov, chunks the text, embeds, and stores in pgvector.
    Returns total chunks stored.
    """
    from plotlot.ingestion.san_diego_scraper import scrape_san_diego, sections_to_chunks

    logger.info("=== Ingesting San Diego (PDF pipeline) ===")

    sections = await retry_async(
        scrape_san_diego,
        retries=2,
        delay=15.0,
        label="scrape:San Diego",
    )
    if not sections:
        logger.warning("No sections scraped for San Diego — check docs.sandiego.gov availability")
        return 0

    logger.info("Scraped %d PDF sections", len(sections))
    chunks = await asyncio.to_thread(sections_to_chunks, sections)
    logger.info("Created %d chunks", len(chunks))

    if not chunks:
        return 0

    texts = [c.text for c in chunks]
    embeddings = await retry_async(
        embed_texts,
        texts,
        retries=3,
        delay=10.0,
        label="embed:San Diego",
    )

    chunks, embeddings = validate_chunks(chunks, embeddings)
    if not chunks:
        logger.warning("No valid chunks after validation")
        return 0

    await init_db()
    session = await get_session()
    try:
        stored = 0
        now = datetime.now(timezone.utc)
        for batch_start in range(0, len(chunks), COMMIT_BATCH_SIZE):
            batch_chunks = chunks[batch_start : batch_start + COMMIT_BATCH_SIZE]
            batch_embeddings = embeddings[batch_start : batch_start + COMMIT_BATCH_SIZE]
            row_dicts = []
            for chunk, emb in zip(batch_chunks, batch_embeddings):
                row_dicts.append(
                    {
                        "municipality": chunk.metadata.municipality,
                        "county": chunk.metadata.county,
                        "chapter": chunk.metadata.chapter,
                        "section": chunk.metadata.section,
                        "section_title": chunk.metadata.section_title,
                        "zone_codes": chunk.metadata.zone_codes,
                        "chunk_text": chunk.text,
                        "chunk_index": chunk.metadata.chunk_index,
                        "embedding": emb,
                        "municode_node_id": chunk.metadata.municode_node_id,
                        "source_url": "https://docs.sandiego.gov/municode/",
                        "scraped_at": now,
                        "embedding_model": EMBEDDING_MODEL_ID,
                        "state": "CA",
                    }
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
        logger.info("Stored %d chunks for San Diego", stored)
        return stored
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def ingest_county(state_abbr: str, county_key: str) -> dict[str, int]:
    """Ingest all municipalities within a single county.

    Designed for manual county-by-county ingestion workflow. Municipalities
    are processed sequentially (not in parallel) so the operator can monitor
    progress and interrupt cleanly between municipalities.

    Args:
        state_abbr: State abbreviation, e.g. "CA".
        county_key: County key matching the NORCAL_METROS dict, e.g. "sacramento".

    Returns:
        Dict of {municipality_key: chunks_stored} for the county.
    """
    from plotlot.ingestion.discovery import get_municode_configs

    # Discover all available configs then filter to state + county
    all_configs = await get_municode_configs()
    state_configs = {k: v for k, v in all_configs.items() if v.state == state_abbr.upper()}

    # Normalize county key: "contra_costa" matches "Contra Costa"
    def _normalize(s: str) -> str:
        return s.lower().replace(" ", "_").replace("-", "_")

    county_configs = {
        k: v for k, v in state_configs.items() if _normalize(v.county) == _normalize(county_key)
    }

    if not county_configs:
        available = sorted({_normalize(v.county) for v in state_configs.values()})
        raise ValueError(
            f"No municipalities found for county {county_key!r} in {state_abbr}. "
            f"Available counties: {available}"
        )

    county_name = next(iter(county_configs.values())).county
    logger.info(
        "County ingestion: %s — %d municipalities",
        county_name,
        len(county_configs),
    )

    results: dict[str, int] = {}
    succeeded = 0
    failed = 0

    for i, (key, config) in enumerate(county_configs.items(), 1):
        logger.info(
            "[%d/%d] Starting %s",
            i,
            len(county_configs),
            config.municipality,
        )
        try:
            count = await ingest_municipality(key)
            results[key] = count
            succeeded += 1
            logger.info(
                "[%d/%d] %-30s %4d chunks",
                i,
                len(county_configs),
                config.municipality,
                count,
            )
        except Exception as e:
            failed += 1
            results[key] = 0
            logger.error(
                "[%d/%d] %-30s FAILED: %s",
                i,
                len(county_configs),
                config.municipality,
                e,
            )
            # Re-raise credits exhaustion so caller can print the banner
            from plotlot.core.errors import NvidiaCreditsExhaustedError

            if isinstance(e, NvidiaCreditsExhaustedError):
                raise

    total = sum(results.values())
    logger.info(
        "County %s complete: %d chunks across %d municipalities (%d succeeded, %d failed)",
        county_name,
        total,
        len(county_configs),
        succeeded,
        failed,
    )
    return results


async def _checkpoint_mark(
    session: AsyncSession, batch_id: str, key: str, status: str, **kwargs
) -> None:
    """Update a checkpoint row. Creates if not exists via upsert."""
    values = {"batch_id": batch_id, "municipality_key": key, "status": status, **kwargs}
    stmt = pg_insert(IngestionCheckpoint).values(values)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_checkpoint_batch_muni",
        set_={k: v for k, v in values.items() if k not in ("batch_id", "municipality_key")},
    )
    await session.execute(stmt)
    await session.commit()


async def _get_completed_keys(session: AsyncSession, batch_id: str) -> set[str]:
    """Return municipality keys already completed in this batch."""
    result = await session.execute(
        select(IngestionCheckpoint.municipality_key).where(
            IngestionCheckpoint.batch_id == batch_id,
            IngestionCheckpoint.status == "complete",
        )
    )
    return {row[0] for row in result.fetchall()}


async def ingest_all(
    state_filter: str | None = None,
    resume_batch: str | None = None,
) -> dict[str, int]:
    """Ingest municipalities with checkpoint-driven resumability.

    DDIA patterns:
    - Each municipality is a partition — failures are isolated
    - Checkpoints persist to DB — crash at #85 resumes from #86
    - Idempotent upserts — re-running is safe, not wasteful
    - Bounded connections — pool_size=2 respects Neon free tier

    Args:
        state_filter: Only ingest municipalities for this state (e.g. "FL").
        resume_batch: Resume a previous batch by ID. If None, starts fresh.

    Returns:
        Dict of {municipality_key: chunks_stored}.
    """
    configs = await _resolve_all_configs()

    # Filter by state if requested
    if state_filter:
        configs = {k: v for k, v in configs.items() if v.state == state_filter.upper()}

    batch_id = resume_batch or f"batch-{uuid.uuid4().hex[:8]}"
    logger.info(
        "Batch %s: %d municipalities%s",
        batch_id,
        len(configs),
        f" (state={state_filter.upper()})" if state_filter else "",
    )

    # Initialize DB and check for already-completed municipalities.
    # Fail open when the checkpoint database is unavailable so discovery-only
    # unit tests and degraded local runs can still exercise orchestration logic.
    checkpointing_enabled = True
    completed: set[str] = set()
    try:
        await init_db()
        session = await get_session()
        try:
            completed = await _get_completed_keys(session, batch_id)
        finally:
            await session.close()
    except Exception as e:
        checkpointing_enabled = False
        logger.warning(
            "Checkpoint database unavailable for batch %s — continuing without resumability: %s",
            batch_id,
            e,
        )

    if completed:
        logger.info("Resuming batch %s: %d already complete, skipping", batch_id, len(completed))

    remaining = {k: v for k, v in configs.items() if k not in completed}
    logger.info("Processing %d municipalities (%d skipped)", len(remaining), len(completed))

    results: dict[str, int] = {k: 0 for k in completed}  # pre-fill completed
    succeeded = 0
    failed = 0

    for i, (key, config) in enumerate(sorted(remaining.items()), 1):
        # Mark running
        if checkpointing_enabled:
            session = await get_session()
            try:
                await _checkpoint_mark(
                    session,
                    batch_id,
                    key,
                    "running",
                    state=config.state,
                    started_at=datetime.now(timezone.utc),
                )
            finally:
                await session.close()

        try:
            count = await ingest_municipality(key)
            results[key] = count
            succeeded += 1

            # Mark complete
            if checkpointing_enabled:
                session = await get_session()
                try:
                    await _checkpoint_mark(
                        session,
                        batch_id,
                        key,
                        "complete",
                        state=config.state,
                        chunks_stored=count,
                        completed_at=datetime.now(timezone.utc),
                    )
                finally:
                    await session.close()

            logger.info(
                "[%d/%d] %-30s %4d chunks  (batch %s)",
                i,
                len(remaining),
                config.municipality,
                count,
                batch_id,
            )

        except Exception as e:
            failed += 1
            results[key] = 0

            # Mark failed with error message
            if checkpointing_enabled:
                session = await get_session()
                try:
                    await _checkpoint_mark(
                        session,
                        batch_id,
                        key,
                        "failed",
                        state=config.state,
                        error_message=str(e)[:500],
                        completed_at=datetime.now(timezone.utc),
                    )
                finally:
                    await session.close()

            logger.error(
                "[%d/%d] %-30s FAILED: %s",
                i,
                len(remaining),
                config.municipality,
                e,
            )

    total = sum(results.values())
    logger.info(
        "Batch %s complete: %d chunks across %d municipalities (%d succeeded, %d failed, %d skipped)",
        batch_id,
        total,
        len(configs),
        succeeded,
        failed,
        len(completed),
    )

    _safe_log_metrics(
        {
            "ingest.total_chunks": total,
            "ingest.municipalities_processed": succeeded + failed,
            "ingest.municipalities_succeeded": succeeded,
            "ingest.municipalities_failed": failed,
            "ingest.municipalities_skipped": len(completed),
        }
    )

    return results
