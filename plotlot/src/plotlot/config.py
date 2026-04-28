"""PlotLot configuration — all external service credentials and settings."""

from urllib.parse import parse_qs, urlparse, urlunparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings

from plotlot.oauth.openai_auth import DEFAULT_AUTHORIZE_URL, DEFAULT_REDIRECT_URI, DEFAULT_TOKEN_URL


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://plotlot:plotlot@localhost:5433/plotlot"
    database_require_ssl: bool = False

    @model_validator(mode="after")
    def _normalize_database_url(self) -> "Settings":
        """Rewrite DATABASE_URL for SQLAlchemy+asyncpg compatibility.

        Handles scheme rewriting (postgres:// → postgresql+asyncpg://) and
        strips ALL query params (asyncpg doesn't accept libpq params like
        sslmode, channel_binding through the URL).  SSL is detected from
        sslmode=require and stored as database_require_ssl for the engine.

        Also auto-derives MLflow tracking URI from DATABASE_URL when not
        explicitly set — ensures MLflow persists to Neon PostgreSQL in
        production instead of ephemeral sqlite on Render's /tmp.
        """
        raw_url = self.database_url

        # --- Derive MLflow URI from DATABASE_URL (before asyncpg rewrite) ---
        # Only auto-derive when MLFLOW_TRACKING_URI was NOT explicitly set.
        # Check the environment directly; the default is sqlite:///mlruns/mlflow.db.
        import os

        _mlflow_explicitly_set = "MLFLOW_TRACKING_URI" in os.environ
        if not _mlflow_explicitly_set and self.mlflow_tracking_uri == "sqlite:///mlruns/mlflow.db":
            mlflow_url = raw_url
            if mlflow_url.startswith("postgres://"):
                mlflow_url = mlflow_url.replace("postgres://", "postgresql://", 1)
            elif "+asyncpg" in mlflow_url:
                mlflow_url = mlflow_url.replace("postgresql+asyncpg://", "postgresql://", 1)
            # Keep query params intact (sslmode=require) — psycopg2 handles them
            self.mlflow_tracking_uri = mlflow_url

        # --- Rewrite for asyncpg ---
        url = raw_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://") and "+asyncpg" not in url:
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

        # Detect SSL requirement, then strip all query params
        parsed = urlparse(url)
        if parsed.query:
            params = parse_qs(parsed.query)
            if "sslmode" in params and params["sslmode"][0] in (
                "require",
                "verify-ca",
                "verify-full",
            ):
                self.database_require_ssl = True
            url = urlunparse(parsed._replace(query=""))

        self.database_url = url
        return self

    # Auth (opt-in — app works without auth configured)
    auth_enabled: bool = False
    # Clerk JWT verification (RS256 via JWKS)
    clerk_jwks_url: str = ""  # e.g. https://<instance>.clerk.accounts.dev/.well-known/jwks.json
    # Stripe billing
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_pro_price_id: str = ""

    # Rate limiting
    rate_limit_max_requests: int = 30
    rate_limit_window_seconds: int = 60

    # API keys
    geocodio_api_key: str = ""
    hf_token: str = ""
    nvidia_api_key: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_model: str = "nvidia/llama-3.3-nemotron-super-49b-v1.5"
    nvidia_fallback_model: str = "minimaxai/minimax-m2.5"
    anthropic_api_key: str = ""
    google_api_key: str = ""
    openai_api_key: str = ""
    openai_access_token: str = ""  # OAuth-provided bearer token
    openai_base_url: str = "https://api.openai.com/v1"
    # Optional scoping for legacy user keys / multi-org accounts.
    # See: https://platform.openai.com/docs/api-reference/debugging-requests
    openai_organization: str = ""
    openai_project: str = ""
    openai_model: str = "gpt-4.1"
    openai_reasoning_effort: str = "medium"
    # Local dev convenience: pull the Codex OAuth token from ~/.codex/auth.json.
    # Opt-in via PLOTLOT_USE_CODEX_OAUTH=1 (kept false by default for safety).
    use_codex_oauth: bool = Field(default=False, validation_alias="PLOTLOT_USE_CODEX_OAUTH")
    codex_auth_file: str = Field(default="~/.codex/auth.json", validation_alias="PLOTLOT_CODEX_AUTH_FILE")
    openai_oauth_client_id: str = ""
    openai_oauth_authorize_url: str = DEFAULT_AUTHORIZE_URL
    openai_oauth_token_url: str = DEFAULT_TOKEN_URL
    openai_oauth_redirect_uri: str = DEFAULT_REDIRECT_URI
    openai_oauth_scope: str = "openid offline_access"

    # OpenRouter (OpenAI-compatible) — optional fallback provider
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # If unset, PlotLot will derive a default from OPENAI_MODEL (e.g. openai/gpt-4.1)
    openrouter_model: str = ""
    # Optional attribution headers (recommended by OpenRouter)
    openrouter_http_referer: str = ""
    openrouter_app_title: str = ""

    # Jina.ai search
    jina_api_key: str = ""

    # Sentry
    sentry_dsn: str = ""

    @model_validator(mode="after")
    def _strip_api_keys(self) -> "Settings":
        """Strip whitespace/newlines from API keys — common paste error in dashboards."""
        for field in (
            "geocodio_api_key",
            "hf_token",
            "nvidia_api_key",
            "nvidia_base_url",
            "nvidia_model",
            "nvidia_fallback_model",
            "anthropic_api_key",
            "google_api_key",
            "openai_api_key",
            "openai_access_token",
            "jina_api_key",
            "stripe_secret_key",
            "stripe_webhook_secret",
            "clerk_jwks_url",
            "openai_base_url",
            "openai_organization",
            "openai_project",
            "openrouter_api_key",
            "openrouter_base_url",
            "openrouter_model",
            "openrouter_http_referer",
            "openrouter_app_title",
            "codex_auth_file",
            "openai_oauth_client_id",
            "openai_oauth_authorize_url",
            "openai_oauth_token_url",
            "openai_oauth_redirect_uri",
            "openai_oauth_scope",
        ):
            val = getattr(self, field)
            if val and val != val.strip():
                setattr(self, field, val.strip())
        return self

    @model_validator(mode="after")
    def _maybe_load_codex_oauth(self) -> "Settings":
        """Load Codex OAuth bearer token into OPENAI_ACCESS_TOKEN when opted in."""
        if self.openai_api_key:
            return self
        if not self.use_codex_oauth:
            return self

        try:
            from pathlib import Path

            from plotlot.oauth.openai_auth import load_tokens

            auth_path = Path(self.codex_auth_file).expanduser()
            tokens = load_tokens(auth_path)
            if not tokens or not tokens.access:
                return self
            self.openai_access_token = tokens.access
        except Exception:
            # Never block startup on local dev credential discovery.
            return self

        return self

    # Google Workspace (Sheets/Docs creation)
    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""

    # MLflow — uses MLFLOW_TRACKING_URI env var in production (Neon PostgreSQL),
    # falls back to local SQLite for development.
    mlflow_tracking_uri: str = "sqlite:///mlruns/mlflow.db"
    mlflow_experiment_name: str = "plotlot-rag"

    # GCP / Firestore
    gcp_project_id: str = ""
    firestore_database: str = "(default)"

    # ArcGIS Hub
    arcgis_hub_api_url: str = "https://hub.arcgis.com/api/v3/datasets"
    hub_discovery_timeout: float = 10.0
    hub_cache_ttl_hours: int = 168  # 7 days

    # Logging
    log_json: bool = True
    log_level: str = "INFO"

    # CORS
    cors_origins: list[str] = [
        "https://mlopprojects.vercel.app",
        "https://plotlot-v2.vercel.app",
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://localhost:3003",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3002",
        "http://127.0.0.1:3003",
        "https://plotlot-api-production.up.railway.app",
    ]

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
