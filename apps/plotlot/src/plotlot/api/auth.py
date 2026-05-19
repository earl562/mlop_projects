"""Clerk Auth integration — opt-in JWT verification for PlotLot.

When `auth_enabled=False` (default), all auth checks pass through and users
are treated as anonymous.  When enabled, JWTs issued by Clerk are validated
using PyJWT + JWKS (RS256) fetched from the Clerk instance's JWKS endpoint.

Dependencies:
    get_current_user  — returns user dict or None (never raises)
    require_auth      — returns user dict or raises 401

Production relevance:
    This is the "progressive autonomy" pattern — start permissive, tighten as
    the user base grows.  The opt-in toggle means local dev and CI never need
    auth credentials configured.  JWKS key is cached process-lifetime and
    refreshed on cache miss (e.g. after a Render restart on key rotation).
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm
from fastapi import HTTPException, Request, status

from plotlot.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _fetch_clerk_public_key(jwks_url: str) -> Any:
    """Fetch and cache Clerk's RSA public key from the JWKS endpoint.

    Cached process-lifetime — a Render restart picks up rotated keys.
    Uses synchronous httpx since this is called once at first auth request.
    """
    try:
        resp = httpx.get(jwks_url, timeout=10.0)
        resp.raise_for_status()
        jwks = resp.json()
        keys = jwks.get("keys", [])
        if not keys:
            logger.error("Clerk JWKS returned no keys from %s", jwks_url)
            return None
        return RSAAlgorithm.from_jwk(keys[0])
    except Exception as exc:
        logger.error("Failed to fetch Clerk JWKS from %s: %s", jwks_url, exc)
        return None


async def get_current_user(request: Request) -> dict[str, Any] | None:
    """Extract and validate the current user from a Clerk JWT (RS256).

    Returns:
        dict with ``user_id`` and ``email`` if a valid token is present,
        or ``None`` for anonymous access (including when auth is disabled).
    """
    if not settings.auth_enabled:
        return None  # anonymous access — auth not configured

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header[7:]  # strip "Bearer "
    if not token:
        return None

    if not settings.clerk_jwks_url:
        logger.error("AUTH_ENABLED=true but CLERK_JWKS_URL is not set")
        return None

    public_key = _fetch_clerk_public_key(settings.clerk_jwks_url)
    if public_key is None:
        return None

    try:
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={"verify_aud": False},  # Clerk doesn't use audience claim by default
        )
        return {
            "user_id": payload["sub"],
            "email": payload.get("email"),
            "role": "authenticated",
        }
    except jwt.ExpiredSignatureError:
        logger.debug("JWT expired for request to %s", request.url.path)
        return None
    except jwt.InvalidTokenError as exc:
        logger.debug("Invalid JWT for request to %s: %s", request.url.path, exc)
        return None


async def require_auth(request: Request) -> dict[str, Any]:
    """Dependency that enforces authentication — raises 401 if no valid token.

    When ``auth_enabled=False``, returns a synthetic anonymous user so
    protected endpoints still work during development.
    """
    if not settings.auth_enabled:
        # Return a synthetic anonymous user for dev/testing
        return {"user_id": "anonymous", "email": None, "role": "anonymous"}

    user = await get_current_user(request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
