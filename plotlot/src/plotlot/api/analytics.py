"""Lightweight in-memory API usage analytics.

Tracks request counts, latency percentiles, and error rates per endpoint.
Resets on service restart -- for persistent analytics, integrate with MLflow.
"""

import time
import logging
from collections import defaultdict
from threading import Lock

logger = logging.getLogger(__name__)

_lock = Lock()
_endpoint_stats: dict[str, dict] = defaultdict(lambda: {
    "count": 0,
    "errors": 0,
    "latencies": [],  # last 1000
})
_start_time: float = time.time()

MAX_LATENCIES = 1000


def record_request(endpoint: str, latency_ms: float, is_error: bool = False) -> None:
    """Record a request to an endpoint."""
    with _lock:
        stats = _endpoint_stats[endpoint]
        stats["count"] += 1
        if is_error:
            stats["errors"] += 1
        stats["latencies"].append(latency_ms)
        if len(stats["latencies"]) > MAX_LATENCIES:
            stats["latencies"] = stats["latencies"][-MAX_LATENCIES:]


def get_analytics() -> dict:
    """Get current analytics snapshot."""
    with _lock:
        uptime = time.time() - _start_time
        endpoints = {}
        total_requests = 0
        total_errors = 0

        for endpoint, stats in _endpoint_stats.items():
            count = stats["count"]
            errors = stats["errors"]
            latencies = sorted(stats["latencies"])
            total_requests += count
            total_errors += errors

            p50 = latencies[len(latencies) // 2] if latencies else 0
            p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0
            p99 = latencies[int(len(latencies) * 0.99)] if latencies else 0

            endpoints[endpoint] = {
                "count": count,
                "errors": errors,
                "error_rate": round(errors / count * 100, 1) if count > 0 else 0,
                "latency_p50_ms": round(p50, 1),
                "latency_p95_ms": round(p95, 1),
                "latency_p99_ms": round(p99, 1),
            }

        return {
            "uptime_seconds": round(uptime),
            "total_requests": total_requests,
            "total_errors": total_errors,
            "endpoints": endpoints,
        }


def reset() -> None:
    """Reset all counters (for testing)."""
    global _start_time
    with _lock:
        _endpoint_stats.clear()
        _start_time = time.time()
