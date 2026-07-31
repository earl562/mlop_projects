from __future__ import annotations

import json
from uuid import uuid4

from pydantic import JsonValue
from sqlalchemy import text

from plotlot.harness.job_models import (
    InvalidJobTransitionError,
    JobId,
    JobNotFoundError,
    JobRecord,
    LeaseToken,
)
from plotlot.harness.job_rows import JOB_ALIAS_COLUMNS, JOB_COLUMNS, job_from_row
from plotlot.harness.job_storage_context import JobStorageContext


class PostgresJobMutationMixin(JobStorageContext):
    async def mark_started(
        self,
        tenant_id: str,
        job_id: JobId,
        lease_token: LeaseToken,
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
                            SET status='running', updated_at=now()
                            WHERE tenant_id=:tenant_id AND job_id=:job_id
                              AND lease_token=:lease_token
                              AND status='leased' AND lease_expires_at > now()
                            RETURNING {JOB_COLUMNS}"""
                            ),
                            {
                                "tenant_id": tenant_id,
                                "job_id": str(job_id),
                                "lease_token": str(lease_token),
                            },
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    raise InvalidJobTransitionError(job_id, "active leased state")
                job = job_from_row(row)
                await self._event(session, job.tenant_id, job_id, "job.started", {})
                return job

    async def complete(
        self,
        *,
        tenant_id: str,
        job_id: JobId,
        lease_token: LeaseToken,
        engine_run_id: str,
        engine_revision_id: str,
        notification: dict[str, JsonValue],
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
                            SET status='completed', lease_owner=NULL, lease_token=NULL,
                                lease_expires_at=NULL, updated_at=now()
                            WHERE tenant_id=:tenant_id AND job_id=:job_id
                              AND lease_token=:lease_token
                              AND status IN ('leased', 'running')
                              AND lease_expires_at > now()
                            RETURNING {JOB_COLUMNS}"""
                            ),
                            {
                                "tenant_id": tenant_id,
                                "job_id": str(job_id),
                                "lease_token": str(lease_token),
                            },
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    existing = (
                        (
                            await session.execute(
                                text(
                                    f"""SELECT {JOB_ALIAS_COLUMNS}, result.engine_run_id,
                                result.engine_revision_id
                                FROM plotlot.jobs AS job
                                LEFT JOIN plotlot.job_terminal_results AS result
                                  ON result.tenant_id=job.tenant_id
                                 AND result.job_id=job.job_id
                                WHERE job.tenant_id=:tenant_id
                                  AND job.job_id=:job_id"""
                                ),
                                {"tenant_id": tenant_id, "job_id": str(job_id)},
                            )
                        )
                        .mappings()
                        .one_or_none()
                    )
                    if (
                        existing is not None
                        and existing["status"] == "completed"
                        and existing["engine_run_id"] == engine_run_id
                        and existing["engine_revision_id"] == engine_revision_id
                    ):
                        return job_from_row(existing)
                    raise InvalidJobTransitionError(job_id, "active lease")
                job = job_from_row(row)
                await session.execute(
                    text(
                        """INSERT INTO plotlot.job_terminal_results
                        (tenant_id, job_id, engine_run_id, engine_revision_id)
                        VALUES (:tenant_id, :job_id, :engine_run_id, :engine_revision_id)
                        ON CONFLICT (tenant_id, job_id) DO NOTHING"""
                    ),
                    {
                        "tenant_id": job.tenant_id,
                        "job_id": str(job_id),
                        "engine_run_id": engine_run_id,
                        "engine_revision_id": engine_revision_id,
                    },
                )
                await session.execute(
                    text(
                        """INSERT INTO plotlot.job_outbox
                        (tenant_id, outbox_id, job_id, receipt_key, payload)
                        VALUES (:tenant_id, :outbox_id, :job_id, :receipt_key,
                                CAST(:payload AS jsonb))
                        ON CONFLICT (tenant_id, receipt_key) DO NOTHING"""
                    ),
                    {
                        "tenant_id": job.tenant_id,
                        "outbox_id": str(uuid4()),
                        "job_id": str(job_id),
                        "receipt_key": f"job-terminal:{job_id}",
                        "payload": json.dumps(notification),
                    },
                )
                await self._event(session, job.tenant_id, job_id, "job.completed", {})
                return job

    async def cancel(
        self,
        *,
        tenant_id: str,
        job_id: JobId,
        actor_id: str,
        reason: str,
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
                            SET status='cancelled', lease_owner=NULL, lease_token=NULL,
                                lease_expires_at=NULL, updated_at=now()
                            WHERE tenant_id=:tenant_id AND job_id=:job_id
                              AND status IN (
                                'queued', 'leased', 'running', 'retry_wait'
                              )
                            RETURNING {JOB_COLUMNS}"""
                            ),
                            {"tenant_id": tenant_id, "job_id": str(job_id)},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    existing = await self._get_in_session(session, tenant_id, job_id)
                    if existing is None:
                        raise JobNotFoundError(tenant_id, job_id)
                    raise InvalidJobTransitionError(job_id, "cancellable state")
                job = job_from_row(row)
                await self._event(
                    session,
                    tenant_id,
                    job_id,
                    "job.cancelled",
                    {"actor_id": actor_id, "reason": reason},
                )
                return job
