from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.mcp.tool_types import JsonObject
from plotlot.storage.models import OrdinanceChunk

type GetSession = Callable[[], Awaitable[AsyncSession]]


class CoverageRow(Protocol):
    municipality: str
    county: str | None
    state: str | None
    chunks: int


@dataclass(frozen=True, slots=True)
class CoverageDeps:
    get_session: GetSession


async def run_get_coverage(deps: CoverageDeps) -> JsonObject:
    session = await deps.get_session()
    try:
        result = await session.execute(
            select(
                OrdinanceChunk.municipality,
                OrdinanceChunk.county,
                OrdinanceChunk.state,
                func.count().label("chunks"),
            )
            .group_by(
                OrdinanceChunk.municipality,
                OrdinanceChunk.county,
                OrdinanceChunk.state,
            )
            .order_by(func.count().desc())
        )
        rows: list[CoverageRow] = list(result.fetchall())
    except (RuntimeError, SQLAlchemyError) as exc:
        return {"error": str(exc), "municipalities": [], "total_chunks": 0}
    finally:
        await session.close()

    total_chunks = sum(row.chunks for row in rows)
    return {
        "total_municipalities": len(rows),
        "total_chunks": total_chunks,
        "municipalities": [
            {
                "municipality": row.municipality,
                "county": row.county,
                "state": row.state,
                "chunks": row.chunks,
            }
            for row in rows
        ],
    }
