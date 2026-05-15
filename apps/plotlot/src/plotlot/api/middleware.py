"""Rate limiting middleware for PlotLot API.

Implements a sliding-window in-memory rate limiter.  Authenticated users get
higher limits; anonymous users are rate-limited by IP.

Design decisions:
    - In-memory dict (not Redis) — keeps the free-tier footprint at zero
      additional services.  Trade-off: limits reset on deploy/restart and
      don't share across multiple workers.  Acceptable for a single-dyno
      Render deployment.
    - Periodic cleanup prevents unbounded memory growth from unique IPs.
    - Configurable via settings (rate_limit_max_requests, rate_limit_window_seconds).

Production relevance:
    GetOnStack's costs went from $127/week to $47K/month without rate limits.
    Even a simple in-memory limiter prevents runaway LLM costs from bots or
    accidental loops.  Upgrade path: swap the dict for Redis when scaling
    beyond a single worker.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

from plotlot.config import settings

logger = logging.getLogger(__name__)

# Authenticated users get 3x the anonymous limit
_AUTH_MULTIPLIER = 3


class RateLimiter:
    """Sliding-window rate limiter backed by an in-memory dict.

    Usage as a FastAPI dependency::

        rate_limiter = RateLimiter()

        @router.post("/analyze", dependencies=[Depends(rate_limiter)])
        async def analyze(...): ...
    """

    def __init__(
        self,
        max_requests: int | None = None,
        window_seconds: int | None = None,
    ) -> None:
        self.max_requests = max_requests or settings.rate_limit_max_requests
        self.window_seconds = window_seconds or settings.rate_limit_window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._last_cleanup: float = time.time()
        self._cleanup_interval: float = 300.0  # purge stale entries every 5 min

    async def __call__(self, request: Request) -> None:
        """FastAPI dependency interface — check rate limit for the request."""
        await self.check(request)

    def _get_client_key(self, request: Request) -> tuple[str, int]:
        """Return (client_key, allowed_requests) for the request.

        Authenticated users are keyed by user_id and get a higher limit.
        Anonymous users are keyed by IP address.
        """
        # Check if auth middleware has set user info on request state
        user = getattr(request.state, "user", None) if hasattr(request, "state") else None
        if user and isinstance(user, dict) and user.get("user_id", "anonymous") != "anonymous":
            return f"user:{user['user_id']}", self.max_requests * _AUTH_MULTIPLIER

        # Fall back to IP-based limiting
        ip = request.client.host if request.client else "unknown"

        # Include X-Forwarded-For header for clients behind Render's proxy
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            ip = forwarded.split(",")[0].strip()

        return f"ip:{ip}", self.max_requests

    def _maybe_cleanup(self, now: float) -> None:
        """Periodically purge stale entries to prevent unbounded memory growth."""
        if now - self._last_cleanup < self._cleanup_interval:
            return
        self._last_cleanup = now
        cutoff = now - self.window_seconds
        stale_keys = [
            k
            for k, timestamps in self._requests.items()
            if not timestamps or timestamps[-1] < cutoff
        ]
        for k in stale_keys:
            del self._requests[k]
        if stale_keys:
            logger.debug("Rate limiter cleanup: purged %d stale keys", len(stale_keys))

    async def check(self, request: Request) -> None:
        """Enforce the sliding-window rate limit.

        Raises:
            HTTPException(429) when the rate limit is exceeded.
        """
        client_key, allowed = self._get_client_key(request)
        now = time.time()

        # Periodic cleanup
        self._maybe_cleanup(now)

        # Sliding window — drop timestamps outside the window
        cutoff = now - self.window_seconds
        timestamps = self._requests[client_key]
        self._requests[client_key] = [t for t in timestamps if t > cutoff]

        if len(self._requests[client_key]) >= allowed:
            retry_after = int(self.window_seconds - (now - self._requests[client_key][0])) + 1
            logger.warning(
                "Rate limit exceeded for %s — %d requests in %ds window",
                client_key,
                len(self._requests[client_key]),
                self.window_seconds,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Rate limit exceeded: {allowed} requests per "
                    f"{self.window_seconds}s. Try again in {retry_after}s."
                ),
                headers={"Retry-After": str(retry_after)},
            )

        self._requests[client_key].append(now)


# Singleton instance — use as a FastAPI dependency
# Example: dependencies=[Depends(rate_limiter)]
rate_limiter = RateLimiter()
