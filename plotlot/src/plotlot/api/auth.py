"""Production Clerk JWT verification and request actor derivation."""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from typing import TypedDict

import httpx
import jwt
from fastapi import HTTPException, Request, status
from jwt.algorithms import RSAAlgorithm
from pydantic import BaseModel, ConfigDict, TypeAdapter

from plotlot.api.auth_types import (
    Actor,
    Capability,
    IdentityRole,
    ServicePrincipalClaims,
    ServicePrincipalScope,
    capabilities_for_role,
)
from plotlot.api.service_auth import (
    issue_service_principal_token,
    verify_service_principal_token,
)
from plotlot.config import settings


class _JWKS(TypedDict):
    keys: list[dict[str, str]]


class _ClerkClaims(BaseModel):
    model_config = ConfigDict(frozen=True)

    sub: str
    azp: str
    jti: str
    org_id: str | None = None
    org_role: str | None = None
    email: str | None = None


JWKSFetcher = Callable[[str], _JWKS]


def _fetch_remote_jwks(url: str) -> _JWKS:
    timeout = httpx.Timeout(connect=3.0, read=5.0, write=5.0, pool=3.0)
    limits = httpx.Limits(
        max_connections=4,
        max_keepalive_connections=2,
        keepalive_expiry=30.0,
    )
    transport = httpx.HTTPTransport(retries=2)
    with httpx.Client(
        timeout=timeout,
        limits=limits,
        transport=transport,
        follow_redirects=False,
        trust_env=False,
    ) as client:
        response = client.get(url, headers={"Accept": "application/json"})
        response.raise_for_status()
        if len(response.content) > 1_048_576:
            raise jwt.InvalidTokenError("JWKS response exceeds the size limit")
        return TypeAdapter(_JWKS).validate_json(response.content)


def _identity_role(raw_role: str | None) -> IdentityRole:
    normalized = (raw_role or "").removeprefix("org:")
    try:
        return IdentityRole(normalized)
    except ValueError:
        return IdentityRole.VIEWER


class ClerkJWTVerifier:
    """Verify Clerk session JWTs against a pinned, rotating JWKS endpoint."""

    def __init__(
        self,
        *,
        jwks_url: str,
        issuer: str,
        audience: str,
        authorized_parties: frozenset[str],
        revoked_token_ids: frozenset[str],
        fetch_jwks: JWKSFetcher = _fetch_remote_jwks,
    ) -> None:
        self._jwks_url = jwks_url
        self._issuer = issuer
        self._audience = audience
        self._authorized_parties = authorized_parties
        self._revoked_token_ids = revoked_token_ids
        self._fetch_jwks = fetch_jwks
        self._keys: dict[str, dict[str, str]] = {}

    def _refresh_keys(self) -> None:
        jwks = self._fetch_jwks(self._jwks_url)
        self._keys = {
            key["kid"]: key
            for key in jwks["keys"]
            if key.get("kid") and key.get("kty") == "RSA" and key.get("use", "sig") == "sig"
        }

    def _key_for_token(self, token: str):
        header = jwt.get_unverified_header(token)
        if header.get("alg") != "RS256":
            raise jwt.InvalidTokenError("JWT algorithm is not permitted")
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise jwt.InvalidTokenError("JWT signing key id is missing")
        if not self._keys:
            self._refresh_keys()
        jwk = self._keys.get(kid)
        if jwk is None:
            self._refresh_keys()
            jwk = self._keys.get(kid)
        if jwk is None:
            raise jwt.InvalidTokenError("JWT signing key is unknown")
        return RSAAlgorithm.from_jwk(jwk)

    def verify(self, token: str) -> Actor:
        key = self._key_for_token(token)
        try:
            payload = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                issuer=self._issuer,
                audience=self._audience,
                options={
                    "require": [
                        "sub",
                        "iss",
                        "aud",
                        "azp",
                        "iat",
                        "nbf",
                        "exp",
                        "jti",
                    ]
                },
            )
        except jwt.ExpiredSignatureError as exc:
            raise jwt.InvalidTokenError("JWT expired") from exc
        except jwt.InvalidAudienceError as exc:
            raise jwt.InvalidTokenError("JWT audience is invalid") from exc
        except jwt.InvalidSignatureError as exc:
            raise jwt.InvalidTokenError("JWT signature verification failed") from exc
        claims = _ClerkClaims.model_validate(payload)
        if claims.azp not in self._authorized_parties:
            raise jwt.InvalidTokenError("JWT authorized party is invalid")
        if claims.jti in self._revoked_token_ids:
            raise jwt.InvalidTokenError("JWT is revoked")
        role = _identity_role(claims.org_role)
        return Actor(
            user_id=claims.sub,
            tenant_id=claims.org_id,
            role=role,
            capabilities=capabilities_for_role(role),
            email=claims.email,
        )


@lru_cache(maxsize=1)
def _configured_verifier() -> ClerkJWTVerifier:
    return ClerkJWTVerifier(
        jwks_url=settings.clerk_jwks_url,
        issuer=settings.clerk_issuer,
        audience=settings.clerk_audience,
        authorized_parties=frozenset(settings.clerk_authorized_parties),
        revoked_token_ids=frozenset(settings.clerk_revoked_token_ids),
    )


async def authenticate_request(
    request: Request,
    verifier: ClerkJWTVerifier,
) -> Actor | None:
    """Authenticate exclusively from a verified Authorization bearer token."""
    scheme, separator, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or separator != " " or not token:
        return None
    try:
        return verifier.verify(token)
    except jwt.InvalidTokenError:
        return None


async def get_current_user(
    request: Request,
) -> dict[str, str | None | frozenset[Capability]] | None:
    """Return a verified request user; never derive identity from request input."""
    if not settings.auth_enabled:
        return None
    actor = await authenticate_request(request, _configured_verifier())
    return actor.as_request_user() if actor is not None else None


async def require_auth(
    request: Request,
) -> dict[str, str | None | frozenset[Capability]]:
    """Require a verified production identity; no synthetic actor is created."""
    user = await get_current_user(request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


__all__ = [
    "Capability",
    "ClerkJWTVerifier",
    "IdentityRole",
    "ServicePrincipalClaims",
    "ServicePrincipalScope",
    "authenticate_request",
    "capabilities_for_role",
    "get_current_user",
    "issue_service_principal_token",
    "require_auth",
    "verify_service_principal_token",
]
