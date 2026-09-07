from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from pydantic import ValidationError
from starlette.requests import Request

from plotlot.api.auth import (
    Capability,
    ClerkJWTVerifier,
    IdentityRole,
    authenticate_request,
    capabilities_for_role,
)
from plotlot.config import Settings

ISSUER = "https://clerk.test"
AUDIENCE = "plotlot-api"
AUTHORIZED_PARTY = "https://app.plotlot.test"


def _key_pair(kid: str) -> tuple[rsa.RSAPrivateKey, dict[str, str]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    return private_key, {**public_jwk, "kid": kid, "use": "sig", "alg": "RS256"}


def _token(
    private_key: rsa.RSAPrivateKey,
    kid: str,
    *,
    now: datetime,
    claims: dict[str, str | int] | None = None,
) -> str:
    payload: dict[str, str | int] = {
        "sub": "user_verified",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "azp": AUTHORIZED_PARTY,
        "iat": int(now.timestamp()),
        "nbf": int((now - timedelta(seconds=1)).timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "jti": "token-valid",
        "org_id": "tenant_verified",
        "org_role": "org:analyst",
    }
    payload.update(claims or {})
    return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": kid})


def _verifier(
    jwks_fetcher: Callable[[str], dict[str, list[dict[str, str]]]],
    *,
    revoked_token_ids: frozenset[str] = frozenset(),
) -> ClerkJWTVerifier:
    return ClerkJWTVerifier(
        jwks_url="https://keys.plotlot.test/jwks.json",
        issuer=ISSUER,
        audience=AUDIENCE,
        authorized_parties=frozenset({AUTHORIZED_PARTY}),
        revoked_token_ids=revoked_token_ids,
        fetch_jwks=jwks_fetcher,
    )


@pytest.mark.parametrize(
    "missing",
    [
        "auth_enabled",
        "clerk_jwks_url",
        "clerk_issuer",
        "clerk_audience",
        "clerk_authorized_parties",
        "service_principal_signing_key",
    ],
)
def test_production_settings_fail_when_identity_configuration_is_incomplete(missing: str) -> None:
    values: dict[str, bool | str | list[str]] = {
        "deployment_environment": "production",
        "auth_enabled": True,
        "clerk_jwks_url": "https://keys.plotlot.test/jwks.json",
        "clerk_issuer": ISSUER,
        "clerk_audience": AUDIENCE,
        "clerk_authorized_parties": [AUTHORIZED_PARTY],
        "service_principal_signing_key": "s" * 32,
    }
    values[missing] = (
        False if missing == "auth_enabled" else ([] if missing.endswith("parties") else "")
    )

    with pytest.raises(ValidationError, match="production identity configuration"):
        Settings(_env_file=None, **values)


@pytest.mark.asyncio
async def test_verified_token_derives_actor_and_ignores_request_spoofing() -> None:
    now = datetime.now(UTC)
    key, jwk = _key_pair("key-1")
    token = _token(key, "key-1", now=now)
    body = json.dumps(
        {"actor_user_id": "body_spoof", "user_id": "body_spoof", "tenant_id": "body_tenant"}
    ).encode()
    sent = False

    async def receive() -> dict[str, bytes | bool | str]:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/tools",
            "query_string": b"actor_user_id=query_spoof&tenant_id=query_tenant",
            "headers": [(b"authorization", f"Bearer {token}".encode())],
            "server": ("test", 443),
            "scheme": "https",
        },
        receive,
    )

    actor = await authenticate_request(
        request,
        _verifier(lambda _: {"keys": [jwk]}),
    )

    assert actor is not None
    assert actor.user_id == "user_verified"
    assert actor.tenant_id == "tenant_verified"
    assert actor.role is IdentityRole.ANALYST
    assert actor.capabilities == capabilities_for_role(IdentityRole.ANALYST)


@pytest.mark.parametrize(
    ("claim_override", "expected_error"),
    [
        ({"iss": "https://attacker.test"}, "issuer"),
        ({"aud": "other-api"}, "audience"),
        ({"azp": "https://attacker.test"}, "authorized party"),
        ({"exp": 1}, "expired"),
        ({"nbf": 4_102_444_800}, "not yet valid"),
        ({"jti": "token-revoked"}, "revoked"),
    ],
)
def test_clerk_verifier_rejects_invalid_claims(
    claim_override: dict[str, str | int],
    expected_error: str,
) -> None:
    now = datetime.now(UTC)
    key, jwk = _key_pair("key-1")
    token = _token(key, "key-1", now=now, claims=claim_override)
    revoked = (
        frozenset({"token-revoked"})
        if claim_override.get("jti") == "token-revoked"
        else frozenset()
    )

    with pytest.raises(jwt.InvalidTokenError, match=expected_error):
        _verifier(lambda _: {"keys": [jwk]}, revoked_token_ids=revoked).verify(token)


def test_clerk_verifier_rejects_wrong_kid_and_signature() -> None:
    now = datetime.now(UTC)
    trusted_key, trusted_jwk = _key_pair("trusted")
    attacker_key, _ = _key_pair("attacker")
    wrong_kid_token = _token(attacker_key, "unknown", now=now)
    wrong_signature_token = _token(attacker_key, "trusted", now=now)
    verifier = _verifier(lambda _: {"keys": [trusted_jwk]})

    with pytest.raises(jwt.InvalidTokenError, match="signing key"):
        verifier.verify(wrong_kid_token)
    with pytest.raises(jwt.InvalidTokenError, match="signature"):
        verifier.verify(wrong_signature_token)

    assert trusted_key.key_size == 2048


def test_clerk_verifier_refreshes_jwks_for_rotated_kid() -> None:
    now = datetime.now(UTC)
    old_key, old_jwk = _key_pair("old")
    new_key, new_jwk = _key_pair("new")
    responses = iter(({"keys": [old_jwk]}, {"keys": [new_jwk]}))
    fetch_count = 0

    def fetch(_: str) -> dict[str, list[dict[str, str]]]:
        nonlocal fetch_count
        fetch_count += 1
        return next(responses)

    verifier = _verifier(fetch)

    assert verifier.verify(_token(old_key, "old", now=now)).user_id == "user_verified"
    assert verifier.verify(_token(new_key, "new", now=now)).user_id == "user_verified"
    assert fetch_count == 2


def test_role_capabilities_are_least_privilege() -> None:
    assert Capability.MANAGE_WORKSPACE in capabilities_for_role(IdentityRole.OWNER)
    assert Capability.MANAGE_MEMBERS in capabilities_for_role(IdentityRole.ADMIN)
    assert capabilities_for_role(IdentityRole.ANALYST) == frozenset(
        {Capability.RUN_ANALYSIS, Capability.VIEW_ANALYSIS}
    )
    assert capabilities_for_role(IdentityRole.REVIEWER) == frozenset(
        {
            Capability.RELEASE_EXTERNAL,
            Capability.REVIEW_ANALYSIS,
            Capability.VIEW_ANALYSIS,
        }
    )
    assert capabilities_for_role(IdentityRole.VIEWER) == frozenset({Capability.VIEW_ANALYSIS})
