"""Supabase Auth integration — opt-in JWT verification for PlotLot.

When `auth_enabled=False` (default), all auth checks pass through and users
are treated as anonymous.  When enabled, JWTs issued by Supabase are validated
using PyJWT against the project's JWT secret.

Dependencies:
    get_current_user  — returns user dict or None (never raises)
    require_auth      — returns user dict or raises 401

Production relevance:
    This is the "progressive autonomy" pattern — start permissive, tighten as
    the user base grows.  Supabase free tier gives 50K MAU, more than enough
    for an MVP.  The opt-in toggle means local dev and CI never need auth
    credentials configured.
"""

from __future__ import annotations

import logging
from typing import Any

import jwt
from fastapi import HTTPException, Request, status

from plotlot.config import settings

logger = logging.getLogger(__name__)


async def get_current_user(request: Request) -> dict[str, Any] | None:
    """Extract and validate the current user from a Supabase JWT.

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

    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return {
            "user_id": payload["sub"],
            "email": payload.get("email"),
            "role": payload.get("role", "authenticated"),
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
