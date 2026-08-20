from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID, uuid4

import asyncpg
import pytest

from plotlot.security.context import reset_tenant, set_tenant
from plotlot.security.release import ReleaseConflictError, ReleaseRequest, ReleaseRevision
from plotlot.storage.release_repository import PostgresReleaseRepository


_ADMIN_DATABASE_URL = (
    "postgresql://storage_admin:storage_test_password@127.0.0.1:55432/plotlot_storage"
)
_APP_DATABASE_URL = (
    "postgresql://plotlot_app:plotlot_rls_test_password@127.0.0.1:55432/plotlot_storage"
)
_ASYNC_APP_DATABASE_URL = _APP_DATABASE_URL.replace(
    "postgresql://",
    "postgresql+asyncpg://",
)


@dataclass(frozen=True, slots=True)
class ReleaseFixture:
    tenant_id: str
    request_id: UUID


async def _seed_release(*, released: bool) -> ReleaseFixture:
    fixture = ReleaseFixture(
        tenant_id=f"tenant-release-guard-{uuid4().hex}",
        request_id=uuid4(),
    )
    digest = sha256(fixture.tenant_id.encode()).hexdigest()
    admin = await asyncpg.connect(_ADMIN_DATABASE_URL)
    try:
        await admin.execute(
            """INSERT INTO plotlot.analysis_revision_heads
            (tenant_id, analysis_id, revision_id, revision_sha256, is_clean)
            VALUES ($1, 'analysis-guard', 'revision-guard', $2, true)""",
            fixture.tenant_id,
            digest,
        )
        await admin.execute(
            """INSERT INTO plotlot.external_release_requests
            (tenant_id, request_id, analysis_id, revision_id, revision_sha256,
             requested_by, reviewed_by, status, released_at)
            VALUES ($1, $2, 'analysis-guard', 'revision-guard', $3,
                    'analyst-guard',
                    CASE WHEN $4 THEN 'reviewer-guard' END,
                    CASE WHEN $4 THEN 'released' ELSE 'pending' END,
                    CASE WHEN $4 THEN now() END)""",
            fixture.tenant_id,
            fixture.request_id,
            digest,
            released,
        )
    finally:
        await admin.close()
    return fixture


async def _delete_fixture(fixture: ReleaseFixture) -> None:
    admin = await asyncpg.connect(_ADMIN_DATABASE_URL)
    try:
        await admin.execute(
            "DELETE FROM plotlot.external_release_requests WHERE tenant_id=$1",
            fixture.tenant_id,
        )
        await admin.execute(
            "DELETE FROM plotlot.analysis_revision_heads WHERE tenant_id=$1",
            fixture.tenant_id,
        )
    finally:
        await admin.close()


_IMMUTABLE_COLUMN_ATTACKS = (
    "UPDATE plotlot.external_release_requests "
    "SET tenant_id=tenant_id || '-rewritten' WHERE request_id=$1",
    "UPDATE plotlot.external_release_requests SET request_id=gen_random_uuid() WHERE request_id=$1",
    "UPDATE plotlot.external_release_requests "
    "SET analysis_id='analysis-rewritten' WHERE request_id=$1",
    "UPDATE plotlot.external_release_requests "
    "SET revision_id='revision-rewritten' WHERE request_id=$1",
    "UPDATE plotlot.external_release_requests "
    "SET revision_sha256=repeat('0', 64) WHERE request_id=$1",
    "UPDATE plotlot.external_release_requests "
    "SET requested_by='requester-rewritten' WHERE request_id=$1",
    "UPDATE plotlot.external_release_requests "
    "SET created_at=created_at + interval '1 second' WHERE request_id=$1",
)


@pytest.mark.parametrize("attack_sql", _IMMUTABLE_COLUMN_ATTACKS)
async def test_plotlot_app_cannot_rewrite_release_audit_identity(
    attack_sql: str,
) -> None:
    fixture = await _seed_release(released=False)
    app = await asyncpg.connect(_APP_DATABASE_URL)
    try:
        async with app.transaction():
            await app.execute(
                "SELECT set_config('app.tenant_id', $1, true)",
                fixture.tenant_id,
            )
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await app.execute(attack_sql, fixture.request_id)
    finally:
        await app.close()
        await _delete_fixture(fixture)


@pytest.mark.parametrize(
    ("released", "attack_sql"),
    [
        (
            False,
            "UPDATE plotlot.external_release_requests "
            "SET reviewed_by='reviewer-guard' WHERE request_id=$1",
        ),
        (
            False,
            "UPDATE plotlot.external_release_requests SET status='released' WHERE request_id=$1",
        ),
        (
            False,
            "UPDATE plotlot.external_release_requests "
            "SET status='released', reviewed_by=requested_by "
            "WHERE request_id=$1",
        ),
        (
            True,
            "UPDATE plotlot.external_release_requests "
            "SET status='pending', reviewed_by=NULL "
            "WHERE request_id=$1",
        ),
        (
            True,
            "UPDATE plotlot.external_release_requests "
            "SET reviewed_by='reviewer-rewritten' WHERE request_id=$1",
        ),
    ],
)
async def test_plotlot_app_cannot_make_invalid_transition_with_granted_columns(
    *,
    released: bool,
    attack_sql: str,
) -> None:
    fixture = await _seed_release(released=released)
    app = await asyncpg.connect(_APP_DATABASE_URL)
    try:
        async with app.transaction():
            await app.execute(
                "SELECT set_config('app.tenant_id', $1, true)",
                fixture.tenant_id,
            )
            with pytest.raises(asyncpg.CheckViolationError):
                await app.execute(attack_sql, fixture.request_id)
    finally:
        await app.close()
        await _delete_fixture(fixture)


@pytest.mark.parametrize(
    ("released", "attack_sql"),
    [
        (
            False,
            "UPDATE plotlot.external_release_requests SET released_at=now() WHERE request_id=$1",
        ),
        (
            False,
            "UPDATE plotlot.external_release_requests "
            "SET status='released', reviewed_by='reviewer-guard', released_at=now() "
            "WHERE request_id=$1",
        ),
        (
            True,
            "UPDATE plotlot.external_release_requests "
            "SET status='pending', reviewed_by=NULL, released_at=NULL "
            "WHERE request_id=$1",
        ),
        (
            True,
            "UPDATE plotlot.external_release_requests "
            "SET released_at=released_at + interval '1 second' WHERE request_id=$1",
        ),
    ],
)
async def test_plotlot_app_has_no_released_at_update_privilege(
    *,
    released: bool,
    attack_sql: str,
) -> None:
    fixture = await _seed_release(released=released)
    app = await asyncpg.connect(_APP_DATABASE_URL)
    try:
        async with app.transaction():
            await app.execute(
                "SELECT set_config('app.tenant_id', $1, true)",
                fixture.tenant_id,
            )
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await app.execute(attack_sql, fixture.request_id)
    finally:
        await app.close()
        await _delete_fixture(fixture)


async def test_plotlot_app_cannot_forge_release_state_on_insert() -> None:
    fixture = await _seed_release(released=False)
    admin = await asyncpg.connect(_ADMIN_DATABASE_URL)
    try:
        await admin.execute(
            "DELETE FROM plotlot.external_release_requests WHERE tenant_id=$1",
            fixture.tenant_id,
        )
    finally:
        await admin.close()

    app = await asyncpg.connect(_APP_DATABASE_URL)
    try:
        async with app.transaction():
            await app.execute(
                "SELECT set_config('app.tenant_id', $1, true)",
                fixture.tenant_id,
            )
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await app.execute(
                    """INSERT INTO plotlot.external_release_requests
                    (tenant_id, request_id, analysis_id, revision_id,
                     revision_sha256, requested_by, reviewed_by, status, released_at)
                    SELECT tenant_id, $1, analysis_id, revision_id,
                           revision_sha256, 'forged-requester', 'forged-reviewer',
                           'released', now()
                    FROM plotlot.analysis_revision_heads
                    WHERE tenant_id=$2""",
                    uuid4(),
                    fixture.tenant_id,
                )
    finally:
        await app.close()
        await _delete_fixture(fixture)


async def test_plotlot_app_cannot_delete_release_audit_row() -> None:
    fixture = await _seed_release(released=True)
    app = await asyncpg.connect(_APP_DATABASE_URL)
    try:
        async with app.transaction():
            await app.execute(
                "SELECT set_config('app.tenant_id', $1, true)",
                fixture.tenant_id,
            )
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await app.execute(
                    "DELETE FROM plotlot.external_release_requests WHERE request_id=$1",
                    fixture.request_id,
                )
    finally:
        await app.close()
        await _delete_fixture(fixture)


async def test_repository_can_create_and_atomically_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from plotlot.storage import db

    fixture = await _seed_release(released=False)
    admin = await asyncpg.connect(_ADMIN_DATABASE_URL)
    try:
        await admin.execute(
            "DELETE FROM plotlot.external_release_requests WHERE tenant_id=$1",
            fixture.tenant_id,
        )
        head = await admin.fetchrow(
            """SELECT revision_sha256
            FROM plotlot.analysis_revision_heads
            WHERE tenant_id=$1""",
            fixture.tenant_id,
        )
    finally:
        await admin.close()
    assert head is not None

    monkeypatch.setattr(db.settings, "database_url", _ASYNC_APP_DATABASE_URL)
    monkeypatch.setattr(db, "_engine", None)
    monkeypatch.setattr(db, "_session_factory", None)
    monkeypatch.setattr(db, "_engine_loop_id", None)
    request = ReleaseRequest(
        request_id=str(uuid4()),
        revision=ReleaseRevision(
            tenant_id=fixture.tenant_id,
            analysis_id="analysis-guard",
            revision_id="revision-guard",
            revision_sha256=head["revision_sha256"],
            is_clean=True,
        ),
        requested_by="analyst-guard",
    )
    repository = PostgresReleaseRepository()
    tenant_token = set_tenant(fixture.tenant_id)
    try:
        created = await repository.create(request)
        released = await repository.compare_and_release(
            request.request_id,
            "reviewer-guard",
        )
        with pytest.raises(ReleaseConflictError):
            await repository.compare_and_release(
                request.request_id,
                "second-reviewer",
            )
    finally:
        reset_tenant(tenant_token)
        if db._engine is not None:
            await db._engine.dispose()

    admin = await asyncpg.connect(_ADMIN_DATABASE_URL)
    try:
        persisted = await admin.fetchrow(
            """SELECT requested_by, reviewed_by, status, released_at
            FROM plotlot.external_release_requests
            WHERE tenant_id=$1 AND request_id=$2""",
            fixture.tenant_id,
            UUID(request.request_id),
        )
    finally:
        await admin.close()
        await _delete_fixture(fixture)

    assert created == request
    assert released is not None
    assert released.status == "released"
    assert released.reviewed_by == "reviewer-guard"
    assert persisted is not None
    assert dict(persisted) == {
        "requested_by": "analyst-guard",
        "reviewed_by": "reviewer-guard",
        "status": "released",
        "released_at": persisted["released_at"],
    }
    assert persisted["released_at"] is not None
