from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import text

from plotlot.harness.job_models import (
    InvalidJobTransitionError,
    JobId,
    LeaseToken,
    OutboxId,
    OutboxRecord,
)
from plotlot.harness.job_rows import OUTBOX_ALIAS_COLUMNS, OUTBOX_COLUMNS, outbox_from_row
from plotlot.harness.job_storage_context import JobStorageContext


class PostgresOutboxMixin(JobStorageContext):
    async def claim_outbox(
        self,
        *,
        tenant_id: str,
        worker_id: str,
        lease_for: timedelta,
    ) -> OutboxRecord | None:
        session = await self._session()
        lease_token = str(uuid4())
        async with session:
            async with session.begin():
                await self._set_tenant(session, tenant_id)
                await session.execute(
                    text(
                        """UPDATE plotlot.job_outbox
                        SET status='dead_lettered', lease_owner=NULL, lease_token=NULL,
                            lease_expires_at=NULL
                        WHERE tenant_id=:tenant_id AND status='leased'
                          AND lease_expires_at <= now() AND attempts >= max_attempts"""
                    ),
                    {"tenant_id": tenant_id},
                )
                row = (
                    (
                        await session.execute(
                            text(
                                f"""WITH candidate AS (
                            SELECT tenant_id, outbox_id
                            FROM plotlot.job_outbox
                            WHERE tenant_id=:tenant_id
                              AND (
                                (status IN ('pending', 'retry_wait')
                                  AND available_at <= now())
                                OR (status='leased' AND lease_expires_at <= now())
                              )
                              AND attempts < max_attempts
                            ORDER BY available_at, created_at
                            FOR UPDATE SKIP LOCKED LIMIT 1
                            )
                            UPDATE plotlot.job_outbox AS item
                            SET status='leased', attempts=item.attempts + 1,
                                lease_owner=:worker_id, lease_token=:lease_token,
                                lease_expires_at=now() + :lease_seconds * interval '1 second'
                            FROM candidate
                            WHERE item.tenant_id=candidate.tenant_id
                              AND item.outbox_id=candidate.outbox_id
                            RETURNING {OUTBOX_ALIAS_COLUMNS}"""
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
                return outbox_from_row(row) if row is not None else None

    async def acknowledge_outbox(
        self,
        *,
        tenant_id: str,
        outbox_id: OutboxId,
        lease_token: LeaseToken,
        provider_receipt_id: str,
    ) -> OutboxRecord:
        session = await self._session()
        async with session:
            async with session.begin():
                await self._set_tenant(session, tenant_id)
                row = (
                    (
                        await session.execute(
                            text(
                                f"""UPDATE plotlot.job_outbox
                            SET status='sent', sent_at=now(), lease_owner=NULL,
                                lease_token=NULL, lease_expires_at=NULL
                            WHERE tenant_id=:tenant_id AND outbox_id=:outbox_id
                              AND lease_token=:lease_token
                              AND status='leased' AND lease_expires_at > now()
                            RETURNING {OUTBOX_COLUMNS}"""
                            ),
                            {
                                "tenant_id": tenant_id,
                                "outbox_id": str(outbox_id),
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
                                    f"""SELECT {OUTBOX_ALIAS_COLUMNS},
                                receipt.provider_receipt_id
                                FROM plotlot.job_outbox AS item
                                JOIN plotlot.notification_receipts AS receipt
                                  ON receipt.tenant_id=item.tenant_id
                                 AND receipt.outbox_id=item.outbox_id
                                WHERE item.tenant_id=:tenant_id
                                  AND item.outbox_id=:outbox_id"""
                                ),
                                {"tenant_id": tenant_id, "outbox_id": str(outbox_id)},
                            )
                        )
                        .mappings()
                        .one_or_none()
                    )
                    if (
                        existing is not None
                        and existing["status"] == "sent"
                        and existing["provider_receipt_id"] == provider_receipt_id
                    ):
                        return outbox_from_row(existing)
                    raise InvalidJobTransitionError(
                        job_id=JobId(str(outbox_id)),
                        expected="active outbox lease",
                    )
                await session.execute(
                    text(
                        """INSERT INTO plotlot.notification_receipts
                        (tenant_id, outbox_id, job_id, provider_receipt_id)
                        VALUES (:tenant_id, :outbox_id, :job_id, :provider_receipt_id)
                        ON CONFLICT (tenant_id, outbox_id) DO NOTHING"""
                    ),
                    {
                        "tenant_id": row["tenant_id"],
                        "outbox_id": row["outbox_id"],
                        "job_id": row["job_id"],
                        "provider_receipt_id": provider_receipt_id,
                    },
                )
                return outbox_from_row(row)

    async def fail_outbox(
        self,
        *,
        tenant_id: str,
        outbox_id: OutboxId,
        lease_token: LeaseToken,
        error: str,
    ) -> OutboxRecord:
        session = await self._session()
        async with session:
            async with session.begin():
                await self._set_tenant(session, tenant_id)
                row = (
                    (
                        await session.execute(
                            text(
                                f"""UPDATE plotlot.job_outbox
                            SET status=CASE WHEN attempts >= max_attempts
                                 THEN 'dead_lettered' ELSE 'retry_wait' END,
                                available_at=now() + least(
                                  300, power(2, greatest(attempts - 1, 0))
                                ) * interval '1 second',
                                last_error=:error, lease_owner=NULL,
                                lease_token=NULL, lease_expires_at=NULL
                            WHERE tenant_id=:tenant_id AND outbox_id=:outbox_id
                              AND lease_token=:lease_token
                              AND status='leased'
                            RETURNING {OUTBOX_COLUMNS}"""
                            ),
                            {
                                "outbox_id": str(outbox_id),
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
                    raise InvalidJobTransitionError(
                        job_id=JobId(str(outbox_id)),
                        expected="leased outbox",
                    )
                return outbox_from_row(row)

    async def expire_outbox_lease_for_tests(self, outbox_id: OutboxId) -> None:
        session = await self._session()
        async with session:
            async with session.begin():
                await session.execute(
                    text(
                        """UPDATE plotlot.job_outbox
                        SET lease_expires_at=now() - interval '1 second'
                        WHERE outbox_id=:outbox_id"""
                    ),
                    {"outbox_id": str(outbox_id)},
                )
