"""Structured JSON logging with async-safe correlation IDs.

Production pattern: every log line is JSON with a correlation_id that
traces a single request across all async functions it touches. This is
what Datadog, Grafana Loki, and CloudWatch expect for log aggregation.
"""

import json
import logging
from contextvars import ContextVar
from datetime import datetime, timezone

# Async-safe correlation ID — propagates through await chains automatically
correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    """Return the current correlation ID, or empty string if not set."""
    return correlation_id.get()


class JSONFormatter(logging.Formatter):
    """Format log records as single-line JSON."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        cid = correlation_id.get()
        if cid:
            log_entry["correlation_id"] = cid

        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Include any extra fields passed via logger.info("msg", extra={...})
        for key in ("county", "municipality", "address", "step", "duration_ms"):
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val

        return json.dumps(log_entry, default=str)


def setup_logging(json_format: bool = True, level: str = "INFO") -> None:
    """Configure root logger with JSON or text format.

    Args:
        json_format: True for JSON (production), False for text (local dev).
        level: Log level string (DEBUG, INFO, WARNING, ERROR).
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates
    root.handlers.clear()

    handler = logging.StreamHandler()
    if json_format:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    root.addHandler(handler)

    # Quiet noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
