"""PlotLot configuration — all external service credentials and settings."""

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from pydantic import model_validator
from pydantic_settings import BaseSettings

# asyncpg-compatible URL query parameters (strip libpq-only params like channel_binding)
_ASYNCPG_PARAMS = {"sslmode", "ssl", "application_name", "options"}


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://plotlot:plotlot@localhost:5433/plotlot"

    @model_validator(mode="after")
    def _normalize_database_url(self) -> "Settings":
        """Rewrite DATABASE_URL for SQLAlchemy+asyncpg compatibility.

        Handles scheme rewriting (postgres:// → postgresql+asyncpg://) and
        strips libpq-only query params (e.g. channel_binding) that asyncpg
        doesn't understand.  Neon, Railway, and Supabase all need this.
        """
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://") and "+asyncpg" not in url:
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

        # Strip query params asyncpg doesn't support
        parsed = urlparse(url)
        if parsed.query:
            params = parse_qs(parsed.query)
            filtered = {k: v for k, v in params.items() if k in _ASYNCPG_PARAMS}
            url = urlunparse(parsed._replace(query=urlencode(filtered, doseq=True)))

        self.database_url = url
        return self

    # API keys
    geocodio_api_key: str = ""
    hf_token: str = ""
    openrouter_api_key: str = ""
    nvidia_api_key: str = ""

    # Jina.ai search
    jina_api_key: str = ""

    # Google Workspace (Sheets/Docs creation)
    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""

    # MLflow
    mlflow_tracking_uri: str = "sqlite:///mlruns/mlflow.db"
    mlflow_experiment_name: str = "plotlot-rag"

    # Logging
    log_json: bool = True
    log_level: str = "INFO"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
