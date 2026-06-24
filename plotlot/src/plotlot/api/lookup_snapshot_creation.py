from __future__ import annotations

from typing import Final

import anyio
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from plotlot.api.schemas import AnalyzeRequest
from plotlot.core.lookup_snapshot import LookupSnapshot
from plotlot.core.types import ZoningReport
from plotlot.pipeline.lookup import lookup_address
from plotlot.pipeline.lookup_snapshot import build_lookup_snapshot
from plotlot.pipeline.lookup_snapshot_repository import (
    LookupSnapshotPersistenceContext,
    persist_lookup_snapshot,
)
from plotlot.pipeline.lookup_snapshot_store import save_lookup_snapshot
from plotlot.storage.db import get_session

PIPELINE_TIMEOUT: Final = 120


async def create_lookup_snapshot_domain(request: AnalyzeRequest) -> LookupSnapshot:
    report = await _lookup_report(request)
    lookup_snapshot = report.lookup_snapshot
    if lookup_snapshot is None:
        lookup_snapshot = build_lookup_snapshot(report)

    stored = save_lookup_snapshot(lookup_snapshot)
    report.lookup_snapshot = stored.snapshot
    try:
        await persist_created_lookup_snapshot(stored.snapshot, request.address)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Lookup snapshot persistence failed",
        ) from exc
    return stored.snapshot


async def persist_created_lookup_snapshot(
    snapshot: LookupSnapshot,
    request_address: str,
) -> None:
    session = await get_session()
    try:
        await persist_lookup_snapshot(
            session,
            snapshot,
            LookupSnapshotPersistenceContext(request_address=request_address),
        )
    finally:
        await session.close()


async def _lookup_report(request: AnalyzeRequest) -> ZoningReport:
    try:
        with anyio.fail_after(PIPELINE_TIMEOUT):
            report: ZoningReport | None
            report = await lookup_address(request.address)
    except TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"Pipeline timed out after {PIPELINE_TIMEOUT}s",
        ) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if report is None:
        raise HTTPException(
            status_code=422,
            detail=f"Could not geocode address: {request.address}",
        )
    return report
