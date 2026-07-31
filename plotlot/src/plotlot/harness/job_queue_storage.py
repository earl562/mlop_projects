from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.harness.job_models import (
    IdempotencyConflictError,
    InvalidJobTransitionError,
    JobCreate,
    JobEnqueueResult,
    JobId,
    JobRecord,
    LeaseToken,
)
from plotlot.harness.job_inspection_storage import PostgresJobInspectionMixin
from plotlot.harness.job_hashing import body_sha256
from plotlot.harness.job_mutation_storage import PostgresJobMutationMixin
from plotlot.harness.job_outbox_storage import PostgresOutboxMixin
from plotlot.harness.job_replay_storage import PostgresJobReplayMixin
from plotlot.harness.job_rows import JOB_ALIAS_COLUMNS, JOB_COLUMNS, job_from_row


SessionProvider = Callable[[], Awaitable[AsyncSession]]


class PostgresJobQueueStorage(
    PostgresJobMutationMixin,
    PostgresJobReplayMixin,
    PostgresOutboxMixin,
    PostgresJobInspectionMixin,
):
    def __init__(self, session_provider: SessionProvider) -> None:
        self._session_provider = session_provider

    async def _session(self) -> AsyncSession:
        return await self._session_provider()

    @staticmethod
    async def _set_tenant(session: AsyncSession, tenant_id: str) -> None:
        await session.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": tenant_id},
        )

    async def enqueue(self, command: JobCreate) -> JobRecord:
        return (await self.enqueue_result(command)).job

    async def enqueue_result(self, command: JobCreate) -> JobEnqueueResult:
        command_sha256 = body_sha256(command.body)
        job_id = JobId(str(uuid4()))
        session = await self._session()
        async with session:
            async with session.begin():
                await self._set_tenant(session, command.tenant_id)
                row = (
                    (
                        await session.execute(
                            text(
                                f"""INSERT INTO plotlot.jobs
                            (tenant_id, job_id, idempotency_key, body_sha256, body,
                             max_attempts, replay_of_job_id)
                            VALUES (:tenant_id, :job_id, :idempotency_key, :body_sha256,
                                    CAST(:body AS jsonb), :max_attempts, :replay_of_job_id)
                            ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
                            RETURNING {JOB_COLUMNS}"""
                            ),
                            {
                                "tenant_id": command.tenant_id,
                                "job_id": str(job_id),
                                "idempotency_key": command.idempotency_key,
                                "body_sha256": command_sha256,
                                "body": json.dumps(command.body),
                                "max_attempts": command.max_attempts,
                                "replay_of_job_id": command.replay_of_job_id,
                            },
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    row = (
                        (
                            await session.execute(
                                text(
                                    f"""SELECT {JOB_COLUMNS} FROM plotlot.jobs
                                WHERE tenant_id=:tenant_id
                                  AND idempotency_key=:idempotency_key"""
                                ),
                                {
                                    "tenant_id": command.tenant_id,
                                    "idempotency_key": command.idempotency_key,
                                },
                            )
                        )
                        .mappings()
                        .one()
                    )
                    if row["body_sha256"] != command_sha256:
                        raise IdempotencyConflictError(
                            command.tenant_id,
                            command.idempotency_key,
                        )
                    return JobEnqueueResult(job=job_from_row(row), reused=True)
                await self._event(
                    session,
                    command.tenant_id,
                    job_id,
                    "job.queued",
                    {},
                )
                return JobEnqueueResult(job=job_from_row(row), reused=False)

    async def claim(
        self,
        *,
        tenant_id: str,
        worker_id: str,
        lease_for: timedelta,
    ) -> JobRecord | None:
        session = await self._session()
        lease_token = str(uuid4())
        async with session:
            async with session.begin():
                await self._set_tenant(session, tenant_id)
                await session.execute(
                    text(
                        """UPDATE plotlot.jobs
                        SET status='dead_lettered', lease_owner=NULL, lease_token=NULL,
                            lease_expires_at=NULL, last_error='lease expired at retry limit',
                            updated_at=now()
                        WHERE tenant_id=:tenant_id
                          AND status IN ('leased', 'running')
                          AND lease_expires_at <= now() AND attempts >= max_attempts"""
                    ),
                    {"tenant_id": tenant_id},
                )
                row = (
                    (
                        await session.execute(
                            text(
                                f"""WITH candidate AS (
                            SELECT tenant_id, job_id FROM plotlot.jobs
                            WHERE tenant_id=:tenant_id AND attempts < max_attempts
                              AND (
                                (status IN ('queued', 'retry_wait')
                                  AND available_at <= now())
                                OR (status IN ('leased', 'running')
                                  AND lease_expires_at <= now())
                              )
                            ORDER BY available_at, created_at
                            FOR UPDATE SKIP LOCKED LIMIT 1
                            )
                            UPDATE plotlot.jobs AS job
                            SET status='leased', attempts=job.attempts + 1,
                                lease_owner=:worker_id, lease_token=:lease_token,
                                lease_expires_at=now() + :lease_seconds * interval '1 second',
                                updated_at=now()
                            FROM candidate
                            WHERE job.tenant_id=candidate.tenant_id
                              AND job.job_id=candidate.job_id
                            RETURNING {JOB_ALIAS_COLUMNS}"""
                            ),
                            {
                                "tenant_id": tenant_id,
                                "worker_id": worker_id,
                                "lease_token": lease_token,
                                "lease_seconds": lease_for.total_seconds(),
                            },
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    return None
                job = job_from_row(row)
                await self._event(session, tenant_id, job.job_id, "job.claimed", {})
                return job

    async def heartbeat(
        self,
        tenant_id: str,
        job_id: JobId,
        lease_token: LeaseToken,
        *,
        lease_for: timedelta,
    ) -> bool:
        session = await self._session()
        async with session:
            async with session.begin():
                await self._set_tenant(session, tenant_id)
                updated = await session.scalar(
                    text(
                        """UPDATE plotlot.jobs
                        SET lease_expires_at=now() + :lease_seconds * interval '1 second',
                            updated_at=now()
                        WHERE tenant_id=:tenant_id AND job_id=:job_id
                          AND lease_token=:lease_token
                          AND status IN ('leased', 'running')
                          AND lease_expires_at > now()
                        RETURNING 1"""
                    ),
                    {
                        "job_id": str(job_id),
                        "tenant_id": tenant_id,
                        "lease_token": str(lease_token),
                        "lease_seconds": lease_for.total_seconds(),
                    },
                )
                return updated is not None

    async def fail(
        self,
        tenant_id: str,
        job_id: JobId,
        lease_token: LeaseToken,
        error: str,
    ) -> JobRecord:
        session = await self._session()
        async with session:
            async with session.begin():
                await self._set_tenant(session, tenant_id)
                row = (
                    (
                        await session.execute(
                            text(
                                f"""UPDATE plotlot.jobs
                            SET status=CASE WHEN attempts >= max_attempts
                                 THEN 'dead_lettered' ELSE 'retry_wait' END,
                                available_at=now() + least(
                                  300, power(2, greatest(attempts - 1, 0))
                                ) * interval '1 second',
                                last_error=:error, lease_owner=NULL,
                                lease_token=NULL, lease_expires_at=NULL, updated_at=now()
                            WHERE tenant_id=:tenant_id AND job_id=:job_id
                              AND lease_token=:lease_token
                              AND status IN ('leased', 'running')
                            RETURNING {JOB_COLUMNS}"""
                            ),
                            {
                                "job_id": str(job_id),
                                "tenant_id": tenant_id,
                                "lease_token": str(lease_token),
                                "error": error,
                            },
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    raise InvalidJobTransitionError(job_id, "active lease")
                job = job_from_row(row)
                await self._event(session, job.tenant_id, job_id, f"job.{job.status}", {})
                return job
