from unittest.mock import MagicMock, patch

from plotlot.observability.tracing import configure_mlflow, configure_otel, start_run, trace


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


def test_trace_decorator_fails_open_when_mlflow_wrapper_raises():
    def broken_trace(**_kwargs):
        def decorate(fn):
            def wrapped(*_args, **_kw):
                raise RuntimeError("Detected out-of-date database schema")

            return wrapped

        return decorate

    mock_mlflow = MagicMock()
    mock_mlflow.trace.side_effect = broken_trace

    with (
        patch("plotlot.observability.tracing._HAS_MLFLOW", True),
        patch("plotlot.observability.tracing._MLFLOW_ENABLED", True),
        patch("plotlot.observability.tracing._mlflow", mock_mlflow),
    ):

        @trace(name="unit")
        def traced_function() -> str:
            return "ok"

        assert traced_function() == "ok"


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
