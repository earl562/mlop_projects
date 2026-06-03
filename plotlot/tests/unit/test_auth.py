"""Regression tests for PlotLot Clerk auth middleware (get_current_user / require_auth).

The auth layer is opt-in: when ``AUTH_ENABLED=false`` (the default), all
requests pass through as anonymous and protected endpoints accept a
synthetic anonymous user.  When ``AUTH_ENABLED=true``, the Clerk JWKS
endpoint must be reachable and incoming JWTs must verify under RS256.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import httpx
import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from jwt.algorithms import RSAAlgorithm
from starlette.requests import Request

from plotlot.api.auth import _fetch_clerk_public_key, get_current_user, require_auth


def _make_rsa_keypair() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def _kid_for(public_key: rsa.RSAPublicKey, kid: str = "test-kid") -> dict:
    return dict(RSAAlgorithm.to_jwk(public_key, as_dict=True)) | {"kid": kid}


def _request(headers: dict[str, str] | None = None, path: str = "/") -> Request:
    scope = {
        "type": "http",
        "path": path,
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "client": ("127.0.0.1", 12345),
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_get_current_user_returns_none_when_auth_disabled():
    request = _request({"Authorization": "Bearer whatever"})
    with patch("plotlot.api.auth.settings") as mock_settings:
        mock_settings.auth_enabled = False
        user = await get_current_user(request)
    assert user is None


@pytest.mark.asyncio
async def test_get_current_user_returns_none_when_auth_disabled_and_no_header():
    request = _request()
    with patch("plotlot.api.auth.settings") as mock_settings:
        mock_settings.auth_enabled = False
        user = await get_current_user(request)
    assert user is None


@pytest.mark.asyncio
async def test_get_current_user_returns_none_when_header_missing():
    request = _request()
    with patch("plotlot.api.auth.settings") as mock_settings:
        mock_settings.auth_enabled = True
        mock_settings.clerk_jwks_url = "https://example.clerk/.well-known/jwks.json"
        user = await get_current_user(request)
    assert user is None


@pytest.mark.asyncio
async def test_get_current_user_returns_none_when_header_not_bearer():
    request = _request({"Authorization": "Basic abc123"})
    with patch("plotlot.api.auth.settings") as mock_settings:
        mock_settings.auth_enabled = True
        mock_settings.clerk_jwks_url = "https://example.clerk/.well-known/jwks.json"
        user = await get_current_user(request)
    assert user is None


@pytest.mark.asyncio
async def test_get_current_user_returns_none_when_jwks_url_missing():
    request = _request({"Authorization": "Bearer fake.token.value"})
    with patch("plotlot.api.auth.settings") as mock_settings:
        mock_settings.auth_enabled = True
        mock_settings.clerk_jwks_url = ""
        user = await get_current_user(request)
    assert user is None


@pytest.mark.asyncio
async def test_get_current_user_returns_none_when_jwks_fetch_fails():
    request = _request({"Authorization": "Bearer fake.token.value"})
    with (
        patch("plotlot.api.auth.settings") as mock_settings,
        patch("plotlot.api.auth._fetch_clerk_public_key", return_value=None),
    ):
        mock_settings.auth_enabled = True
        mock_settings.clerk_jwks_url = "https://example.clerk/.well-known/jwks.json"
        user = await get_current_user(request)
    assert user is None


@pytest.mark.asyncio
async def test_get_current_user_returns_user_for_valid_token():
    private_key, public_key = _make_rsa_keypair()
    token = pyjwt.encode(
        {"sub": "user_42", "email": "user@example.com"},
        private_key,
        algorithm="RS256",
        headers={"kid": "test-kid"},
    )
    request = _request({"Authorization": f"Bearer {token}"})

    with (
        patch("plotlot.api.auth.settings") as mock_settings,
        patch("plotlot.api.auth._fetch_clerk_public_key", return_value=public_key),
    ):
        mock_settings.auth_enabled = True
        mock_settings.clerk_jwks_url = "https://example.clerk/.well-known/jwks.json"
        user = await get_current_user(request)

    assert user == {
        "user_id": "user_42",
        "email": "user@example.com",
        "role": "authenticated",
    }


@pytest.mark.asyncio
async def test_get_current_user_returns_none_for_expired_token():
    private_key, public_key = _make_rsa_keypair()
    token = pyjwt.encode(
        {"sub": "user_42", "exp": int(time.time()) - 60},
        private_key,
        algorithm="RS256",
        headers={"kid": "test-kid"},
    )
    request = _request({"Authorization": f"Bearer {token}"})

    with (
        patch("plotlot.api.auth.settings") as mock_settings,
        patch("plotlot.api.auth._fetch_clerk_public_key", return_value=public_key),
    ):
        mock_settings.auth_enabled = True
        mock_settings.clerk_jwks_url = "https://example.clerk/.well-known/jwks.json"
        user = await get_current_user(request)
    assert user is None


@pytest.mark.asyncio
async def test_get_current_user_returns_none_for_invalid_signature():
    private_key_a, _ = _make_rsa_keypair()
    _, public_key_b = _make_rsa_keypair()
    token = pyjwt.encode(
        {"sub": "user_42"},
        private_key_a,
        algorithm="RS256",
        headers={"kid": "test-kid"},
    )
    request = _request({"Authorization": f"Bearer {token}"})

    with (
        patch("plotlot.api.auth.settings") as mock_settings,
        patch("plotlot.api.auth._fetch_clerk_public_key", return_value=public_key_b),
    ):
        mock_settings.auth_enabled = True
        mock_settings.clerk_jwks_url = "https://example.clerk/.well-known/jwks.json"
        user = await get_current_user(request)
    assert user is None


@pytest.mark.asyncio
async def test_get_current_user_handles_missing_email_claim():
    private_key, public_key = _make_rsa_keypair()
    token = pyjwt.encode(
        {"sub": "user_99"},
        private_key,
        algorithm="RS256",
        headers={"kid": "test-kid"},
    )
    request = _request({"Authorization": f"Bearer {token}"})

    with (
        patch("plotlot.api.auth.settings") as mock_settings,
        patch("plotlot.api.auth._fetch_clerk_public_key", return_value=public_key),
    ):
        mock_settings.auth_enabled = True
        mock_settings.clerk_jwks_url = "https://example.clerk/.well-known/jwks.json"
        user = await get_current_user(request)

    assert user is not None
    assert user["user_id"] == "user_99"
    assert user["email"] is None


@pytest.mark.asyncio
async def test_require_auth_returns_synthetic_user_when_disabled():
    request = _request()
    with patch("plotlot.api.auth.settings") as mock_settings:
        mock_settings.auth_enabled = False
        user = await require_auth(request)
    assert user == {"user_id": "anonymous", "email": None, "role": "anonymous"}


@pytest.mark.asyncio
async def test_require_auth_raises_401_when_enabled_and_no_token():
    request = _request()
    with patch("plotlot.api.auth.settings") as mock_settings:
        mock_settings.auth_enabled = True
        mock_settings.clerk_jwks_url = "https://example.clerk/.well-known/jwks.json"
        with pytest.raises(HTTPException) as exc:
            await require_auth(request)
    assert exc.value.status_code == 401
    assert exc.value.headers.get("WWW-Authenticate") == "Bearer"


@pytest.mark.asyncio
async def test_require_auth_returns_user_when_enabled_and_valid_token():
    private_key, public_key = _make_rsa_keypair()
    token = pyjwt.encode(
        {"sub": "user_42", "email": "user@example.com"},
        private_key,
        algorithm="RS256",
        headers={"kid": "test-kid"},
    )
    request = _request({"Authorization": f"Bearer {token}"})

    with (
        patch("plotlot.api.auth.settings") as mock_settings,
        patch("plotlot.api.auth._fetch_clerk_public_key", return_value=public_key),
    ):
        mock_settings.auth_enabled = True
        mock_settings.clerk_jwks_url = "https://example.clerk/.well-known/jwks.json"
        user = await require_auth(request)
    assert user["user_id"] == "user_42"


def test_fetch_clerk_public_key_returns_none_when_jwks_has_no_keys():
    fake_response = MagicMock()
    fake_response.json.return_value = {"keys": []}
    fake_response.raise_for_status = MagicMock()

    with patch("plotlot.api.auth.httpx.get", return_value=fake_response):
        key = _fetch_clerk_public_key("https://example.clerk/empty-jwks.json")
    assert key is None


def test_fetch_clerk_public_key_returns_none_on_http_error():
    fake_response = MagicMock()
    fake_response.raise_for_status.side_effect = httpx.HTTPError("boom")

    with patch("plotlot.api.auth.httpx.get", return_value=fake_response):
        key = _fetch_clerk_public_key("https://example.clerk/error-jwks.json")
    assert key is None


def test_fetch_clerk_public_key_returns_rsa_key_on_success():
    _fetch_clerk_public_key.cache_clear()
    private_key, public_key = _make_rsa_keypair()
    jwk_dict = _kid_for(public_key)

    fake_response = MagicMock()
    fake_response.json.return_value = {"keys": [jwk_dict]}
    fake_response.raise_for_status = MagicMock()

    with patch("plotlot.api.auth.httpx.get", return_value=fake_response):
        key = _fetch_clerk_public_key("https://example.clerk/ok-jwks.json")
    assert key is not None

    token = pyjwt.encode(
        {"sub": "u"}, private_key, algorithm="RS256", headers={"kid": "test-kid"}
    )
    decoded = pyjwt.decode(token, key, algorithms=["RS256"], options={"verify_aud": False})
    assert decoded["sub"] == "u"
