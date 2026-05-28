"""Lightweight MLflow tracing wrapper — no-ops when MLflow is not installed.

Makes MLflow an optional dependency for production API deployment.
All tracing, metrics, and artifact logging gracefully degrade to no-ops.

Usage (replaces `import mlflow` in all modules):

    from plotlot.observability.tracing import mlflow, trace, start_span, start_run

    @trace()                        # decorator — works with or without MLflow
    async def my_function(): ...

    with start_span("step") as s:   # context manager — no-ops gracefully
        if s: s.set_inputs({...})

    with start_run(run_name="x"):   # MLflow run context — no-ops gracefully
        log_params({"key": "val"})
"""

import functools
import inspect
import logging
import socket
import sys
from contextlib import contextmanager
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

try:
    import mlflow as _mlflow

    mlflow = _mlflow
    _HAS_MLFLOW = True
    _MLFLOW_ENABLED = False
    logger.debug("MLflow available — tracing enabled")
except ImportError:
    mlflow = None  # type: ignore[assignment]
    _HAS_MLFLOW = False
    _MLFLOW_ENABLED = False
    logger.debug("MLflow not installed — tracing disabled")


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------


def trace(name: str | None = None, **kwargs):
    """Decorator: wraps function with MLflow trace if available."""

    def decorator(fn):
        traced_fn = None
        if _HAS_MLFLOW:
            try:
                traced_fn = (
                    _mlflow.trace(name=name, **kwargs)(fn) if name else _mlflow.trace(**kwargs)(fn)
                )
            except Exception as exc:
                logger.debug("MLflow trace wrapper unavailable — using passthrough: %s", exc)

        @functools.wraps(fn)
        def wrapper(*args, **kw):
            global _MLFLOW_ENABLED
            if traced_fn is not None and _MLFLOW_ENABLED:
                try:
                    return traced_fn(*args, **kw)
                except Exception as exc:
                    logger.warning("MLflow trace failed; disabling tracing: %s", exc)
                    _MLFLOW_ENABLED = False
            return fn(*args, **kw)

        @functools.wraps(fn)
        async def async_wrapper(*args, **kw):
            global _MLFLOW_ENABLED
            if traced_fn is not None and _MLFLOW_ENABLED:
                try:
                    return await traced_fn(*args, **kw)
                except Exception as exc:
                    logger.warning("MLflow trace failed; disabling tracing: %s", exc)
                    _MLFLOW_ENABLED = False
            return await fn(*args, **kw)

        return async_wrapper if inspect.iscoroutinefunction(fn) else wrapper

    return decorator


# ---------------------------------------------------------------------------
# Context managers
# ---------------------------------------------------------------------------


@contextmanager
def start_span(name: str = "span", **kwargs):
    """Context manager: MLflow span if available, otherwise no-op."""
    global _MLFLOW_ENABLED
    if not (_HAS_MLFLOW and _MLFLOW_ENABLED):
        yield _NoOpSpan()
        return

    span_cm = None
    try:
        span_cm = _mlflow.start_span(name=name, **kwargs)
        span = span_cm.__enter__()
    except Exception as exc:
        logger.warning("MLflow start_span unavailable; disabling tracing: %s", exc)
        _MLFLOW_ENABLED = False
        yield _NoOpSpan()
        return

    try:
        yield span
    finally:
        span_cm.__exit__(*sys.exc_info())


@contextmanager
def start_run(**kwargs):
    """Context manager: MLflow run if available, otherwise no-op.

    Defensively ends any orphaned active run before starting a new one.
    This prevents the 'Run with UUID ... is already active' error that
    blocks all subsequent requests when a previous run leaked (e.g., the
    streaming endpoint crashed mid-analysis).
    """
    global _MLFLOW_ENABLED
    if not (_HAS_MLFLOW and _MLFLOW_ENABLED):
        yield None
        return

    run_cm = None
    try:
        active = _mlflow.active_run()
        if active:
            logger.warning(
                "Ending orphaned MLflow run %s before starting new run",
                active.info.run_id,
            )
            _mlflow.end_run()
        run_cm = _mlflow.start_run(**kwargs)
        run = run_cm.__enter__()
    except Exception as exc:
        logger.warning("MLflow start_run unavailable; disabling tracing: %s", exc)
        _MLFLOW_ENABLED = False
        yield None
        return

    try:
        yield run
    finally:
        run_cm.__exit__(*sys.exc_info())


# ---------------------------------------------------------------------------
# Logging functions (no-op when MLflow absent)
# ---------------------------------------------------------------------------


def log_params(params: dict) -> None:
    if _HAS_MLFLOW and _MLFLOW_ENABLED:
        try:
            _mlflow.log_params(params)
        except Exception:
            pass


def log_metrics(metrics: dict, step: int | None = None) -> None:
    if _HAS_MLFLOW and _MLFLOW_ENABLED:
        try:
            _mlflow.log_metrics(metrics, step=step)
        except Exception:
            pass


def log_metric(key: str, value: float, step: int | None = None) -> None:
    if _HAS_MLFLOW and _MLFLOW_ENABLED:
        try:
            _mlflow.log_metric(key, value, step=step)
        except Exception:
            pass


def log_dict(data: dict, artifact_file: str) -> None:
    if _HAS_MLFLOW and _MLFLOW_ENABLED:
        try:
            _mlflow.log_dict(data, artifact_file)
        except Exception:
            pass


def log_text(text: str, artifact_file: str) -> None:
    if _HAS_MLFLOW and _MLFLOW_ENABLED:
        try:
            _mlflow.log_text(text, artifact_file)
        except Exception:
            pass


def log_artifact(path: str) -> None:
    if _HAS_MLFLOW and _MLFLOW_ENABLED:
        try:
            _mlflow.log_artifact(path)
        except Exception:
            pass


def set_tag(key: str, value: str) -> None:
    if _HAS_MLFLOW and _MLFLOW_ENABLED:
        try:
            _mlflow.set_tag(key, value)
        except Exception:
            pass


def set_tracking_uri(uri: str) -> None:
    if _HAS_MLFLOW and _MLFLOW_ENABLED:
        _mlflow.set_tracking_uri(uri)


def set_experiment(name: str) -> None:
    if _HAS_MLFLOW and _MLFLOW_ENABLED:
        _mlflow.set_experiment(name)


def enable_async_logging() -> None:
    if _HAS_MLFLOW and _MLFLOW_ENABLED:
        _mlflow.config.enable_async_logging()


def configure_mlflow(
    tracking_uri: str,
    experiment_name: str,
    *,
    enable_async_logging: bool = True,
) -> bool:
    """Configure MLflow, failing open when the tracking backend is unavailable."""
    global _MLFLOW_ENABLED
    if not _HAS_MLFLOW:
        return False

    parsed = urlparse(tracking_uri)
    if parsed.scheme in {"postgres", "postgresql"} and parsed.hostname and parsed.port:
        try:
            with socket.create_connection((parsed.hostname, parsed.port), timeout=1.0):
                pass
        except OSError:
            _MLFLOW_ENABLED = False
            return False

    try:
        _mlflow.set_tracking_uri(tracking_uri)
        _mlflow.set_experiment(experiment_name)
        if enable_async_logging:
            _mlflow.config.enable_async_logging()
        _MLFLOW_ENABLED = True
        return True
    except Exception:
        _MLFLOW_ENABLED = False
        return False


# ---------------------------------------------------------------------------
# No-op span for when MLflow is absent
# ---------------------------------------------------------------------------


class _NoOpSpan:
    """Dummy span that accepts set_inputs/set_outputs without error."""

    def set_inputs(self, inputs: dict) -> None:
        pass

    def set_outputs(self, outputs: dict) -> None:
        pass
