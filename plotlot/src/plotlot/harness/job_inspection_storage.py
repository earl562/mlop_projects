from __future__ import annotations

from sqlalchemy import text

from plotlot.harness.job_models import JobId
from plotlot.harness.job_storage_context import JobStorageContext


class PostgresJobInspectionMixin(JobStorageContext):
    async def count_jobs(self, tenant_id: str) -> int:
        return await self._count(
            "plotlot.jobs",
            "tenant_id=:tenant_id",
            {"tenant_id": tenant_id},
        )

    async def count_terminal_results(self, tenant_id: str, job_id: JobId) -> int:
        return await self._count(
            "plotlot.job_terminal_results",
            "tenant_id=:tenant_id AND job_id=:job_id",
            {"tenant_id": tenant_id, "job_id": str(job_id)},
        )

    async def count_outbox(self, tenant_id: str, job_id: JobId) -> int:
        return await self._count(
            "plotlot.job_outbox",
            "tenant_id=:tenant_id AND job_id=:job_id",
            {"tenant_id": tenant_id, "job_id": str(job_id)},
        )

    async def count_notification_receipts(self, tenant_id: str, job_id: JobId) -> int:
        return await self._count(
            "plotlot.notification_receipts",
            "tenant_id=:tenant_id AND job_id=:job_id",
            {"tenant_id": tenant_id, "job_id": str(job_id)},
        )

    async def _count(
        self,
        table: str,
        predicate: str,
        parameters: dict[str, str],
    ) -> int:
        session = await self._session()
        async with session:
            value = await session.scalar(
                text(f"SELECT count(*) FROM {table} WHERE {predicate}"),
                parameters,
            )
            return int(value or 0)

    async def make_retry_ready_for_tests(self, job_id: JobId) -> None:
        await self._test_update(
            """UPDATE plotlot.jobs SET available_at=now() - interval '1 second'
            WHERE job_id=:identity""",
            str(job_id),
        )

    async def expire_job_lease_for_tests(self, job_id: JobId) -> None:
        await self._test_update(
            """UPDATE plotlot.jobs SET lease_expires_at=now() - interval '1 second'
            WHERE job_id=:identity""",
            str(job_id),
        )

    async def _test_update(self, statement: str, identity: str) -> None:
        session = await self._session()
        async with session:
            async with session.begin():
                await session.execute(text(statement), {"identity": identity})

    async def clear_for_tests(self) -> None:
        session = await self._session()
        async with session:
            async with session.begin():
                await session.execute(
                    text(
                        """TRUNCATE plotlot.notification_receipts, plotlot.job_outbox,
                        plotlot.job_terminal_results, plotlot.job_events, plotlot.jobs
                        RESTART IDENTITY CASCADE"""
                    )
                )
