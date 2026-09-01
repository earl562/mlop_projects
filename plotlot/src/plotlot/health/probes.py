"""Bounded, evidence-rich HTTP health probing.

The nightly workflow uses this module directly so a Render cold start, an HTTP
failure, an invalid payload, and an explicitly degraded application are
reported as different operational conditions.
"""

from __future__ import annotations

import json
import os
import socket
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


class ProbeCategory(StrEnum):
    HEALTHY = "healthy"
    APPLICATION_TIMEOUT = "application_timeout"
    HTTP_ERROR = "http_error"
    TRANSPORT_ERROR = "transport_error"
    INVALID_PAYLOAD = "invalid_payload"
    UNHEALTHY_PAYLOAD = "unhealthy_payload"


@dataclass(frozen=True)
class ProbeAttempt:
    number: int
    category: ProbeCategory
    elapsed_seconds: float
    http_status: int | None = None
    reported_status: str | None = None
    response_excerpt: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class ProbeResult:
    url: str
    healthy: bool
    category: ProbeCategory
    attempts: tuple[ProbeAttempt, ...]
    reported_status: str | None = None


Opener = Callable[..., Any]
Sleeper = Callable[[float], None]
Clock = Callable[[], float]


def _excerpt(value: str, *, limit: int = 500) -> str:
    compact = " ".join(value.split())
    return compact[:limit]


def _timeout_from_url_error(exc: URLError) -> bool:
    reason = exc.reason
    return isinstance(reason, (socket.timeout, TimeoutError))


def _failure_result(url: str, attempts: list[ProbeAttempt]) -> ProbeResult:
    last = attempts[-1]
    return ProbeResult(
        url=url,
        healthy=False,
        category=last.category,
        attempts=tuple(attempts),
        reported_status=last.reported_status,
    )


def probe_health_url(
    url: str,
    *,
    attempts: int = 3,
    timeout_seconds: float = 8.0,
    backoff_seconds: float = 2.0,
    opener: Opener = urlopen,
    sleeper: Sleeper = time.sleep,
    clock: Clock = time.monotonic,
) -> ProbeResult:
    """Probe a JSON health endpoint with bounded retries and typed evidence."""

    if attempts < 1:
        raise ValueError("attempts must be positive")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if backoff_seconds < 0:
        raise ValueError("backoff_seconds cannot be negative")

    recorded: list[ProbeAttempt] = []
    for number in range(1, attempts + 1):
        started = clock()
        try:
            with opener(url, timeout=timeout_seconds) as response:
                raw_body = response.read()
                http_status = int(getattr(response, "status", 200))
            body = raw_body.decode("utf-8", errors="replace")
            elapsed = max(0.0, clock() - started)

            if not 200 <= http_status < 300:
                recorded.append(
                    ProbeAttempt(
                        number=number,
                        category=ProbeCategory.HTTP_ERROR,
                        elapsed_seconds=elapsed,
                        http_status=http_status,
                        response_excerpt=_excerpt(body),
                        error=f"unexpected HTTP status {http_status}",
                    )
                )
            else:
                try:
                    payload = json.loads(body)
                except json.JSONDecodeError as exc:
                    recorded.append(
                        ProbeAttempt(
                            number=number,
                            category=ProbeCategory.INVALID_PAYLOAD,
                            elapsed_seconds=elapsed,
                            http_status=http_status,
                            response_excerpt=_excerpt(body),
                            error=f"invalid JSON: {exc.msg}",
                        )
                    )
                else:
                    if not isinstance(payload, dict):
                        recorded.append(
                            ProbeAttempt(
                                number=number,
                                category=ProbeCategory.INVALID_PAYLOAD,
                                elapsed_seconds=elapsed,
                                http_status=http_status,
                                response_excerpt=_excerpt(body),
                                error="health payload must be a JSON object",
                            )
                        )
                    else:
                        reported = str(payload.get("status") or "")
                        if reported == "healthy":
                            success = ProbeAttempt(
                                number=number,
                                category=ProbeCategory.HEALTHY,
                                elapsed_seconds=elapsed,
                                http_status=http_status,
                                reported_status=reported,
                                response_excerpt=_excerpt(body),
                            )
                            recorded.append(success)
                            return ProbeResult(
                                url=url,
                                healthy=True,
                                category=ProbeCategory.HEALTHY,
                                attempts=tuple(recorded),
                                reported_status=reported,
                            )
                        recorded.append(
                            ProbeAttempt(
                                number=number,
                                category=ProbeCategory.UNHEALTHY_PAYLOAD,
                                elapsed_seconds=elapsed,
                                http_status=http_status,
                                reported_status=reported or None,
                                response_excerpt=_excerpt(body),
                                error=f"reported status is {reported!r}",
                            )
                        )
        except HTTPError as exc:
            elapsed = max(0.0, clock() - started)
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            recorded.append(
                ProbeAttempt(
                    number=number,
                    category=ProbeCategory.HTTP_ERROR,
                    elapsed_seconds=elapsed,
                    http_status=exc.code,
                    response_excerpt=_excerpt(body) if body else None,
                    error=str(exc),
                )
            )
        except (socket.timeout, TimeoutError) as exc:
            recorded.append(
                ProbeAttempt(
                    number=number,
                    category=ProbeCategory.APPLICATION_TIMEOUT,
                    elapsed_seconds=max(0.0, clock() - started),
                    error=str(exc) or type(exc).__name__,
                )
            )
        except URLError as exc:
            category = (
                ProbeCategory.APPLICATION_TIMEOUT
                if _timeout_from_url_error(exc)
                else ProbeCategory.TRANSPORT_ERROR
            )
            recorded.append(
                ProbeAttempt(
                    number=number,
                    category=category,
                    elapsed_seconds=max(0.0, clock() - started),
                    error=str(exc),
                )
            )
        except OSError as exc:
            recorded.append(
                ProbeAttempt(
                    number=number,
                    category=ProbeCategory.TRANSPORT_ERROR,
                    elapsed_seconds=max(0.0, clock() - started),
                    error=str(exc),
                )
            )

        if number < attempts:
            sleeper(backoff_seconds)

    return _failure_result(url, recorded)


def main() -> int:
    url = os.environ.get("PLOTLOT_HEALTH_URL") or "https://plotlot-api.onrender.com/health"
    attempts = int(os.environ.get("PLOTLOT_HEALTH_ATTEMPTS", "3"))
    timeout_seconds = float(os.environ.get("PLOTLOT_HEALTH_TIMEOUT_SECONDS", "8"))
    backoff_seconds = float(os.environ.get("PLOTLOT_HEALTH_BACKOFF_SECONDS", "2"))
    result = probe_health_url(
        url,
        attempts=attempts,
        timeout_seconds=timeout_seconds,
        backoff_seconds=backoff_seconds,
    )
    print(json.dumps(asdict(result), indent=2))
    return 0 if result.healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
