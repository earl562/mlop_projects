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
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)
SpanAttribute = str | int | float | bool

try:
    from opentelemetry import trace as _otel_trace
    from opentelemetry.sdk.resources import Resource as _Resource
    from opentelemetry.sdk.trace import TracerProvider as _TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor as _BatchSpanProcessor,
    )
    from opentelemetry.sdk.trace.export import (
        ConsoleSpanExporter as _ConsoleSpanExporter,
    )

    Resource: Any = _Resource
    TracerProvider: Any = _TracerProvider
    BatchSpanProcessor: Any = _BatchSpanProcessor
    ConsoleSpanExporter: Any = _ConsoleSpanExporter
    _OTEL_TRACER: Any = _otel_trace.get_tracer("plotlot")
    _HAS_OTEL = True
except ImportError:
    _OTEL_TRACER = None
    _HAS_OTEL = False
    Resource = None
    TracerProvider = None
    BatchSpanProcessor = None
    ConsoleSpanExporter = None

_OTEL_CONFIGURED = False

try:
    import mlflow as _mlflow

    mlflow = _mlflow
    _HAS_MLFLOW = True
    _MLFLOW_ENABLED = False
    _MLFLOW_TRACING_ENABLED = False
    logger.debug("MLflow available — tracing enabled")
except ImportError:
    mlflow = None  # type: ignore[assignment]
    _HAS_MLFLOW = False
    _MLFLOW_ENABLED = False
    _MLFLOW_TRACING_ENABLED = False
    logger.debug("MLflow not installed — tracing disabled")


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------


def trace(name: str | None = None, **kwargs):
    def decorator(fn):
        span_name = name or fn.__name__

        def open_span():
            global _MLFLOW_ENABLED
            if not (_HAS_MLFLOW and _MLFLOW_ENABLED and _MLFLOW_TRACING_ENABLED):
                return None
            try:
                span_cm = _mlflow.start_span(name=span_name, **kwargs)
                span = span_cm.__enter__()
                return span_cm, span
            except Exception as exc:
                logger.warning("MLflow trace unavailable; disabling tracing: %s", exc)
                _MLFLOW_ENABLED = False
                return None

        def close_span(span_cm, exc_info) -> None:
            global _MLFLOW_ENABLED
            try:
                span_cm.__exit__(*exc_info)
            except Exception as exc:
                logger.warning("MLflow trace export failed; disabling tracing: %s", exc)
                _MLFLOW_ENABLED = False

        @functools.wraps(fn)
        def wrapper(*args, **kw):
            opened = open_span()
            if opened is None:
                return fn(*args, **kw)
            span_cm, span = opened
            exc_info = (None, None, None)
            try:
                _set_span_data(span.set_inputs, _trace_inputs(fn, args, kw))
                result = fn(*args, **kw)
                _set_span_data(span.set_outputs, result)
                return result
            except BaseException:
                exc_info = sys.exc_info()
                raise
            finally:
                close_span(span_cm, exc_info)

        @functools.wraps(fn)
        async def async_wrapper(*args, **kw):
            opened = open_span()
            if opened is None:
                return await fn(*args, **kw)
            span_cm, span = opened
            exc_info = (None, None, None)
            try:
                _set_span_data(span.set_inputs, _trace_inputs(fn, args, kw))
                result = await fn(*args, **kw)
                _set_span_data(span.set_outputs, result)
                return result
            except BaseException:
                exc_info = sys.exc_info()
                raise
            finally:
                close_span(span_cm, exc_info)

        return async_wrapper if inspect.iscoroutinefunction(fn) else wrapper

    return decorator


def _trace_inputs(fn, args: tuple, kwargs: dict) -> dict:
    try:
        return dict(inspect.signature(fn).bind_partial(*args, **kwargs).arguments)
    except (TypeError, ValueError):
        return {"args": args, "kwargs": kwargs}


def _set_span_data(setter, value) -> None:
    try:
        setter(value)
    except Exception as exc:
        logger.debug("MLflow span data unavailable: %s", exc)


# ---------------------------------------------------------------------------
# Context managers
# ---------------------------------------------------------------------------


@contextmanager
def start_span(name: str = "span", **kwargs):
    """Context manager: MLflow span if available, otherwise no-op."""
    global _MLFLOW_ENABLED
    if not (_HAS_MLFLOW and _MLFLOW_ENABLED and _MLFLOW_TRACING_ENABLED):
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
        try:
            span_cm.__exit__(*sys.exc_info())
        except Exception as exc:
            logger.warning("MLflow span export failed; disabling tracing: %s", exc)
            _MLFLOW_ENABLED = False


@contextmanager
def start_otel_span(
    name: str,
    attributes: dict[str, SpanAttribute | None] | None = None,
):
    if not (_HAS_OTEL and _OTEL_TRACER is not None):
        yield _NoOpSpan()
        return

    cleaned_attributes = (
        {key: value for key, value in attributes.items() if value is not None}
        if attributes
        else None
    )
    span_cm = None
    try:
        span_cm = _OTEL_TRACER.start_as_current_span(name, attributes=cleaned_attributes)
        span = span_cm.__enter__()
    except Exception as exc:
        logger.debug("OpenTelemetry span unavailable: %s", exc)
        yield _NoOpSpan()
        return

    try:
        yield span
    finally:
        span_cm.__exit__(*sys.exc_info())


@contextmanager
def start_otel_span(
    name: str,
    attributes: dict[str, SpanAttribute | None] | None = None,
):
    if not (_HAS_OTEL and _OTEL_TRACER is not None):
        yield _NoOpSpan()
        return

    cleaned_attributes = (
        {key: value for key, value in attributes.items() if value is not None}
        if attributes
        else None
    )
    span_cm = None
    try:
        span_cm = _OTEL_TRACER.start_as_current_span(name, attributes=cleaned_attributes)
        span = span_cm.__enter__()
    except Exception as exc:
        logger.debug("OpenTelemetry span unavailable: %s", exc)
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
    enable_async_logging: bool = False,
    enable_tracing: bool = False,
) -> bool:
    """Configure MLflow, failing open when the tracking backend is unavailable."""
    global _MLFLOW_ENABLED, _MLFLOW_TRACING_ENABLED
    if not _HAS_MLFLOW:
        return False

    parsed = urlparse(tracking_uri)
    if parsed.scheme in {"postgres", "postgresql"} and parsed.hostname and parsed.port:
        try:
            with socket.create_connection((parsed.hostname, parsed.port), timeout=1.0):
                pass
        except OSError:
            _MLFLOW_ENABLED = False
            _MLFLOW_TRACING_ENABLED = False
            return False

    try:
        _mlflow.set_tracking_uri(tracking_uri)
        _mlflow.set_experiment(experiment_name)
        _mlflow.config.enable_async_logging(enable_async_logging)
        _MLFLOW_ENABLED = True
        _MLFLOW_TRACING_ENABLED = enable_tracing
        return True
    except Exception:
        _MLFLOW_ENABLED = False
        _MLFLOW_TRACING_ENABLED = False
        return False


def configure_otel(
    service_name: str,
    service_version: str,
    *,
    console_exporter: bool = False,
) -> bool:
    global _OTEL_CONFIGURED, _OTEL_TRACER
    if not _HAS_OTEL:
        return False
    if _OTEL_CONFIGURED:
        return True

    try:
        provider = TracerProvider(
            resource=Resource.create(
                {
                    "service.name": service_name,
                    "service.version": service_version,
                }
            )
        )
        if console_exporter:
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        _otel_trace.set_tracer_provider(provider)
        _OTEL_TRACER = _otel_trace.get_tracer(service_name)
        _OTEL_CONFIGURED = True
        return True
    except Exception as exc:
        logger.warning("OpenTelemetry configuration unavailable: %s", exc)
        return False


def configure_otel(
    service_name: str,
    service_version: str,
    *,
    console_exporter: bool = False,
) -> bool:
    global _OTEL_CONFIGURED, _OTEL_TRACER
    if not _HAS_OTEL:
        return False
    if _OTEL_CONFIGURED:
        return True

    try:
        provider = TracerProvider(
            resource=Resource.create(
                {
                    "service.name": service_name,
                    "service.version": service_version,
                }
            )
        )
        if console_exporter:
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        _otel_trace.set_tracer_provider(provider)
        _OTEL_TRACER = _otel_trace.get_tracer(service_name)
        _OTEL_CONFIGURED = True
        return True
    except Exception as exc:
        logger.warning("OpenTelemetry configuration unavailable: %s", exc)
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

    def set_attribute(self, key: str, value: SpanAttribute) -> None:
        pass
