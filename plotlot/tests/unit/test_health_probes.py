"""Tests for deterministic deployed-health probing and failure classification."""

from __future__ import annotations

import io
import socket
from dataclasses import dataclass

from plotlot.health.probes import ProbeCategory, probe_health_url


@dataclass
class FakeResponse:
    body: bytes
    status: int = 200

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class SequenceOpener:
    def __init__(self, outcomes: list[object]) -> None:
        self._outcomes = iter(outcomes)
        self.calls: list[tuple[str, float]] = []

    def __call__(self, url: str, *, timeout: float) -> FakeResponse:
        self.calls.append((url, timeout))
        outcome = next(self._outcomes)
        if isinstance(outcome, BaseException):
            raise outcome
        assert isinstance(outcome, FakeResponse)
        return outcome


def test_probe_retries_timeouts_and_records_successful_recovery():
    opener = SequenceOpener(
        [
            socket.timeout("cold start"),
            TimeoutError("read timed out"),
            FakeResponse(b'{"status":"healthy"}'),
        ]
    )
    sleeps: list[float] = []

    result = probe_health_url(
        "https://example.test/health",
        attempts=3,
        timeout_seconds=8,
        backoff_seconds=0.25,
        opener=opener,
        sleeper=sleeps.append,
    )

    assert result.healthy is True
    assert result.category == ProbeCategory.HEALTHY
    assert len(result.attempts) == 3
    assert [attempt.category for attempt in result.attempts[:2]] == [
        ProbeCategory.APPLICATION_TIMEOUT,
        ProbeCategory.APPLICATION_TIMEOUT,
    ]
    assert sleeps == [0.25, 0.25]


def test_probe_classifies_invalid_json_without_hiding_response_body():
    opener = SequenceOpener([FakeResponse(b"render maintenance page")])

    result = probe_health_url(
        "https://example.test/health",
        attempts=1,
        opener=opener,
    )

    assert result.healthy is False
    assert result.category == ProbeCategory.INVALID_PAYLOAD
    assert result.attempts[0].response_excerpt == "render maintenance page"


def test_probe_classifies_unhealthy_payload():
    opener = SequenceOpener([FakeResponse(b'{"status":"degraded"}')])

    result = probe_health_url(
        "https://example.test/health",
        attempts=1,
        opener=opener,
    )

    assert result.healthy is False
    assert result.category == ProbeCategory.UNHEALTHY_PAYLOAD
    assert result.reported_status == "degraded"


def test_probe_rejects_invalid_configuration():
    opener = SequenceOpener([FakeResponse(io.BytesIO(b"").read())])

    try:
        probe_health_url("https://example.test/health", attempts=0, opener=opener)
    except ValueError as exc:
        assert str(exc) == "attempts must be positive"
    else:
        raise AssertionError("expected invalid attempts to raise ValueError")
