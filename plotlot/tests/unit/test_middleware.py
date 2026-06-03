"""Regression tests for PlotLot in-memory sliding-window rate limiter.

The limiter is a process-local dict — its trade-off (zero extra services,
single-dyno friendly) is documented in ``plotlot.api.middleware``. These
tests pin the public contract: anonymous-by-IP keying, authenticated 3x
bonus, sliding-window eviction, and the 429 response with Retry-After.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from plotlot.api.middleware import RateLimiter, _AUTH_MULTIPLIER


def _request(
    ip: str = "1.2.3.4",
    user: dict | None = None,
    forwarded_for: str | None = None,
    path: str = "/api/v1/analyze",
) -> Request:
    headers = []
    if forwarded_for is not None:
        headers.append((b"x-forwarded-for", forwarded_for.encode()))
    scope = {
        "type": "http",
        "path": path,
        "headers": headers,
        "client": (ip, 50000),
    }
    request = Request(scope)
    if user is not None:
        request.state.user = user
    return request


def _new_limiter(max_requests: int = 3, window_seconds: int = 60) -> RateLimiter:
    return RateLimiter(max_requests=max_requests, window_seconds=window_seconds)


@pytest.mark.asyncio
async def test_allows_requests_under_anonymous_limit():
    limiter = _new_limiter(max_requests=3)
    request = _request(ip="10.0.0.1")

    for _ in range(3):
        await limiter.check(request)
    assert len(limiter._requests["ip:10.0.0.1"]) == 3


@pytest.mark.asyncio
async def test_raises_429_when_anonymous_limit_exceeded():
    limiter = _new_limiter(max_requests=2)
    request = _request(ip="10.0.0.1")

    await limiter.check(request)
    await limiter.check(request)

    with pytest.raises(HTTPException) as exc:
        await limiter.check(request)
    assert exc.value.status_code == 429
    assert "Retry-After" in exc.value.headers
    assert "Rate limit exceeded" in exc.value.detail


@pytest.mark.asyncio
async def test_authenticated_user_gets_3x_limit():
    limiter = _new_limiter(max_requests=2)
    request = _request(user={"user_id": "user_abc", "email": "u@x.com"})

    allowed = 2 * _AUTH_MULTIPLIER
    for _ in range(allowed):
        await limiter.check(request)
    assert len(limiter._requests["user:user_abc"]) == allowed

    with pytest.raises(HTTPException) as exc:
        await limiter.check(request)
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_anonymous_user_keyed_by_ip_not_user_id():
    limiter = _new_limiter(max_requests=1)
    request = _request(
        ip="10.0.0.99",
        user={"user_id": "anonymous"},
    )

    await limiter.check(request)
    with pytest.raises(HTTPException):
        await limiter.check(request)
    assert "ip:10.0.0.99" in limiter._requests


@pytest.mark.asyncio
async def test_uses_x_forwarded_for_header_when_present():
    limiter = _new_limiter(max_requests=1)
    request = _request(ip="10.0.0.1", forwarded_for="203.0.113.5, 10.0.0.1")

    await limiter.check(request)
    with pytest.raises(HTTPException):
        await limiter.check(request)
    assert "ip:203.0.113.5" in limiter._requests


@pytest.mark.asyncio
async def test_different_ips_have_separate_buckets():
    limiter = _new_limiter(max_requests=1)
    await limiter.check(_request(ip="10.0.0.1"))
    await limiter.check(_request(ip="10.0.0.2"))
    assert "ip:10.0.0.1" in limiter._requests
    assert "ip:10.0.0.2" in limiter._requests


@pytest.mark.asyncio
async def test_sliding_window_evicts_old_timestamps():
    limiter = _new_limiter(max_requests=2, window_seconds=10)
    request = _request(ip="10.0.0.5")

    base = 1_000_000.0
    with patch("plotlot.api.middleware.time.time", return_value=base):
        await limiter.check(request)
        await limiter.check(request)
        assert len(limiter._requests["ip:10.0.0.5"]) == 2

    with patch("plotlot.api.middleware.time.time", return_value=base + 11):
        await limiter.check(request)

    assert len(limiter._requests["ip:10.0.0.5"]) == 1


@pytest.mark.asyncio
async def test_call_interface_works_as_fastapi_dependency():
    limiter = _new_limiter(max_requests=5)
    request = _request(ip="10.0.0.6")
    await limiter(request)
    assert len(limiter._requests["ip:10.0.0.6"]) == 1


@pytest.mark.asyncio
async def test_retry_after_header_uses_window_remaining():
    limiter = _new_limiter(max_requests=1, window_seconds=10)
    request = _request(ip="10.0.0.7")

    base = 1_000_000.0
    with patch("plotlot.api.middleware.time.time", return_value=base):
        await limiter.check(request)

    with patch("plotlot.api.middleware.time.time", return_value=base + 3):
        with pytest.raises(HTTPException) as exc:
            await limiter.check(request)

    retry_after = int(exc.value.headers["Retry-After"])
    assert 7 <= retry_after <= 9


def test_singleton_rate_limiter_exists():
    from plotlot.api.middleware import rate_limiter

    assert isinstance(rate_limiter, RateLimiter)


def test_get_client_key_handles_request_without_state():
    limiter = _new_limiter()
    request = _request(ip="10.0.0.8")

    request_magic = MagicMock(spec=Request)
    del request_magic.state
    del request_magic.url

    if not hasattr(request_magic, "state"):
        return
    with patch.object(request, "state", new=MagicMock(spec=[])):

        class _NoState:
            pass

        no_state = _NoState()
        with patch("plotlot.api.middleware.getattr") as mock_getattr:

            def _side_effect(obj, name, *args, **kwargs):
                if obj is no_state and name == "user":
                    raise AttributeError("no state")
                return MagicMock()

            mock_getattr.side_effect = _side_effect
            key, allowed = limiter._get_client_key(request)
            assert key.startswith("ip:")
            assert allowed == limiter.max_requests
