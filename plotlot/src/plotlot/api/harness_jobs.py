from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from plotlot.api.auth_types import Actor
from plotlot.harness.job_models import (
    IdempotencyConflictError,
    InvalidJobTransitionError,
    JobCreate,
    JobId,
    JobNotFoundError,
)
from plotlot.harness.job_queue import default_harness_job_storage
from plotlot.harness.job_queue_storage import PostgresJobQueueStorage
from plotlot.harness.run_cancellation import CancellationRequest, cancel_run


router = APIRouter(prefix="/api/v1/harness/jobs", tags=["harness-jobs"])
admin_router = APIRouter(
    prefix="/api/v1/admin/harness/jobs",
    tags=["admin", "harness-jobs"],
)


class HarnessJobCreateRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    body: dict[str, JsonValue]
    max_attempts: int = Field(default=3, ge=1, le=20)


class HarnessJobCancelRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    reason: str = Field(min_length=1, max_length=500)


class HarnessJobReplayRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    idempotency_key: str = Field(min_length=16, max_length=200)


def job_storage() -> PostgresJobQueueStorage:
    return default_harness_job_storage()


async def actor_for_jobs(request: Request) -> Actor:
    if not hasattr(request.state, "actor"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Verified tenant actor required",
        )
    actor: Actor = request.state.actor
    if actor.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Verified tenant actor required",
        )
    return actor


JobStorage = Annotated[PostgresJobQueueStorage, Depends(job_storage)]
VerifiedActor = Annotated[Actor, Depends(actor_for_jobs)]
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=16, max_length=200)]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_job(
    body: HarnessJobCreateRequest,
    response: Response,
    idempotency_key: IdempotencyKey,
    actor: VerifiedActor,
    storage: JobStorage,
) -> dict[str, JsonValue]:
    tenant_id = _tenant_id(actor)
    try:
        result = await storage.enqueue_result(
            JobCreate(
                tenant_id=tenant_id,
                idempotency_key=idempotency_key,
                body=body.body,
                max_attempts=body.max_attempts,
            )
        )
    except IdempotencyConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency key body conflict",
        ) from exc
    if result.reused:
        response.status_code = status.HTTP_200_OK
    return result.job.model_dump(mode="json")


@router.get("/{job_id}")
async def get_job(
    job_id: str,
    actor: VerifiedActor,
    storage: JobStorage,
) -> dict[str, JsonValue]:
    try:
        job = await storage.get(_tenant_id(actor), JobId(job_id))
    except JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found") from exc
    return job.model_dump(mode="json")


@router.get("/{job_id}/events")
async def list_job_events(
    job_id: str,
    actor: VerifiedActor,
    storage: JobStorage,
    after_cursor: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> dict[str, JsonValue]:
    events = await storage.events(
        tenant_id=_tenant_id(actor),
        job_id=JobId(job_id),
        after_cursor=after_cursor,
        limit=limit,
    )
    return {
        "items": [event.model_dump(mode="json") for event in events],
        "next_cursor": events[-1].cursor if events else after_cursor,
    }


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    body: HarnessJobCancelRequest,
    actor: VerifiedActor,
    storage: JobStorage,
) -> dict[str, JsonValue]:
    try:
        job = await cancel_run(
            storage,
            CancellationRequest(
                tenant_id=_tenant_id(actor),
                job_id=JobId(job_id),
                actor_id=actor.user_id,
                reason=body.reason,
            ),
        )
    except JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found") from exc
    except InvalidJobTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job cannot be cancelled from its current state",
        ) from exc
    return job.model_dump(mode="json")


@router.post("/{job_id}/replay", status_code=status.HTTP_201_CREATED)
async def replay_job(
    job_id: str,
    body: HarnessJobReplayRequest,
    actor: VerifiedActor,
    storage: JobStorage,
) -> dict[str, JsonValue]:
    try:
        replay = await storage.replay(
            tenant_id=_tenant_id(actor),
            job_id=JobId(job_id),
            idempotency_key=body.idempotency_key,
            actor_id=actor.user_id,
        )
    except JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found") from exc
    except IdempotencyConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency key body conflict",
        ) from exc
    return replay.model_dump(mode="json")


def _tenant_id(actor: Actor) -> str:
    if actor.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Verified tenant actor required",
        )
    return actor.tenant_id


@admin_router.get("/dead-letters")
async def list_dead_letters(
    actor: VerifiedActor,
    storage: JobStorage,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> dict[str, JsonValue]:
    jobs = await storage.dead_letters(_tenant_id(actor), limit)
    return {"items": [job.model_dump(mode="json") for job in jobs]}


@admin_router.post("/{job_id}/requeue")
async def requeue_dead_letter(
    job_id: str,
    actor: VerifiedActor,
    storage: JobStorage,
) -> dict[str, JsonValue]:
    try:
        job = await storage.requeue_dead_letter(
            tenant_id=_tenant_id(actor),
            job_id=JobId(job_id),
            actor_id=actor.user_id,
        )
    except InvalidJobTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only dead-lettered jobs can be requeued",
        ) from exc
    return job.model_dump(mode="json")


# Multi-agent runs share the same authenticated harness-job boundary.
from plotlot.api.agent_runs import router as agent_runs_router  # noqa: E402

router.include_router(agent_runs_router, dependencies=[Depends(actor_for_jobs)])
