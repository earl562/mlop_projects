"""Hybrid search: vector similarity + full-text search with RRF fusion."""

import logging

import mlflow
from mlflow.entities import SpanType
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.core.types import SearchResult
from plotlot.ingestion.embedder import embed_texts

logger = logging.getLogger(__name__)

# RRF constant — controls how much top ranks dominate
RRF_K = 60


@mlflow.trace(name="hybrid_search", span_type=SpanType.RETRIEVER)
async def hybrid_search(
    session: AsyncSession,
    municipality: str,
    zone_code: str,
    limit: int = 10,
    embedding: list[float] | None = None,
) -> list[SearchResult]:
    """Run hybrid search combining vector similarity and full-text matching.

    Uses Reciprocal Rank Fusion (RRF) to combine vector and keyword scores.
    If an embedding is provided it is used directly; otherwise the zone_code
    is embedded at query time with input_type="query".
    """
    # Embed the search query for vector similarity
    if embedding is None:
        try:
            vectors = await embed_texts([zone_code], input_type="query")
            embedding = vectors[0] if vectors else None
        except Exception:
            logger.warning("Query embedding failed, falling back to keyword-only search")
            embedding = None

    if embedding is not None:
        return await _hybrid_rrf(session, municipality, zone_code, embedding, limit)

    # Fallback: keyword-only when embedding unavailable
    return await _keyword_only(session, municipality, zone_code, limit)


async def _hybrid_rrf(
    session: AsyncSession,
    municipality: str,
    zone_code: str,
    embedding: list[float],
    limit: int,
) -> list[SearchResult]:
    """Full hybrid search with RRF fusion of vector + keyword results."""
    query = text("""
        WITH vector_results AS (
            SELECT id, section, section_title, zone_codes, chunk_text, municipality,
                   ROW_NUMBER() OVER (ORDER BY embedding <=> CAST(:embedding AS vector)) AS vrank
            FROM ordinance_chunks
            WHERE municipality ILIKE :municipality
              AND embedding IS NOT NULL
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :pool
        ),
        keyword_results AS (
            SELECT id, section, section_title, zone_codes, chunk_text, municipality,
                   ROW_NUMBER() OVER (ORDER BY ts_rank(search_vector, plainto_tsquery(:query)) DESC) AS krank
            FROM ordinance_chunks
            WHERE municipality ILIKE :municipality
              AND (search_vector @@ plainto_tsquery(:query)
                   OR :zone_code = ANY(zone_codes))
            ORDER BY ts_rank(search_vector, plainto_tsquery(:query)) DESC
            LIMIT :pool
        ),
        fused AS (
            SELECT
                COALESCE(v.id, k.id) AS id,
                COALESCE(v.section, k.section) AS section,
                COALESCE(v.section_title, k.section_title) AS section_title,
                COALESCE(v.zone_codes, k.zone_codes) AS zone_codes,
                COALESCE(v.chunk_text, k.chunk_text) AS chunk_text,
                COALESCE(v.municipality, k.municipality) AS municipality,
                COALESCE(1.0 / (:rrf_k + v.vrank), 0) +
                COALESCE(1.0 / (:rrf_k + k.krank), 0) AS rrf_score
            FROM vector_results v
            FULL OUTER JOIN keyword_results k ON v.id = k.id
        )
        SELECT id, section, section_title, zone_codes, chunk_text, municipality, rrf_score
        FROM fused
        ORDER BY rrf_score DESC
        LIMIT :limit
    """)

    embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"
    pool_size = limit * 3  # fetch 3x from each source for better fusion

    result = await session.execute(
        query,
        {
            "municipality": f"%{municipality}%",
            "zone_code": zone_code,
            "query": zone_code,
            "embedding": embedding_str,
            "rrf_k": RRF_K,
            "pool": pool_size,
            "limit": limit,
        },
    )
    rows = result.fetchall()

    return [
        SearchResult(
            section=row.section or "",
            section_title=row.section_title or "",
            zone_codes=row.zone_codes or [],
            chunk_text=row.chunk_text,
            score=float(row.rrf_score),
            municipality=row.municipality,
        )
        for row in rows
    ]


async def _keyword_only(
    session: AsyncSession,
    municipality: str,
    zone_code: str,
    limit: int,
) -> list[SearchResult]:
    """Keyword-only fallback when embedding is unavailable."""
    query = text("""
        SELECT id, section, section_title, zone_codes, chunk_text, municipality,
               ts_rank(search_vector, plainto_tsquery(:query)) AS rank
        FROM ordinance_chunks
        WHERE municipality ILIKE :municipality
          AND (search_vector @@ plainto_tsquery(:query)
               OR :zone_code = ANY(zone_codes))
        ORDER BY rank DESC
        LIMIT :limit
    """)

    result = await session.execute(
        query,
        {
            "municipality": f"%{municipality}%",
            "zone_code": zone_code,
            "query": zone_code,
            "limit": limit,
        },
    )
    rows = result.fetchall()

    return [
        SearchResult(
            section=row.section or "",
            section_title=row.section_title or "",
            zone_codes=row.zone_codes or [],
            chunk_text=row.chunk_text,
            score=float(row.rank),
            municipality=row.municipality,
        )
        for row in rows
    ]
