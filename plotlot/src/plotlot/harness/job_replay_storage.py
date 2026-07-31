from __future__ import annotations

import json

from pydantic import JsonValue
from sqlalchemy import text

from plotlot.harness.job_models import (
    InvalidJobTransitionError,
    JobCreate,
    JobEvent,
    JobId,
    JobNotFoundError,
    JobRecord,
)
from plotlot.harness.job_rows import EVENT_COLUMNS, JOB_COLUMNS, event_from_row, job_from_row
from plotlot.harness.job_storage_context import JobStorageContext


class PostgresJobReplayMixin(JobStorageContext):
    async def dead_letters(self, tenant_id: str, limit: int = 100) -> list[JobRecord]:
        session = await self._session()
        async with session:
            await self._set_tenant(session, tenant_id)
            rows = (
                (
                    await session.execute(
                        text(
                            f"""SELECT {JOB_COLUMNS} FROM plotlot.jobs
                        WHERE tenant_id=:tenant_id AND status='dead_lettered'
                        ORDER BY updated_at, job_id LIMIT :limit"""
                        ),
                        {"tenant_id": tenant_id, "limit": limit},
                    )
                )
                .mappings()
                .all()
            )
            return [job_from_row(row) for row in rows]

    async def replay(
        self,
        *,
        tenant_id: str,
        job_id: JobId,
        idempotency_key: str,
        actor_id: str,
    ) -> JobRecord:
        original = await self.get(tenant_id, job_id)
        replay = await self.enqueue(
            JobCreate(
                tenant_id=tenant_id,
                idempotency_key=idempotency_key,
                body=original.body,
                max_attempts=original.max_attempts,
                replay_of_job_id=job_id,
            )
        )
        session = await self._session()
        async with session:
            async with session.begin():
                await self._set_tenant(session, tenant_id)
                await self._event(
                    session,
                    tenant_id,
                    replay.job_id,
                    "job.replayed",
                    {"actor_id": actor_id, "original_job_id": str(job_id)},
                )
        return replay

    async def requeue_dead_letter(
        self,
        *,
        tenant_id: str,
        job_id: JobId,
        actor_id: str,
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
                            SET status='queued', attempts=0, available_at=now(),
                                last_error=NULL, updated_at=now()
                            WHERE tenant_id=:tenant_id AND job_id=:job_id
                              AND status='dead_lettered'
                            RETURNING {JOB_COLUMNS}"""
                            ),
                            {"tenant_id": tenant_id, "job_id": str(job_id)},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    raise InvalidJobTransitionError(job_id, "dead-lettered")
                job = job_from_row(row)
                await self._event(
                    session,
                    tenant_id,
                    job_id,
                    "job.requeued",
                    {"actor_id": actor_id},
                )
                return job

    async def get(self, tenant_id: str, job_id: JobId) -> JobRecord:
        session = await self._session()
        async with session:
            await self._set_tenant(session, tenant_id)
            row = await self._get_in_session(session, tenant_id, job_id)
            if row is None:
                raise JobNotFoundError(tenant_id, job_id)
            return job_from_row(row)

    async def events(
        self,
        *,
        tenant_id: str,
        job_id: JobId,
        after_cursor: int,
        limit: int,
    ) -> list[JobEvent]:
        session = await self._session()
        async with session:
            await self._set_tenant(session, tenant_id)
            rows = (
                (
                    await session.execute(
                        text(
                            f"""SELECT {EVENT_COLUMNS} FROM plotlot.job_events
                        WHERE tenant_id=:tenant_id AND job_id=:job_id
                          AND cursor > :after_cursor
                        ORDER BY cursor LIMIT :limit"""
                        ),
                        {
                            "tenant_id": tenant_id,
                            "job_id": str(job_id),
                            "after_cursor": after_cursor,
                            "limit": limit,
                        },
                    )
                )
                .mappings()
                .all()
            )
            return [event_from_row(row) for row in rows]

    async def _get_in_session(
        self,
        session,
        tenant_id: str,
        job_id: JobId,
    ):
        return (
            (
                await session.execute(
                    text(
                        f"""SELECT {JOB_COLUMNS} FROM plotlot.jobs
                    WHERE tenant_id=:tenant_id AND job_id=:job_id"""
                    ),
                    {"tenant_id": tenant_id, "job_id": str(job_id)},
                )
            )
            .mappings()
            .one_or_none()
        )

    async def _event(
        self,
        session,
        tenant_id: str,
        job_id: JobId,
        event_type: str,
        payload: dict[str, JsonValue],
    ) -> None:
        await session.execute(
            text(
                """INSERT INTO plotlot.job_events
                (tenant_id, job_id, event_type, payload)
                VALUES (:tenant_id, :job_id, :event_type, CAST(:payload AS jsonb))"""
            ),
            {
                "tenant_id": tenant_id,
                "job_id": str(job_id),
                "event_type": event_type,
                "payload": json.dumps(payload),
            },
        )
