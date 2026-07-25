"""Hybrid search: vector similarity + full-text search with RRF fusion."""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.core.types import SearchResult
from plotlot.ingestion.embedder import embed_texts
from plotlot.observability.tracing import start_span

logger = logging.getLogger(__name__)

# RRF constant — controls how much top ranks dominate
RRF_K = 60

# Municipality match predicate. The ordinance key (ingested city) and the
# parcel/geocode municipality can differ: the parcel layer / Geocodio returns
# composite CDP names like "Belvedere Tiburon" while ordinances were ingested
# under the incorporated city "Tiburon". Match in BOTH directions —
#   1. stored key contains the requested name  (existing behavior), OR
#   2. the requested name contains the stored key  ("Belvedere Tiburon" ⊃ "Tiburon").
# Additive: never removes a match the one-directional filter would have made.
# char_length guard avoids a too-short stored key matching unrelated requests.
_MUNI_WHERE = (
    "(municipality ILIKE :municipality "
    "OR (char_length(municipality) >= 4 AND :municipality_raw ILIKE '%' || municipality || '%'))"
)


async def hybrid_search(
    session: AsyncSession,
    municipality: str,
    zone_code: str,
    limit: int = 10,
    embedding: list[float] | None = None,
    zone_code_boost: str | None = None,
) -> list[SearchResult]:
    """Run hybrid search combining vector similarity and full-text matching.

    Uses Reciprocal Rank Fusion (RRF) to combine vector and keyword scores.
    If an embedding is provided it is used directly; otherwise the zone_code
    is embedded at query time with input_type="query".

    zone_code_boost: optional exact zone code (e.g. "RM-3-7") used to boost chunks
    whose zone_codes[] metadata contains that code, improving accuracy when the
    query text is a natural-language phrase rather than the bare code.
    """
    with start_span(name="hybrid_search", span_type="RETRIEVER") as span:
        span.set_inputs(
            {
                "municipality": municipality,
                "query": zone_code,
                "zone_code_boost": zone_code_boost,
                "limit": limit,
            }
        )

        # Embed the search query for vector similarity
        if embedding is None:
            try:
                vectors = await embed_texts([zone_code], input_type="query")
                embedding = vectors[0] if vectors else None
            except Exception:
                logger.warning("Query embedding failed, falling back to keyword-only search")
                embedding = None

        if embedding is not None:
            results = await _hybrid_rrf(
                session, municipality, zone_code, embedding, limit, zone_code_boost
            )
        else:
            # Fallback: keyword-only when embedding unavailable
            results = await _keyword_only(session, municipality, zone_code, limit)

        # Log retrieval outputs for replay — top 5 with sections, zone_codes, scores
        top_chunks = [
            {
                "section": r.section,
                "section_title": r.section_title,
                "zone_codes": r.zone_codes,
                "score": round(r.score, 4),
            }
            for r in results[:5]
        ]
        span.set_outputs(
            {
                "result_count": len(results),
                "search_mode": "hybrid_rrf" if embedding is not None else "keyword_only",
                "top_chunks": top_chunks,
            }
        )

        return results


async def _hybrid_rrf(
    session: AsyncSession,
    municipality: str,
    zone_code: str,
    embedding: list[float],
    limit: int,
    zone_code_boost: str | None = None,
) -> list[SearchResult]:
    """Full hybrid search with RRF fusion of vector + keyword results.

    zone_code_boost: when provided, chunks whose zone_codes[] metadata contains
    this exact code receive a +0.1 RRF score bonus. This lifts zone-specific
    sections above generic provisions that happen to rank well on semantics alone.
    """
    boost_sql = (
        "CASE WHEN :zone_code_boost = ANY(COALESCE(v.zone_codes, k.zone_codes)) THEN 0.1 ELSE 0 END"
        if zone_code_boost
        else "0"
    )
    query = text(f"""
        WITH vector_results AS (
            SELECT id, section, section_title, zone_codes, chunk_text, municipality,
                   chapter, municode_node_id, source_url,
                   ROW_NUMBER() OVER (ORDER BY embedding <=> CAST(:embedding AS vector)) AS vrank
            FROM ordinance_chunks
            WHERE {_MUNI_WHERE}
              AND embedding IS NOT NULL
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :pool
        ),
        keyword_results AS (
            SELECT id, section, section_title, zone_codes, chunk_text, municipality,
                   chapter, municode_node_id, source_url,
                   ROW_NUMBER() OVER (ORDER BY ts_rank(search_vector, plainto_tsquery(:query)) DESC) AS krank
            FROM ordinance_chunks
            WHERE {_MUNI_WHERE}
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
                COALESCE(v.chapter, k.chapter) AS chapter,
                COALESCE(v.municode_node_id, k.municode_node_id) AS municode_node_id,
                COALESCE(v.source_url, k.source_url) AS source_url,
                COALESCE(1.0 / (:rrf_k + v.vrank), 0) +
                COALESCE(1.0 / (:rrf_k + k.krank), 0) +
                {boost_sql} AS rrf_score
            FROM vector_results v
            FULL OUTER JOIN keyword_results k ON v.id = k.id
        )
        SELECT id, section, section_title, zone_codes, chunk_text, municipality,
               chapter, municode_node_id, source_url, rrf_score
        FROM fused
        ORDER BY rrf_score DESC
        LIMIT :limit
    """)

    embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"
    pool_size = limit * 3  # fetch 3x from each source for better fusion

    params: dict = {
        "municipality": f"%{municipality}%",
        "municipality_raw": municipality,
        "zone_code": zone_code,
        "query": zone_code,
        "embedding": embedding_str,
        "rrf_k": RRF_K,
        "pool": pool_size,
        "limit": limit,
    }
    if zone_code_boost:
        params["zone_code_boost"] = zone_code_boost

    result = await session.execute(query, params)
    rows = result.fetchall()

    return [
        SearchResult(
            section=row.section or "",
            section_title=row.section_title or "",
            zone_codes=row.zone_codes or [],
            chunk_text=row.chunk_text,
            score=float(row.rrf_score),
            municipality=row.municipality,
            chunk_id=int(row.id) if row.id is not None else None,
            chapter=row.chapter,
            municode_node_id=row.municode_node_id,
            source_url=row.source_url,
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
    query = text(f"""
        SELECT id, section, section_title, zone_codes, chunk_text, municipality,
               chapter, municode_node_id, source_url,
               ts_rank(search_vector, plainto_tsquery(:query)) AS rank
        FROM ordinance_chunks
        WHERE {_MUNI_WHERE}
          AND (search_vector @@ plainto_tsquery(:query)
               OR :zone_code = ANY(zone_codes))
        ORDER BY rank DESC
        LIMIT :limit
    """)

    result = await session.execute(
        query,
        {
            "municipality": f"%{municipality}%",
            "municipality_raw": municipality,
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
            chunk_id=int(row.id) if row.id is not None else None,
            chapter=row.chapter,
            municode_node_id=row.municode_node_id,
            source_url=row.source_url,
        )
        for row in rows
    ]
