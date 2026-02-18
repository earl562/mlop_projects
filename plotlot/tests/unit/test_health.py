"""Tests for the /health endpoint response structure."""

from unittest.mock import AsyncMock, MagicMock, patch


class TestHealthEndpoint:
    async def test_health_returns_checks_structure(self):
        """Health response includes database, last_ingestion, and mlflow checks."""
        from plotlot.api.main import health

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        mock_session.execute.return_value = mock_result

        with (
            patch("plotlot.api.main.get_session", return_value=mock_session),
            patch("mlflow.search_experiments", return_value=[]),
        ):
            result = await health()

        assert "status" in result
        assert "checks" in result
        assert "database" in result["checks"]
        assert "last_ingestion" in result["checks"]
        assert "mlflow" in result["checks"]

    async def test_health_degraded_on_db_failure(self):
        """Health returns degraded when DB is unreachable."""
        from plotlot.api.main import health

        with patch("plotlot.api.main.get_session", side_effect=ConnectionError("refused")):
            result = await health()

        assert result["status"] == "degraded"
        assert "error" in result["checks"]["database"]
