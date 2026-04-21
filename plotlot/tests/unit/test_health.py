"""Tests for the /health endpoint response structure."""

from unittest.mock import AsyncMock, MagicMock, patch


class TestHealthEndpoint:
    async def test_health_returns_checks_structure(self):
        """Health response includes database, last_ingestion, mlflow, and runtime checks."""
        from plotlot.api.main import _runtime_health, health

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        mock_session.execute.return_value = mock_result

        _runtime_health["startup_mode"] = "healthy"
        _runtime_health["startup_warnings"] = []
        with (
            patch("plotlot.api.main.get_session", return_value=mock_session),
            patch("mlflow.search_experiments", return_value=[]),
            patch("plotlot.api.main.settings") as mock_settings,
        ):
            # Ensure tests don't depend on developer machine env (.env, exported keys, etc.)
            mock_settings.database_url = "postgresql+asyncpg://plotlot:plotlot@localhost:5433/plotlot"
            mock_settings.database_require_ssl = False
            mock_settings.openai_api_key = ""
            mock_settings.openai_access_token = ""
            mock_settings.openrouter_api_key = ""
            mock_settings.use_codex_oauth = False
            result = await health()

        assert "status" in result
        assert "checks" in result
        assert "database" in result["checks"]
        assert "last_ingestion" in result["checks"]
        assert "mlflow" in result["checks"]
        assert result["database_target"]["host"] == "localhost"
        assert result["database_target"]["port"] == 5433
        assert result["database_target"]["database"] == "plotlot"
        assert result["capabilities"]["db_backed_analysis_ready"] is True
        assert result["capabilities"]["portfolio_ready"] is True
        assert result["capabilities"]["agent_chat_ready"] is False
        assert result["capability_details"]["db_backed_analysis_ready"]["reason"] == "database_ok"
        assert result["capability_details"]["db_backed_analysis_ready"]["blocked_by"] == []
        assert result["capability_details"]["db_backed_analysis_ready"]["dependencies"] == ["database"]
        assert result["capability_details"]["agent_chat_ready"]["reason"] == "llm_credentials_missing"
        assert result["capability_details"]["agent_chat_ready"]["blocked_by"] == ["llm_credentials"]
        assert result["capability_details"]["agent_chat_ready"]["dependencies"] == ["llm_credentials"]
        assert result["runtime"]["startup_mode"] == "healthy"
        assert result["runtime"]["startup_warnings"] == []

    async def test_health_degraded_on_db_failure(self):
        """Health returns degraded when DB is unreachable."""
        from plotlot.api.main import _runtime_health, health

        _runtime_health["startup_mode"] = "degraded"
        _runtime_health["startup_warnings"] = ["database_unavailable"]
        with patch("plotlot.api.main.get_session", side_effect=ConnectionError("refused")):
            result = await health()

        assert result["status"] == "degraded"
        assert "error" in result["checks"]["database"]
        assert result["database_target"]["host"] == "localhost"
        assert result["capabilities"]["db_backed_analysis_ready"] is False
        assert result["capabilities"]["portfolio_ready"] is False
        assert result["capability_details"]["db_backed_analysis_ready"]["reason"] == "database_unavailable"
        assert result["capability_details"]["db_backed_analysis_ready"]["blocked_by"] == ["database"]
        assert result["capability_details"]["db_backed_analysis_ready"]["dependencies"] == ["database"]
        assert result["runtime"]["startup_mode"] == "degraded"
        assert "database_unavailable" in result["runtime"]["startup_warnings"]

    async def test_health_reports_agent_chat_ready_when_credentials_present(self):
        """Health should report chat readiness when OpenAI credentials exist."""
        from plotlot.api.main import _runtime_health, health

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        mock_session.execute.return_value = mock_result

        _runtime_health["startup_mode"] = "healthy"
        _runtime_health["startup_warnings"] = []
        with (
            patch("plotlot.api.main.get_session", return_value=mock_session),
            patch("mlflow.search_experiments", return_value=[]),
            patch("plotlot.api.main.settings") as mock_settings,
        ):
            mock_settings.database_url = "postgresql+asyncpg://plotlot:plotlot@localhost:5433/plotlot"
            mock_settings.database_require_ssl = False
            mock_settings.openai_api_key = "test-key"
            mock_settings.openai_access_token = ""
            mock_settings.openrouter_api_key = ""
            mock_settings.use_codex_oauth = False
            result = await health()

        assert result["capabilities"]["agent_chat_ready"] is True
        assert result["capability_details"]["agent_chat_ready"]["reason"] == "llm_credentials_present"
        assert result["capability_details"]["agent_chat_ready"]["blocked_by"] == []
        assert result["capability_details"]["agent_chat_ready"]["dependencies"] == ["llm_credentials"]

    async def test_health_reports_agent_chat_ready_with_openrouter_only(self):
        """Health should report chat readiness when OpenRouter credentials exist."""
        from plotlot.api.main import _runtime_health, health

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        mock_session.execute.return_value = mock_result

        _runtime_health["startup_mode"] = "healthy"
        _runtime_health["startup_warnings"] = []
        with (
            patch("plotlot.api.main.get_session", return_value=mock_session),
            patch("mlflow.search_experiments", return_value=[]),
            patch("plotlot.api.main.settings") as mock_settings,
        ):
            mock_settings.database_url = "postgresql+asyncpg://plotlot:plotlot@localhost:5433/plotlot"
            mock_settings.database_require_ssl = False
            mock_settings.openai_api_key = ""
            mock_settings.openai_access_token = ""
            mock_settings.openrouter_api_key = "or-key"
            mock_settings.use_codex_oauth = False
            result = await health()

        assert result["capabilities"]["agent_chat_ready"] is True
        assert result["capability_details"]["agent_chat_ready"]["reason"] == "llm_credentials_present"

    async def test_health_reports_agent_chat_ready_with_saved_codex_oauth(self):
        """Health should treat saved Codex OAuth tokens as chat-ready."""
        from plotlot.api.main import _runtime_health, health

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        mock_session.execute.return_value = mock_result

        _runtime_health["startup_mode"] = "healthy"
        _runtime_health["startup_warnings"] = []
        with (
            patch("plotlot.api.main.get_session", return_value=mock_session),
            patch("mlflow.search_experiments", return_value=[]),
            patch("plotlot.api.main.has_saved_tokens", return_value=True),
            patch("plotlot.api.main.settings") as mock_settings,
        ):
            mock_settings.database_url = "postgresql+asyncpg://plotlot:plotlot@localhost:5433/plotlot"
            mock_settings.database_require_ssl = False
            mock_settings.openai_api_key = ""
            mock_settings.openai_access_token = ""
            mock_settings.openrouter_api_key = ""
            mock_settings.use_codex_oauth = True
            mock_settings.codex_auth_file = "~/.codex/auth.json"
            result = await health()

        assert result["capabilities"]["agent_chat_ready"] is True
