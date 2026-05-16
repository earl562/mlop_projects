"""Regression tests for PlotLot MLflow tracing helpers."""

from unittest.mock import MagicMock, patch

from plotlot.observability.tracing import configure_mlflow, start_run, trace


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
        patch("plotlot.observability.tracing.socket.create_connection", side_effect=OSError("refused")),
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
