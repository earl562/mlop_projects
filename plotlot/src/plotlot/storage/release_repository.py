from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import IntegrityError

from plotlot.security.release import (
    ReleaseConflictError,
    ReleaseRequest,
    ReleaseRevision,
    RevisionCoordinate,
)
from plotlot.storage.db import get_session


class PostgresReleaseRepository:
    async def get_revision(
        self,
        coordinate: RevisionCoordinate,
    ) -> ReleaseRevision | None:
        session = await get_session()
        try:
            row = (
                (
                    await session.execute(
                        text(
                            """SELECT tenant_id, analysis_id, revision_id,
                        revision_sha256, is_clean
                        FROM plotlot.analysis_revision_heads
                        WHERE tenant_id=:tenant_id
                          AND analysis_id=:analysis_id
                          AND revision_id=:revision_id
                          AND revision_sha256=:revision_sha256"""
                        ),
                        {
                            "tenant_id": coordinate.tenant_id,
                            "analysis_id": coordinate.analysis_id,
                            "revision_id": coordinate.revision_id,
                            "revision_sha256": coordinate.revision_sha256,
                        },
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            return ReleaseRevision(
                tenant_id=row["tenant_id"],
                analysis_id=row["analysis_id"],
                revision_id=row["revision_id"],
                revision_sha256=row["revision_sha256"],
                is_clean=row["is_clean"],
            )
        finally:
            await session.close()

    async def create(self, request: ReleaseRequest) -> ReleaseRequest:
        session = await get_session()
        try:
            await session.execute(
                text(
                    """INSERT INTO plotlot.external_release_requests (
                    tenant_id, request_id, analysis_id, revision_id,
                    revision_sha256, requested_by
                    ) VALUES (
                    :tenant_id, :request_id, :analysis_id, :revision_id,
                    :revision_sha256, :requested_by
                    )"""
                ),
                {
                    "tenant_id": request.revision.tenant_id,
                    "request_id": request.request_id,
                    "analysis_id": request.revision.analysis_id,
                    "revision_id": request.revision.revision_id,
                    "revision_sha256": request.revision.revision_sha256,
                    "requested_by": request.requested_by,
                },
            )
            await session.commit()
            return request
        except IntegrityError as exc:
            await session.rollback()
            raise ReleaseConflictError(request.request_id) from exc
        finally:
            await session.close()

    async def get(self, request_id: str) -> ReleaseRequest | None:
        session = await get_session()
        try:
            row = (
                (
                    await session.execute(
                        text(
                            """SELECT tenant_id, request_id, analysis_id, revision_id,
                        revision_sha256, requested_by, reviewed_by, status
                        FROM plotlot.external_release_requests
                        WHERE request_id=:request_id"""
                        ),
                        {"request_id": request_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            return self._release_request(row) if row is not None else None
        finally:
            await session.close()

    async def compare_and_release(
        self,
        request_id: str,
        reviewer_user_id: str,
    ) -> ReleaseRequest | None:
        session = await get_session()
        try:
            row = (
                (
                    await session.execute(
                        text(
                            """UPDATE plotlot.external_release_requests AS release
                        SET status='released',
                            reviewed_by=:reviewed_by
                        WHERE release.request_id=:request_id
                          AND release.status='pending'
                          AND release.requested_by<>:reviewed_by
                          AND EXISTS (
                            SELECT 1
                            FROM plotlot.analysis_revision_heads AS head
                            WHERE head.tenant_id=release.tenant_id
                              AND head.analysis_id=release.analysis_id
                              AND head.revision_id=release.revision_id
                              AND head.revision_sha256=release.revision_sha256
                              AND head.is_clean
                          )
                        RETURNING tenant_id, request_id, analysis_id, revision_id,
                                  revision_sha256, requested_by, reviewed_by, status"""
                        ),
                        {
                            "request_id": request_id,
                            "reviewed_by": reviewer_user_id,
                        },
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                await session.rollback()
                raise ReleaseConflictError(request_id)
            await session.commit()
            return self._release_request(row)
        finally:
            await session.close()

    @staticmethod
    def _release_request(row: RowMapping) -> ReleaseRequest:
        return ReleaseRequest(
            request_id=str(row["request_id"]),
            revision=ReleaseRevision(
                tenant_id=row["tenant_id"],
                analysis_id=row["analysis_id"],
                revision_id=row["revision_id"],
                revision_sha256=row["revision_sha256"],
                is_clean=True,
            ),
            requested_by=row["requested_by"],
            reviewed_by=row["reviewed_by"],
            status=row["status"],
        )
