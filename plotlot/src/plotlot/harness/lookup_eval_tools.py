from __future__ import annotations

from collections.abc import Mapping
from typing import Final, assert_never

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy.exc import SQLAlchemyError

from plotlot.land_use.models import ToolContext
from plotlot.harness.lookup_eval_tool_response import lookup_eval_batch_tool_response
from plotlot.pipeline.lookup_snapshot_eval import LOOKUP_CORRECTNESS_SUITE
from plotlot.pipeline.lookup_snapshot_eval_batch_history import (
    LookupSnapshotEvalBatchHistoryRecord,
    load_lookup_snapshot_eval_batch_history,
)
from plotlot.pipeline.lookup_snapshot_eval_release_gate import (
    RELEASE_GATE_HISTORY_LIMIT,
    lookup_snapshot_eval_run_to_json,
    lookup_snapshot_release_gate_response,
)
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
from plotlot.pipeline.lookup_snapshot_json import JsonValue
from plotlot.storage.db import get_session

DEFAULT_EVAL_HISTORY_LIMIT: Final = 20


class ListLookupEvalRunsArgs(BaseModel):
    model_config = ConfigDict(frozen=True)

    suite: str = Field(default=LOOKUP_CORRECTNESS_SUITE, min_length=1)
    limit: int = Field(default=DEFAULT_EVAL_HISTORY_LIMIT, ge=1, le=100)


class AssessLookupReleaseGateArgs(BaseModel):
    model_config = ConfigDict(frozen=True)

    suite: str = Field(default=LOOKUP_CORRECTNESS_SUITE, min_length=1)


class RunLookupGoldenEvalBatchItemArgs(BaseModel):
    model_config = ConfigDict(frozen=True)

    snapshot_id: str = Field(min_length=1)
    address: str | None = Field(default=None, min_length=1)
    case_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _requires_address_or_case_id(self) -> "RunLookupGoldenEvalBatchItemArgs":
        if self.address is None and self.case_id is None:
            raise GoldenEvalItemEvidenceError
        return self

    def to_spec(self) -> LookupSnapshotGoldenEvalBatchItemSpec:
        return LookupSnapshotGoldenEvalBatchItemSpec(
            snapshot_id=self.snapshot_id,
            address=self.address,
            case_id=self.case_id,
        )


class RunLookupGoldenEvalBatchArgs(BaseModel):
    model_config = ConfigDict(frozen=True)

    suite: str = Field(default=LOOKUP_CORRECTNESS_SUITE, min_length=1)
    snapshots: tuple[RunLookupGoldenEvalBatchItemArgs, ...] = Field(min_length=1)
    use_latest_baseline: bool = True

    def to_spec(self) -> LookupSnapshotGoldenEvalBatchSpec:
        return LookupSnapshotGoldenEvalBatchSpec(
            suite=self.suite,
            items=tuple(item.to_spec() for item in self.snapshots),
            use_latest_baseline=self.use_latest_baseline,
        )


async def handle_list_lookup_eval_runs(
    args: Mapping[str, JsonValue],
    _context: ToolContext,
) -> dict[str, JsonValue]:
    try:
        parsed = ListLookupEvalRunsArgs.model_validate(args)
    except ValidationError as exc:
        return {
            "status": "error",
            "message": str(exc),
            "runs": [],
            "run_count": 0,
            "evidence": [],
        }

    records = await _load_history_records(parsed.suite, parsed.limit)

    return {
        "status": "success",
        "suite": parsed.suite,
        "run_count": len(records),
        "runs": [lookup_snapshot_eval_run_to_json(record) for record in records],
        "evidence": [],
    }


async def handle_assess_lookup_release_gate(
    args: Mapping[str, JsonValue],
    _context: ToolContext,
) -> dict[str, JsonValue]:
    try:
        parsed = AssessLookupReleaseGateArgs.model_validate(args)
    except ValidationError as exc:
        return {
            "status": "error",
            "message": str(exc),
            "decision": "blocked",
            "release_blocked": True,
            "blockers": [],
            "evidence": [],
        }

    records = await _load_history_records(parsed.suite, RELEASE_GATE_HISTORY_LIMIT)
    return lookup_snapshot_release_gate_response(parsed.suite, records)


async def handle_run_lookup_golden_eval_batch(
    args: Mapping[str, JsonValue],
    _context: ToolContext,
) -> dict[str, JsonValue]:
    try:
        parsed = RunLookupGoldenEvalBatchArgs.model_validate(args)
    except ValidationError as exc:
        return {
            "status": "error",
            "message": str(exc),
            "evidence": [],
        }

    try:
        outcome = await run_lookup_snapshot_golden_eval_batch(parsed.to_spec())
    except SQLAlchemyError:
        return {
            "status": "error",
            "message": "Lookup snapshot golden batch eval persistence failed",
            "evidence": [],
        }

    match outcome:
        case LookupSnapshotGoldenEvalBatchRan(result=result):
            return lookup_eval_batch_tool_response(result)
        case LookupSnapshotGoldenEvalBatchMissingSnapshots(snapshot_ids=snapshot_ids):
            return {
                "status": "blocked",
                "message": missing_snapshot_message(snapshot_ids),
                "missing_snapshot_ids": list(snapshot_ids),
                "evidence": [],
            }
        case LookupSnapshotGoldenEvalBatchMissingGoldenCases(keys=keys):
            return {
                "status": "blocked",
                "message": missing_golden_case_message(keys),
                "missing_golden_keys": list(keys),
                "evidence": [],
            }
        case unreachable:
            assert_never(unreachable)


async def _load_history_records(
    suite: str,
    limit: int,
) -> tuple[LookupSnapshotEvalBatchHistoryRecord, ...]:
    session = await get_session()
    try:
        return await load_lookup_snapshot_eval_batch_history(
            session,
            suite=suite,
            limit=limit,
        )
    finally:
        await session.close()
