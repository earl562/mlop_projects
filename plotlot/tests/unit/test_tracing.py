from unittest.mock import MagicMock, patch

from plotlot.observability.tracing import (
    configure_mlflow,
    configure_otel,
    start_run,
    start_span,
    trace,
)


def test_configure_mlflow_fails_open_when_tracking_backend_raises():
    mock_mlflow = MagicMock()
    mock_mlflow.set_tracking_uri.return_value = None
    mock_mlflow.set_experiment.side_effect = RuntimeError("tracking backend unavailable")
    mock_mlflow.config = MagicMock()

    with (
        patch("plotlot.observability.tracing._HAS_MLFLOW", True),
        patch("plotlot.observability.tracing._mlflow", mock_mlflow),
    ):
        result = configure_mlflow(
            "sqlite:///tmp/mlflow.db",
            "plotlot",
        )

    assert result is False
    mock_mlflow.set_tracking_uri.assert_called_once()
    mock_mlflow.set_experiment.assert_called_once()


def test_configure_mlflow_short_circuits_when_tracking_backend_unreachable():
    mock_mlflow = MagicMock()
    mock_mlflow.set_tracking_uri.return_value = None
    mock_mlflow.set_experiment.return_value = None
    mock_mlflow.config = MagicMock()

    with (
        patch("plotlot.observability.tracing._HAS_MLFLOW", True),
        patch("plotlot.observability.tracing._mlflow", mock_mlflow),
        patch(
            "plotlot.observability.tracing.socket.create_connection", side_effect=OSError("refused")
        ),
    ):
        result = configure_mlflow(
            "postgresql://plotlot:plotlot@localhost:5433/plotlot",
            "plotlot",
        )

    assert result is False
    mock_mlflow.set_tracking_uri.assert_not_called()
    mock_mlflow.set_experiment.assert_not_called()


def test_start_run_fails_open_when_mlflow_run_creation_raises():
    mock_mlflow = MagicMock()
    mock_mlflow.active_run.return_value = None
    mock_mlflow.start_run.side_effect = RuntimeError("Could not find experiment with ID 0")

    with (
        patch("plotlot.observability.tracing._HAS_MLFLOW", True),
        patch("plotlot.observability.tracing._MLFLOW_ENABLED", True),
        patch("plotlot.observability.tracing._mlflow", mock_mlflow),
    ):
        with start_run(run_name="stream") as run:
            assert run is None

    mock_mlflow.active_run.assert_called_once()
    mock_mlflow.start_run.assert_called_once_with(run_name="stream")


def test_trace_decorator_executes_function_once_when_trace_export_raises():
    calls = 0
    span_cm = MagicMock()
    span_cm.__enter__.return_value = MagicMock()
    span_cm.__exit__.side_effect = RuntimeError("trace export failed")
    mock_mlflow = MagicMock()
    mock_mlflow.start_span.return_value = span_cm

    with (
        patch("plotlot.observability.tracing._HAS_MLFLOW", True),
        patch("plotlot.observability.tracing._MLFLOW_ENABLED", True),
        patch("plotlot.observability.tracing._MLFLOW_TRACING_ENABLED", True),
        patch("plotlot.observability.tracing._mlflow", mock_mlflow),
    ):

        @trace(name="unit")
        def traced_function() -> str:
            nonlocal calls
            calls += 1
            return "ok"

        assert traced_function() == "ok"
        assert calls == 1
        mock_mlflow.start_span.assert_called_once_with(name="unit")


def test_start_span_noops_when_mlflow_tracing_is_disabled():
    mock_mlflow = MagicMock()

    with (
        patch("plotlot.observability.tracing._HAS_MLFLOW", True),
        patch("plotlot.observability.tracing._MLFLOW_ENABLED", True),
        patch("plotlot.observability.tracing._MLFLOW_TRACING_ENABLED", False),
        patch("plotlot.observability.tracing._mlflow", mock_mlflow),
    ):
        with start_span(name="disabled") as span:
            span.set_inputs({"address": "623 4TH ST"})

    mock_mlflow.start_span.assert_not_called()


def test_configure_mlflow_disables_async_logging_by_default():
    mock_mlflow = MagicMock()

    with (
        patch("plotlot.observability.tracing._HAS_MLFLOW", True),
        patch("plotlot.observability.tracing._mlflow", mock_mlflow),
    ):
        assert configure_mlflow("sqlite:///tmp/mlflow.db", "plotlot") is True

    mock_mlflow.config.enable_async_logging.assert_called_once_with(False)


def test_configure_otel_returns_false_when_opentelemetry_is_unavailable():
    with patch("plotlot.observability.tracing._HAS_OTEL", False):
        assert configure_otel("plotlot", "2.0.0") is False


def test_configure_otel_sets_provider_and_console_exporter_when_enabled():
    mock_trace = MagicMock()
    mock_provider = MagicMock()
    mock_resource = MagicMock()
    mock_processor = MagicMock()
    mock_exporter = MagicMock()

    with (
        patch("plotlot.observability.tracing._HAS_OTEL", True),
        patch("plotlot.observability.tracing._OTEL_CONFIGURED", False),
        patch("plotlot.observability.tracing._otel_trace", mock_trace),
        patch("plotlot.observability.tracing.TracerProvider", return_value=mock_provider),
        patch("plotlot.observability.tracing.Resource.create", return_value=mock_resource),
        patch("plotlot.observability.tracing.BatchSpanProcessor", return_value=mock_processor),
        patch("plotlot.observability.tracing.ConsoleSpanExporter", return_value=mock_exporter),
    ):
        result = configure_otel("plotlot-api", "2.0.0", console_exporter=True)

    assert result is True
    mock_trace.set_tracer_provider.assert_called_once_with(mock_provider)
    mock_trace.get_tracer.assert_called_once_with("plotlot-api")
    mock_provider.add_span_processor.assert_called_once_with(mock_processor)
