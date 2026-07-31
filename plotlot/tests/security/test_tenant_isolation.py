from unittest.mock import AsyncMock, patch
from uuid import uuid4

import asyncpg
import pytest
from sqlalchemy import text

from plotlot.api.auth_types import Actor, IdentityRole, capabilities_for_role
from plotlot.api.security_middleware import _server_derived_fields
from plotlot.security.context import reset_tenant, set_tenant
from plotlot.security.membership import resolve_actor_membership


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


def _actor(*, tenant_id: str, user_id: str = "user-a") -> Actor:
    role = IdentityRole.ANALYST
    return Actor(
        user_id=user_id,
        tenant_id=tenant_id,
        role=role,
        capabilities=capabilities_for_role(role),
    )


def test_chat_message_roles_are_not_treated_as_authorization_claims() -> None:
    body = {
        "message": "Synthetic question",
        "history": [{"role": "user", "content": "Synthetic prior message"}],
    }

    assert _server_derived_fields(body) == set()


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", "/api/v1/workspaces/tenant-b/projects", None),
        ("get", "/api/v1/analyses?workspace_id=tenant-b", None),
        ("get", "/api/v1/evidence?workspace_id=tenant-b", None),
        (
            "post",
            "/api/v1/analyses",
            {
                "workspace_id": "tenant-b",
                "project_id": "project-b",
                "name": "spoofed",
                "skill_name": "lookup",
            },
        ),
        (
            "post",
            "/api/v1/mcp/tools/call",
            {
                "name": "geocode_address",
                "arguments": {"address": "synthetic test parcel"},
                "context": {
                    "workspace_id": "tenant-b",
                    "actor_user_id": "forged-user",
                    "run_id": "run-1",
                    "risk_budget_cents": 1_000_000,
                    "live_network_allowed": True,
                    "approved_approval_ids": [],
                },
            },
        ),
    ],
)
async def test_cross_tenant_request_is_denied_before_data_access(
    client,
    method: str,
    path: str,
    body: dict[str, object] | None,
) -> None:
    session_factory = AsyncMock()
    with (
        patch(
            "plotlot.api.security_middleware.get_current_user",
            new=AsyncMock(return_value=_actor(tenant_id="tenant-a").as_request_user()),
        ),
        patch("plotlot.api.workspaces.get_session", new=session_factory),
        patch("plotlot.api.analyses.get_session", new=session_factory),
        patch("plotlot.api.evidence.get_session", new=session_factory),
        patch("plotlot.api.mcp.get_session", new=session_factory),
    ):
        response = await client.request(method, path, json=body)

    assert response.status_code == 403
    session_factory.assert_not_awaited()


async def test_body_identity_and_policy_fields_are_rejected_before_tool_dispatch(client) -> None:
    with (
        patch(
            "plotlot.api.security_middleware.get_current_user",
            new=AsyncMock(return_value=_actor(tenant_id="tenant-a").as_request_user()),
        ),
        patch("plotlot.api.mcp.get_default_runtime") as runtime,
    ):
        response = await client.post(
            "/api/v1/mcp/tools/call",
            json={
                "name": "geocode_address",
                "arguments": {"address": "synthetic test parcel"},
                "context": {
                    "workspace_id": "tenant-a",
                    "actor_user_id": "forged-user",
                    "run_id": "run-1",
                    "role": "owner",
                    "source_mode": "live",
                    "risk_budget_cents": 10,
                    "live_network_allowed": True,
                    "approved_approval_ids": [],
                },
            },
        )

    assert response.status_code == 422
    runtime.assert_not_called()


async def test_omitted_application_predicate_is_still_denied_by_rls() -> None:
    suffix = uuid4().hex[:8]
    tenant_a = f"tenant-a-{suffix}"
    tenant_b = f"tenant-b-{suffix}"
    project_a = f"project-a-{suffix}"
    project_b = f"project-b-{suffix}"
    admin = await asyncpg.connect(_ADMIN_DATABASE_URL)
    try:
        await admin.executemany(
            "INSERT INTO workspaces (id, name) VALUES ($1, $2)",
            [(tenant_a, "Tenant A"), (tenant_b, "Tenant B")],
        )
        await admin.executemany(
            "INSERT INTO projects (id, workspace_id, name) VALUES ($1, $2, $3)",
            [
                (project_a, tenant_a, "Project A"),
                (project_b, tenant_b, "Project B"),
            ],
        )
    finally:
        await admin.close()

    app_connection = await asyncpg.connect(_APP_DATABASE_URL)
    try:
        async with app_connection.transaction():
            await app_connection.execute(
                "SELECT set_config('app.tenant_id', $1, true)",
                tenant_a,
            )
            visible_ids = await app_connection.fetch("SELECT id FROM projects")
        without_context = await app_connection.fetch("SELECT id FROM projects")
    finally:
        await app_connection.close()

    assert [row["id"] for row in visible_ids] == [project_a]
    assert without_context == []


async def test_request_session_sets_transaction_local_tenant_without_pool_leakage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from plotlot.storage import db

    monkeypatch.setattr(db.settings, "database_url", _ASYNC_APP_DATABASE_URL)
    monkeypatch.setattr(db, "_engine", None)
    monkeypatch.setattr(db, "_session_factory", None)
    monkeypatch.setattr(db, "_engine_loop_id", None)
    tenant_token = set_tenant("tenant-a")
    session = await db.get_session()
    try:
        configured_tenant = await session.scalar(
            text("SELECT current_setting('app.tenant_id', true)")
        )
    finally:
        await session.close()
        reset_tenant(tenant_token)

    session_without_tenant = await db.get_session()
    try:
        leaked_tenant = await session_without_tenant.scalar(
            text("SELECT current_setting('app.tenant_id', true)")
        )
    finally:
        await session_without_tenant.close()
        if db._engine is not None:
            await db._engine.dispose()

    assert configured_tenant == "tenant-a"
    assert leaked_tenant in {None, ""}


async def test_persisted_membership_overrides_stale_token_role_and_revocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from plotlot.storage import db

    suffix = uuid4().hex[:8]
    tenant_id = f"tenant-membership-{suffix}"
    user_id = f"user-membership-{suffix}"
    admin = await asyncpg.connect(_ADMIN_DATABASE_URL)
    try:
        await admin.execute(
            "INSERT INTO workspaces (id, name) VALUES ($1, $2)",
            tenant_id,
            "Membership tenant",
        )
        await admin.execute(
            """INSERT INTO workspace_members
            (id, workspace_id, user_id, role)
            VALUES ($1, $2, $3, 'analyst')""",
            f"member-{suffix}",
            tenant_id,
            user_id,
        )
    finally:
        await admin.close()

    monkeypatch.setattr(db.settings, "database_url", _ASYNC_APP_DATABASE_URL)
    monkeypatch.setattr(db, "_engine", None)
    monkeypatch.setattr(db, "_session_factory", None)
    monkeypatch.setattr(db, "_engine_loop_id", None)
    token_actor = Actor(
        user_id=user_id,
        tenant_id=tenant_id,
        role=IdentityRole.OWNER,
        capabilities=capabilities_for_role(IdentityRole.OWNER),
    )
    tenant_token = set_tenant(tenant_id)
    try:
        resolved = await resolve_actor_membership(token_actor)
        admin = await asyncpg.connect(_ADMIN_DATABASE_URL)
        try:
            await admin.execute(
                "DELETE FROM workspace_members WHERE workspace_id = $1",
                tenant_id,
            )
        finally:
            await admin.close()
        revoked = await resolve_actor_membership(token_actor)
    finally:
        reset_tenant(tenant_token)
        if db._engine is not None:
            await db._engine.dispose()

    assert resolved is not None
    assert resolved.role is IdentityRole.ANALYST
    assert resolved.capabilities == capabilities_for_role(IdentityRole.ANALYST)
    assert revoked is None
