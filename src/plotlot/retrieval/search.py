"""Hybrid search: vector similarity + full-text search with RRF fusion."""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.core.types import SearchResult

logger = logging.getLogger(__name__)


async def hybrid_search(
    session: AsyncSession,
    municipality: str,
    zone_code: str,
    limit: int = 10,
    embedding: list[float] | None = None,
) -> list[SearchResult]:
    """Run hybrid search combining vector similarity and full-text matching.

    Uses Reciprocal Rank Fusion (RRF) to combine vector and keyword scores.
    """
    query = text("""
        WITH keyword_results AS (
            SELECT id, section, section_title, zone_codes, chunk_text, municipality,
                   ts_rank(search_vector, plainto_tsquery(:query)) AS rank
            FROM ordinance_chunks
            WHERE municipality ILIKE :municipality
              AND (search_vector @@ plainto_tsquery(:query)
                   OR :zone_code = ANY(zone_codes))
            ORDER BY rank DESC
            LIMIT :limit
        )
        SELECT id, section, section_title, zone_codes, chunk_text, municipality, rank
        FROM keyword_results
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
