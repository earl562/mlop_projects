"""Regression tests for PlotLot MLflow tracing helpers."""

from unittest.mock import MagicMock, patch

from plotlot.observability.tracing import configure_mlflow


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
