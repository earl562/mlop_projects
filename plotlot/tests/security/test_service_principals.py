from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from plotlot.api.auth import (
    ServicePrincipalScope,
    issue_service_principal_token,
    verify_service_principal_token,
)
from plotlot.config import settings
from plotlot.storage.models import ServicePrincipal, WorkspaceMember


def test_service_principal_token_is_tenant_and_action_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "service_principal_signing_key", "t" * 32)
    monkeypatch.setattr(settings, "service_principal_max_ttl_seconds", 900)
    token = issue_service_principal_token(
        principal_id="sp_ingest",
        tenant_id="tenant_a",
        actions=frozenset({"analysis:run", "evidence:write"}),
        ttl_seconds=300,
    )

    claims = verify_service_principal_token(
        token,
        ServicePrincipalScope(tenant_id="tenant_a", required_action="analysis:run"),
    )

    assert claims.principal_id == "sp_ingest"
    assert claims.tenant_id == "tenant_a"
    assert claims.actions == frozenset({"analysis:run", "evidence:write"})


@pytest.mark.parametrize(
    "scope",
    [
        ServicePrincipalScope(tenant_id="tenant_b", required_action="analysis:run"),
        ServicePrincipalScope(tenant_id="tenant_a", required_action="workspace:manage"),
    ],
)
def test_service_principal_rejects_cross_scope_access(
    monkeypatch: pytest.MonkeyPatch,
    scope: ServicePrincipalScope,
) -> None:
    monkeypatch.setattr(settings, "service_principal_signing_key", "t" * 32)
    token = issue_service_principal_token(
        principal_id="sp_ingest",
        tenant_id="tenant_a",
        actions=frozenset({"analysis:run"}),
        ttl_seconds=60,
    )

    with pytest.raises(jwt.InvalidTokenError, match="scope"):
        verify_service_principal_token(token, scope)


def test_service_principal_rejects_expired_and_revoked_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "service_principal_signing_key", "t" * 32)
    now = datetime.now(UTC)
    expired = jwt.encode(
        {
            "sub": "sp_expired",
            "iss": settings.service_principal_issuer,
            "aud": settings.service_principal_audience,
            "iat": int((now - timedelta(minutes=10)).timestamp()),
            "nbf": int((now - timedelta(minutes=10)).timestamp()),
            "exp": int((now - timedelta(minutes=5)).timestamp()),
            "jti": "expired-jti",
            "tenant_id": "tenant_a",
            "actions": ["analysis:run"],
            "token_type": "service_principal",
        },
        settings.service_principal_signing_key,
        algorithm="HS256",
    )
    scope = ServicePrincipalScope(tenant_id="tenant_a", required_action="analysis:run")

    with pytest.raises(jwt.ExpiredSignatureError):
        verify_service_principal_token(expired, scope)

    active = issue_service_principal_token(
        principal_id="sp_revoked",
        tenant_id="tenant_a",
        actions=frozenset({"analysis:run"}),
        ttl_seconds=60,
    )
    revoked_scope = ServicePrincipalScope(
        tenant_id="tenant_a",
        required_action="analysis:run",
        revoked_principal_ids=frozenset({"sp_revoked"}),
    )
    with pytest.raises(jwt.InvalidTokenError, match="revoked"):
        verify_service_principal_token(active, revoked_scope)


def test_service_principal_ttl_is_short_lived(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "service_principal_signing_key", "t" * 32)
    monkeypatch.setattr(settings, "service_principal_max_ttl_seconds", 900)

    with pytest.raises(ValueError, match="TTL"):
        issue_service_principal_token(
            principal_id="sp_long",
            tenant_id="tenant_a",
            actions=frozenset({"analysis:run"}),
            ttl_seconds=901,
        )


def test_identity_models_expose_membership_and_service_principal_fields() -> None:
    member_columns = set(WorkspaceMember.__table__.columns.keys())
    principal_columns = set(ServicePrincipal.__table__.columns.keys())

    assert {"workspace_id", "user_id", "role", "clerk_organization_id"}.issubset(member_columns)
    assert {
        "id",
        "workspace_id",
        "name",
        "allowed_actions",
        "expires_at",
        "revoked_at",
        "created_by_user_id",
    }.issubset(principal_columns)
