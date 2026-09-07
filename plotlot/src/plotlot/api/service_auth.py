"""Short-lived, tenant/action-scoped service-principal tokens."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
from pydantic import BaseModel, ConfigDict

from plotlot.api.auth_types import ServicePrincipalClaims, ServicePrincipalScope
from plotlot.config import settings


@dataclass(frozen=True, slots=True)
class ServicePrincipalConfigurationError(ValueError):
    reason: str

    def __str__(self) -> str:
        return self.reason


class _ServiceClaims(BaseModel):
    model_config = ConfigDict(frozen=True)

    sub: str
    iat: int
    exp: int
    tenant_id: str
    actions: list[str]
    token_type: str


def issue_service_principal_token(
    *,
    principal_id: str,
    tenant_id: str,
    actions: frozenset[str],
    ttl_seconds: int,
) -> str:
    """Issue a bounded service token using the configured deployment key."""
    if not 0 < ttl_seconds <= settings.service_principal_max_ttl_seconds:
        raise ServicePrincipalConfigurationError(
            reason="service-principal TTL exceeds the configured short-lived maximum"
        )
    if not principal_id or not tenant_id or not actions:
        raise ServicePrincipalConfigurationError(
            reason="service-principal identity, tenant, and actions are required"
        )
    now = datetime.now(UTC)
    payload = {
        "sub": principal_id,
        "iss": settings.service_principal_issuer,
        "aud": settings.service_principal_audience,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
        "jti": str(uuid4()),
        "tenant_id": tenant_id,
        "actions": sorted(actions),
        "token_type": "service_principal",
    }
    return jwt.encode(
        payload,
        settings.service_principal_signing_key,
        algorithm="HS256",
    )


def verify_service_principal_token(
    token: str,
    scope: ServicePrincipalScope,
) -> ServicePrincipalClaims:
    """Verify signature, lifetime, revocation, tenant, and requested action."""
    payload = jwt.decode(
        token,
        settings.service_principal_signing_key,
        algorithms=["HS256"],
        issuer=settings.service_principal_issuer,
        audience=settings.service_principal_audience,
        options={
            "require": [
                "sub",
                "iss",
                "aud",
                "iat",
                "nbf",
                "exp",
                "jti",
                "tenant_id",
                "actions",
                "token_type",
            ]
        },
    )
    claims = _ServiceClaims.model_validate(payload)
    lifetime_seconds = claims.exp - claims.iat
    if not 0 < lifetime_seconds <= settings.service_principal_max_ttl_seconds:
        raise jwt.InvalidTokenError("service-principal lifetime is outside configured bounds")
    if claims.token_type != "service_principal":
        raise jwt.InvalidTokenError("invalid service-principal token type")
    if claims.sub in scope.revoked_principal_ids:
        raise jwt.InvalidTokenError("service principal is revoked")
    actions = frozenset(claims.actions)
    if claims.tenant_id != scope.tenant_id or scope.required_action not in actions:
        raise jwt.InvalidTokenError("service-principal scope does not authorize this request")
    return ServicePrincipalClaims(
        principal_id=claims.sub,
        tenant_id=claims.tenant_id,
        actions=actions,
    )
