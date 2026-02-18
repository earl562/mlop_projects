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
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

try:
    import mlflow as _mlflow

    mlflow = _mlflow
    _HAS_MLFLOW = True
    logger.debug("MLflow available — tracing enabled")
except ImportError:
    mlflow = None  # type: ignore[assignment]
    _HAS_MLFLOW = False
    logger.debug("MLflow not installed — tracing disabled")


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def trace(name: str | None = None, **kwargs):
    """Decorator: wraps function with MLflow trace if available."""
    if _HAS_MLFLOW:
        return _mlflow.trace(name=name, **kwargs) if name else _mlflow.trace(**kwargs)

    def passthrough(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kw):
            return fn(*args, **kw)

        @functools.wraps(fn)
        async def async_wrapper(*args, **kw):
            return await fn(*args, **kw)

        import asyncio
        return async_wrapper if asyncio.iscoroutinefunction(fn) else wrapper

    return passthrough


# ---------------------------------------------------------------------------
# Context managers
# ---------------------------------------------------------------------------

@contextmanager
def start_span(name: str = "span", **kwargs):
    """Context manager: MLflow span if available, otherwise no-op."""
    if _HAS_MLFLOW:
        with _mlflow.start_span(name=name, **kwargs) as span:
            yield span
    else:
        yield _NoOpSpan()


@contextmanager
def start_run(**kwargs):
    """Context manager: MLflow run if available, otherwise no-op."""
    if _HAS_MLFLOW:
        with _mlflow.start_run(**kwargs) as run:
            yield run
    else:
        yield None


# ---------------------------------------------------------------------------
# Logging functions (no-op when MLflow absent)
# ---------------------------------------------------------------------------

def log_params(params: dict) -> None:
    if _HAS_MLFLOW:
        try:
            _mlflow.log_params(params)
        except Exception:
            pass


def log_metrics(metrics: dict, step: int | None = None) -> None:
    if _HAS_MLFLOW:
        try:
            _mlflow.log_metrics(metrics, step=step)
        except Exception:
            pass


def log_metric(key: str, value: float, step: int | None = None) -> None:
    if _HAS_MLFLOW:
        try:
            _mlflow.log_metric(key, value, step=step)
        except Exception:
            pass


def log_dict(data: dict, artifact_file: str) -> None:
    if _HAS_MLFLOW:
        try:
            _mlflow.log_dict(data, artifact_file)
        except Exception:
            pass


def log_text(text: str, artifact_file: str) -> None:
    if _HAS_MLFLOW:
        try:
            _mlflow.log_text(text, artifact_file)
        except Exception:
            pass


def log_artifact(path: str) -> None:
    if _HAS_MLFLOW:
        try:
            _mlflow.log_artifact(path)
        except Exception:
            pass


def set_tag(key: str, value: str) -> None:
    if _HAS_MLFLOW:
        try:
            _mlflow.set_tag(key, value)
        except Exception:
            pass


def set_tracking_uri(uri: str) -> None:
    if _HAS_MLFLOW:
        _mlflow.set_tracking_uri(uri)


def set_experiment(name: str) -> None:
    if _HAS_MLFLOW:
        _mlflow.set_experiment(name)


def enable_async_logging() -> None:
    if _HAS_MLFLOW:
        _mlflow.config.enable_async_logging()


# ---------------------------------------------------------------------------
# No-op span for when MLflow is absent
# ---------------------------------------------------------------------------

class _NoOpSpan:
    """Dummy span that accepts set_inputs/set_outputs without error."""

    def set_inputs(self, inputs: dict) -> None:
        pass

    def set_outputs(self, outputs: dict) -> None:
        pass
