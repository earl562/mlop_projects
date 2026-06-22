from __future__ import annotations

from typing import assert_never

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.exc import SQLAlchemyError

from plotlot.api import lookup_snapshot_eval_responses as eval_responses
from plotlot.pipeline.lookup_snapshot_eval import LOOKUP_CORRECTNESS_SUITE
from plotlot.pipeline.lookup_snapshot_golden_eval_runner import (
    GoldenEvalItemEvidenceError,
    LookupSnapshotGoldenEvalBatchItemSpec,
    LookupSnapshotGoldenEvalBatchMissingGoldenCases,
    LookupSnapshotGoldenEvalBatchMissingSnapshots,
    LookupSnapshotGoldenEvalBatchRan,
    LookupSnapshotGoldenEvalBatchSpec,
    missing_golden_case_message,
    missing_snapshot_message,
    run_lookup_snapshot_golden_eval_batch,
)

router = APIRouter(prefix="/api/v1", tags=["lookup-snapshot-golden-evals"])


class LookupSnapshotGoldenEvalBatchItem(BaseModel):
    snapshot_id: str = Field(min_length=1)
    address: str | None = Field(default=None, min_length=1)
    case_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _requires_address_or_case_id(self) -> "LookupSnapshotGoldenEvalBatchItem":
        if self.address is None and self.case_id is None:
            raise GoldenEvalItemEvidenceError
        return self

    def to_spec(self) -> LookupSnapshotGoldenEvalBatchItemSpec:
        return LookupSnapshotGoldenEvalBatchItemSpec(
            snapshot_id=self.snapshot_id,
            address=self.address,
            case_id=self.case_id,
        )


class LookupSnapshotGoldenEvalBatchRequest(BaseModel):
    suite: str = Field(default=LOOKUP_CORRECTNESS_SUITE, min_length=1)
    snapshots: tuple[LookupSnapshotGoldenEvalBatchItem, ...] = Field(min_length=1)
    use_latest_baseline: bool = True

    def to_spec(self) -> LookupSnapshotGoldenEvalBatchSpec:
        return LookupSnapshotGoldenEvalBatchSpec(
            suite=self.suite,
            items=tuple(item.to_spec() for item in self.snapshots),
            use_latest_baseline=self.use_latest_baseline,
        )


@router.post("/lookup-snapshots/evals/batch/golden")
async def evaluate_lookup_snapshot_golden_batch(
    request: LookupSnapshotGoldenEvalBatchRequest,
):
    try:
        outcome = await run_lookup_snapshot_golden_eval_batch(request.to_spec())
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Lookup snapshot golden batch eval persistence failed",
        ) from exc

    match outcome:
        case LookupSnapshotGoldenEvalBatchRan(result=result):
            return eval_responses.batch_eval_response(result)
        case LookupSnapshotGoldenEvalBatchMissingSnapshots(snapshot_ids=snapshot_ids):
            raise HTTPException(status_code=404, detail=missing_snapshot_message(snapshot_ids))
        case LookupSnapshotGoldenEvalBatchMissingGoldenCases(keys=keys):
            raise HTTPException(status_code=422, detail=missing_golden_case_message(keys))
        case unreachable:
            assert_never(unreachable)
