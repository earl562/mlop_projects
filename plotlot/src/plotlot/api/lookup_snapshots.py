from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from plotlot.api import lookup_snapshot_eval_responses as eval_responses
from plotlot.api.agent_runs import router as agent_runs_router
from plotlot.api.billing import check_analysis_limit
from plotlot.api.lookup_snapshot_creation import create_lookup_snapshot_domain
from plotlot.api.lookup_snapshot_responses import LookupSnapshotResponse
from plotlot.api.schemas import AnalyzeRequest
from plotlot.core.lookup_snapshot import LookupSnapshot
from plotlot.pipeline import lookup_snapshot_eval_batch_history as batch_history
from plotlot.pipeline.lookup_snapshot_eval import (
    LOOKUP_CORRECTNESS_SUITE,
    LookupSnapshotEvalResult,
    LookupSnapshotGoldenCase,
    score_lookup_snapshot,
)
from plotlot.pipeline.lookup_snapshot_eval_batch import (
    LookupSnapshotEvalBatch,
    LookupSnapshotEvalBatchCase,
    LookupSnapshotEvalBatchMetrics,
    LookupSnapshotEvalBatchResult,
    run_lookup_snapshot_eval_batch,
)
from plotlot.pipeline.lookup_snapshot_eval_batch_repository import (
    load_latest_lookup_snapshot_eval_batch_baseline,
    persist_lookup_snapshot_eval_batch,
)
from plotlot.pipeline.lookup_snapshot_eval_release_gate import (
    RELEASE_GATE_HISTORY_LIMIT,
    lookup_snapshot_release_gate_response,
)
from plotlot.pipeline.lookup_snapshot_eval_json import diffs_to_json, metrics_to_json
from plotlot.pipeline.lookup_snapshot_eval_repository import persist_lookup_snapshot_eval_result
from plotlot.pipeline.lookup_snapshot_repository import (
    PersistedLookupSnapshotRecord,
    load_lookup_snapshot_record,
)
from plotlot.pipeline.lookup_snapshot_serialization import (
    lookup_snapshot_from_dict,
    lookup_snapshot_to_dict,
)
from plotlot.pipeline.lookup_snapshot_store import (
    evidence_records_to_dicts,
    get_lookup_snapshot,
    trace_record_to_dict,
)
from plotlot.storage.db import get_session

router = APIRouter(prefix="/api/v1", tags=["lookup-snapshots"])
router.include_router(agent_runs_router)


class LookupSnapshotEvalBatchItem(BaseModel):
    snapshot_id: str = Field(min_length=1)
    case: LookupSnapshotGoldenCase


class LookupSnapshotEvalBatchRequest(BaseModel):
    suite: str = Field(default=LOOKUP_CORRECTNESS_SUITE, min_length=1)
    cases: tuple[LookupSnapshotEvalBatchItem, ...] = Field(min_length=1)
    use_latest_baseline: bool = True


@router.post("/lookup-snapshots", response_model=LookupSnapshotResponse)
async def create_lookup_snapshot(
    request: AnalyzeRequest,
    _: None = Depends(check_analysis_limit),
):
    snapshot = await create_lookup_snapshot_domain(request)
    return lookup_snapshot_to_dict(snapshot)


@router.get("/lookup-snapshots/{snapshot_id}", response_model=LookupSnapshotResponse)
async def get_lookup_snapshot_route(snapshot_id: str):
    stored = get_lookup_snapshot(snapshot_id)
    if stored is not None:
        return lookup_snapshot_to_dict(stored.snapshot)
    persisted = await _get_persisted_lookup_snapshot(snapshot_id)
    if persisted is not None:
        return persisted.snapshot_json
    raise HTTPException(status_code=404, detail="Lookup snapshot not found")


@router.get("/lookup-snapshots/{snapshot_id}/evidence")
async def get_lookup_snapshot_evidence(snapshot_id: str):
    stored = get_lookup_snapshot(snapshot_id)
    if stored is not None:
        return evidence_records_to_dicts(stored.evidence_records)
    persisted = await _get_persisted_lookup_snapshot(snapshot_id)
    if persisted is not None:
        return list(persisted.evidence_records)
    raise HTTPException(status_code=404, detail="Lookup snapshot not found")


@router.get("/lookup-snapshots/{snapshot_id}/trace")
async def get_lookup_snapshot_trace(snapshot_id: str):
    stored = get_lookup_snapshot(snapshot_id)
    if stored is not None:
        return trace_record_to_dict(stored.trace_record)
    persisted = await _get_persisted_lookup_snapshot(snapshot_id)
    if persisted is not None:
        return persisted.trace_record
    raise HTTPException(status_code=404, detail="Lookup snapshot not found")


@router.post("/lookup-snapshots/{snapshot_id}/evals")
async def evaluate_lookup_snapshot(
    snapshot_id: str,
    case: LookupSnapshotGoldenCase,
):
    snapshot = await _get_lookup_snapshot_domain(snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Lookup snapshot not found")

    result = score_lookup_snapshot(snapshot, case)
    try:
        await _persist_lookup_snapshot_eval(result)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Lookup snapshot eval persistence failed",
        ) from exc
    return {
        "lookup_snapshot_id": result.lookup_snapshot_id,
        "case_id": result.case.case_id,
        "status": result.status,
        "metrics": metrics_to_json(result.metrics),
        "diffs": diffs_to_json(result),
    }


@router.get("/lookup-snapshots/evals/batch/runs")
async def list_lookup_snapshot_eval_batch_runs(
    suite: str = Query(default=LOOKUP_CORRECTNESS_SUITE, min_length=1),
    limit: int = Query(default=20, ge=1, le=100),
):
    try:
        records = await _load_lookup_snapshot_eval_batch_history(suite, limit)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Lookup snapshot batch eval history unavailable",
        ) from exc
    return eval_responses.batch_eval_history_response(records)


@router.get("/lookup-snapshots/evals/batch/release-gate")
async def get_lookup_snapshot_eval_release_gate(
    suite: str = Query(default=LOOKUP_CORRECTNESS_SUITE, min_length=1),
):
    try:
        records = await _load_lookup_snapshot_eval_batch_history(
            suite,
            RELEASE_GATE_HISTORY_LIMIT,
        )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Lookup snapshot batch eval history unavailable",
        ) from exc
    return lookup_snapshot_release_gate_response(suite, records)


@router.post("/lookup-snapshots/evals/batch")
async def evaluate_lookup_snapshot_batch(request: LookupSnapshotEvalBatchRequest):
    batch_cases: list[LookupSnapshotEvalBatchCase] = []
    missing_snapshot_ids: list[str] = []

    for item in request.cases:
        snapshot = await _get_lookup_snapshot_domain(item.snapshot_id)
        if snapshot is None:
            missing_snapshot_ids.append(item.snapshot_id)
            continue
        batch_cases.append(LookupSnapshotEvalBatchCase(snapshot=snapshot, case=item.case))

    if missing_snapshot_ids:
        raise HTTPException(
            status_code=404,
            detail=f"Lookup snapshot not found: {', '.join(missing_snapshot_ids)}",
        )

    try:
        baseline = (
            await _load_lookup_snapshot_eval_batch_baseline(request.suite)
            if request.use_latest_baseline
            else None
        )
        result = run_lookup_snapshot_eval_batch(
            LookupSnapshotEvalBatch(
                suite=request.suite,
                cases=tuple(batch_cases),
                baseline=baseline,
            )
        )
        await _persist_lookup_snapshot_eval_batch(result)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Lookup snapshot batch eval persistence failed",
        ) from exc

    return eval_responses.batch_eval_response(result)


async def _persist_lookup_snapshot_eval(result: LookupSnapshotEvalResult) -> None:
    session = await get_session()
    try:
        await persist_lookup_snapshot_eval_result(session, result)
    finally:
        await session.close()


async def _load_lookup_snapshot_eval_batch_baseline(
    suite: str,
) -> LookupSnapshotEvalBatchMetrics | None:
    session = await get_session()
    try:
        return await load_latest_lookup_snapshot_eval_batch_baseline(session, suite)
    finally:
        await session.close()


async def _load_lookup_snapshot_eval_batch_history(
    suite: str,
    limit: int,
) -> tuple[batch_history.LookupSnapshotEvalBatchHistoryRecord, ...]:
    session = await get_session()
    try:
        return await batch_history.load_lookup_snapshot_eval_batch_history(
            session,
            suite=suite,
            limit=limit,
        )
    finally:
        await session.close()


async def _persist_lookup_snapshot_eval_batch(result: LookupSnapshotEvalBatchResult) -> None:
    session = await get_session()
    try:
        await persist_lookup_snapshot_eval_batch(session, result)
    finally:
        await session.close()


async def _get_lookup_snapshot_domain(snapshot_id: str) -> LookupSnapshot | None:
    stored = get_lookup_snapshot(snapshot_id)
    if stored is not None:
        return stored.snapshot
    persisted = await _get_persisted_lookup_snapshot(snapshot_id)
    if persisted is None:
        return None
    return lookup_snapshot_from_dict(persisted.snapshot_json)


async def _get_persisted_lookup_snapshot(
    snapshot_id: str,
) -> PersistedLookupSnapshotRecord | None:
    session = await get_session()
    try:
        return await load_lookup_snapshot_record(session, snapshot_id)
    finally:
        await session.close()
