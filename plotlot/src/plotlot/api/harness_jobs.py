from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from plotlot.harness.contracts import ExecutionMode, JobId, JsonObject, SourceMode
from plotlot.harness.fixture_runs import FixtureDealRunRequest
from plotlot.harness.job_queue import (
    HarnessJobCancellationRequest,
    HarnessJobNotFoundError,
    JobCancellationBlockedError,
    default_harness_job_queue,
)
from plotlot.harness.run_persistence import default_fixture_run_persistence_stores

router = APIRouter(prefix="/api/v1", tags=["harness-jobs"])


class HarnessJobCreateRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    address: str = Field(min_length=3)
    analysis_type: str = Field(default="acquisition_memo", min_length=1)
    source_mode: SourceMode = SourceMode.FIXTURE
    max_attempts: int = Field(default=3, ge=1)
    assumptions: JsonObject = Field(default_factory=dict)


class HarnessJobCancellationRequestBody(BaseModel):
    model_config = ConfigDict(frozen=True)

    reason: str = Field(default="Cancellation requested.", min_length=1)
    actor_user_id: str = Field(default="api", min_length=1)


@router.post("/harness/jobs")
async def harness_job_create(body: HarnessJobCreateRequest) -> JsonObject:
    if body.source_mode is not SourceMode.FIXTURE:
        raise HTTPException(
            status_code=501, detail="Only fixture harness jobs are wired in this slice"
        )
    job = default_harness_job_queue().create_analysis_job(
        FixtureDealRunRequest(
            address=body.address,
            analysis_type=body.analysis_type,
            source_mode=body.source_mode,
            assumptions=body.assumptions,
        ),
        max_attempts=body.max_attempts,
    )
    return job.model_dump(mode="json")


@router.get("/harness/jobs")
async def harness_jobs() -> JsonObject:
    jobs = default_harness_job_queue().list_jobs()
    return {"jobs": [job.model_dump(mode="json") for job in jobs]}


@router.get("/harness/jobs/{job_id}")
async def harness_job(job_id: str) -> JsonObject:
    try:
        job = default_harness_job_queue().get_job(JobId(job_id))
    except HarnessJobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return job.model_dump(mode="json")


@router.get("/harness/jobs/{job_id}/events")
async def harness_job_events(job_id: str) -> JsonObject:
    try:
        events = default_harness_job_queue().get_events(JobId(job_id))
    except HarnessJobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"job_id": job_id, "events": [event.model_dump(mode="json") for event in events]}


@router.post("/harness/jobs/{job_id}/cancel")
async def harness_job_cancel(
    job_id: str,
    body: HarnessJobCancellationRequestBody | None = None,
) -> JsonObject:
    request_body = body or HarnessJobCancellationRequestBody()
    try:
        job = default_harness_job_queue().cancel_job(
            HarnessJobCancellationRequest(
                job_id=JobId(job_id),
                actor_user_id=request_body.actor_user_id,
                reason=request_body.reason,
                execution_mode=ExecutionMode.API,
            )
        )
    except HarnessJobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except JobCancellationBlockedError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "job_cancellation_blocked",
                "reason": exc.reason,
                "current_status": exc.current_status,
            },
        ) from exc
    return job.model_dump(mode="json")


@router.post("/harness/jobs/run-next")
async def harness_job_run_next() -> JsonObject:
    job = await default_harness_job_queue().run_next_async(default_fixture_run_persistence_stores())
    if job is None:
        return {"status": "idle"}
    return job.model_dump(mode="json")
