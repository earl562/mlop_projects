from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.core.types import SearchResult
from plotlot.mcp.tool_types import JsonObject, JsonValue

type GetSession = Callable[[], Awaitable[AsyncSession]]


class HybridSearch(Protocol):
    async def __call__(
        self,
        session: AsyncSession,
        municipality: str,
        zone_code: str,
        limit: int = 10,
        embedding: list[float] | None = None,
        zone_code_boost: str | None = None,
    ) -> Sequence[SearchResult]: ...


@dataclass(frozen=True, slots=True)
class SearchZoningInput:
    municipality: str
    query: str
    limit: int = 10


@dataclass(frozen=True, slots=True)
class SearchZoningDeps:
    get_session: GetSession
    hybrid_search: HybridSearch


async def run_search_zoning(input_data: SearchZoningInput, deps: SearchZoningDeps) -> JsonObject:
    limit = max(1, min(25, input_data.limit))
    session = await deps.get_session()
    try:
        results = await deps.hybrid_search(
            session,
            input_data.municipality,
            input_data.query,
            limit=limit,
        )
    except (RuntimeError, SQLAlchemyError) as exc:
        return {
            "municipality": input_data.municipality,
            "query": input_data.query,
            "error": str(exc),
            "results": [],
        }
    finally:
        await session.close()

    return {
        "municipality": input_data.municipality,
        "query": input_data.query,
        "result_count": len(results),
        "results": [_result_payload(row) for row in results],
    }


def _result_payload(row: SearchResult) -> JsonObject:
    zone_codes: list[JsonValue] = [code for code in row.zone_codes]
    return {
        "section": row.section,
        "section_title": row.section_title,
        "chapter": row.chapter,
        "zone_codes": zone_codes,
        "score": round(row.score, 4),
        "chunk_text": row.chunk_text,
        "source_url": row.source_url,
    }
