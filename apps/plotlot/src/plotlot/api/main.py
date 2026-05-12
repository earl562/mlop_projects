"""PlotLot API — FastAPI application for zoning analysis.

Run:
    uvicorn plotlot.api.main:app --reload
    # or
    plotlot-api
"""

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, TypedDict
from urllib.parse import urlparse

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from plotlot.api.auth import get_current_user
from plotlot.api.artifacts import router as artifacts_router
from plotlot.api.billing import router as billing_router  # noqa: F401 — registered below
from plotlot.api.chat import router as chat_router
from plotlot.api.geometry import router as geometry_router
from plotlot.api.harness import router as harness_router
from plotlot.api.mcp import router as mcp_router
from plotlot.api.middleware import rate_limiter
from plotlot.api.ordinances import router as ordinances_router
from plotlot.api.portfolio import router as portfolio_router
from plotlot.api.render import router as render_router
from plotlot.api.routes import router
from plotlot.api.workspaces import router as workspaces_router
from plotlot.config import settings
from plotlot.observability.logging import correlation_id, setup_logging
from plotlot.observability.tracing import configure_mlflow
from plotlot.oauth.openai_auth import has_saved_tokens
from plotlot.storage.db import get_session, init_db

logger = logging.getLogger(__name__)


class _RuntimeHealth(TypedDict):
    startup_mode: str
    startup_warnings: list[str]


_runtime_health: _RuntimeHealth = {
    "startup_mode": "starting",
    "startup_warnings": [],
}


def _configured_string(value: object) -> bool:
    """Return true only for explicit non-empty string settings."""

    return isinstance(value, str) and bool(value.strip())


def _settings_string(config: object, name: str, default: str = "") -> str:
    value = getattr(config, name, default)
    return value if isinstance(value, str) else default


def _settings_bool(config: object, name: str, default: bool = False) -> bool:
    value = getattr(config, name, default)
    return value if isinstance(value, bool) else default


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB on startup, cleanup on shutdown."""
    setup_logging(json_format=settings.log_json, level=settings.log_level)
    _runtime_health["startup_mode"] = "healthy"
    _runtime_health["startup_warnings"] = []

    # Initialize Sentry error tracking
    if settings.sentry_dsn:
        try:
            import sentry_sdk

            sentry_sdk.init(
                dsn=settings.sentry_dsn,
                traces_sample_rate=0.1,
                environment="production",
            )
            logger.info("Sentry error tracking enabled")
        except Exception as e:
            logger.warning("Sentry init failed: %s", e)

    # Initialize MLflow tracing
    if configure_mlflow(settings.mlflow_tracking_uri, settings.mlflow_experiment_name):
        logger.info("MLflow tracing enabled: %s", settings.mlflow_tracking_uri)
    else:
        logger.warning("MLflow tracing unavailable — API will start in degraded mode")
        _runtime_health["startup_mode"] = "degraded"
        _runtime_health["startup_warnings"].append("mlflow_unavailable")

    # Log the database URL (redacted) for debugging deployment issues
    parsed = urlparse(settings.database_url)
    redacted_host = f"{parsed.hostname}:{parsed.port}" if parsed.port else parsed.hostname
    logger.info("Connecting to database at %s/%s", redacted_host, parsed.path.lstrip("/"))
    try:
        await asyncio.wait_for(init_db(), timeout=15)
        logger.info("Database initialized successfully")
    except asyncio.TimeoutError:
        logger.error(
            "Database initialization timed out after 15s — API will start in degraded mode"
        )
        _runtime_health["startup_mode"] = "degraded"
        _runtime_health["startup_warnings"].append("database_init_timeout")
    except Exception as e:
        logger.error("Database initialization failed: %s — API will start in degraded mode", e)
        _runtime_health["startup_mode"] = "degraded"
        _runtime_health["startup_warnings"].append("database_unavailable")
    # Log auth and rate-limiting status
    if settings.auth_enabled:
        logger.info("Clerk auth ENABLED (JWKS RS256 verification active)")
    else:
        logger.info("Auth DISABLED — anonymous access allowed (set AUTH_ENABLED=true to enable)")
    logger.info(
        "Rate limiting: %d requests per %ds window on /api/v1/analyze and /api/v1/chat",
        settings.rate_limit_max_requests,
        settings.rate_limit_window_seconds,
    )

    logger.info("PlotLot API ready")
    yield
    logger.info("Shutting down")


class APIVersionMiddleware(BaseHTTPMiddleware):
    """Add API version header to all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["x-api-version"] = "1.0"
        return response


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Set correlation ID from X-Request-ID header or generate a new one."""

    async def dispatch(self, request: Request, call_next):
        cid = request.headers.get("x-request-id", str(uuid.uuid4()))
        token = correlation_id.set(cid)
        try:
            response = await call_next(request)
            response.headers["x-request-id"] = cid
            return response
        finally:
            correlation_id.reset(token)


class AuthMiddleware(BaseHTTPMiddleware):
    """Resolve the current user (if any) and attach to request.state.

    Runs on every request so downstream dependencies and the rate limiter
    can distinguish authenticated from anonymous users.  When auth is
    disabled this is essentially a no-op (sets user=None).
    """

    async def dispatch(self, request: Request, call_next):
        request.state.user = await get_current_user(request)
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Apply rate limiting to expensive API endpoints.

    Only enforced on /api/v1/analyze and /api/v1/chat — the two paths
    that trigger LLM calls and could drive up costs if abused.
    """

    _rate_limited_prefixes = ("/api/v1/analyze", "/api/v1/chat")

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith(self._rate_limited_prefixes):
            await rate_limiter.check(request)
        return await call_next(request)


app = FastAPI(
    title="PlotLot",
    description="AI-powered zoning analysis for South Florida real estate. "
    "Covers 104 municipalities across Miami-Dade, Broward, and Palm Beach counties.",
    version="2.0.0",
    lifespan=lifespan,
)

# Middleware stack (outermost → innermost):
# 1. CORS — must be outermost to handle preflight requests
# 2. API Version — stamp every response with X-API-Version header
# 3. Correlation ID — tag every request for tracing
# 4. Auth — resolve user from JWT (attaches to request.state.user)
# 5. Rate limit — enforce per-IP/per-user limits on expensive endpoints
app.add_middleware(RateLimitMiddleware)
app.add_middleware(AuthMiddleware)
app.add_middleware(CorrelationIDMiddleware)
app.add_middleware(APIVersionMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(artifacts_router)
app.include_router(billing_router)
app.include_router(chat_router)
app.include_router(portfolio_router)
app.include_router(geometry_router)
app.include_router(render_router)
app.include_router(harness_router)
app.include_router(workspaces_router)
app.include_router(ordinances_router)
app.include_router(mcp_router)

# Clause builder document generation (LOI, PSA, Deal Summary, Pro Forma)
from plotlot.api.documents import router as documents_router  # noqa: E402

app.include_router(documents_router)


# ---------------------------------------------------------------------------
# Address autocomplete (Geocodio-backed)
# ---------------------------------------------------------------------------


@app.get("/api/v1/autocomplete")
async def autocomplete(q: str = ""):
    """Return address suggestions using Geocodio forward geocoding."""
    if len(q) < 3 or not settings.geocodio_api_key:
        return {"suggestions": []}

    import httpx

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(
                "https://api.geocod.io/v1.7/geocode",
                params={"q": q, "api_key": settings.geocodio_api_key, "limit": 5},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return {"suggestions": []}

    suggestions = []
    for result in data.get("results", []):
        formatted = result.get("formatted_address", "")
        components = result.get("address_components", {})
        if formatted:
            suggestions.append(
                {
                    "address": formatted,
                    "street": f"{components.get('number', '')} {components.get('formatted_street', '')}".strip(),
                    "city": components.get("city", ""),
                    "state": components.get("state", ""),
                    "zip": components.get("zip", ""),
                }
            )
    return {"suggestions": suggestions}


@app.get("/health")
async def health():
    """Health check — verifies DB connectivity, ingestion freshness, MLflow."""
    checks = {}
    parsed_db = urlparse(settings.database_url)

    session = None
    try:
        from sqlalchemy import text

        session = await get_session()
        await session.execute(text("SELECT 1"))
        checks["database"] = "ok"

        # Ingestion freshness
        try:
            from datetime import datetime

            result = await session.execute(text("SELECT MAX(created_at) FROM ordinance_chunks"))
            latest = result.scalar()
            if asyncio.iscoroutine(latest):
                latest = await latest

            if latest is None:
                checks["last_ingestion"] = "never"
            elif isinstance(latest, datetime):
                checks["last_ingestion"] = latest.isoformat()
            elif isinstance(latest, str):
                checks["last_ingestion"] = latest
            else:
                checks["last_ingestion"] = "unknown"
        except Exception:
            checks["last_ingestion"] = "unknown"
    except Exception as e:
        checks["database"] = f"error: {e}"
        checks["last_ingestion"] = "unknown"
    finally:
        if session:
            await session.close()

    # MLflow connectivity
    from plotlot.observability.tracing import mlflow as _mlflow

    if _mlflow is not None:
        try:
            _mlflow.search_experiments(max_results=1)
            checks["mlflow"] = "ok"
        except Exception as e:
            checks["mlflow"] = f"error: {e}"
    else:
        checks["mlflow"] = "not_installed"

    status = "healthy" if checks.get("database") == "ok" else "degraded"
    database_ready = checks.get("database") == "ok"
    agent_chat_ready = (
        any(
            _configured_string(value)
            for value in (
                _settings_string(settings, "groq_api_key"),
                _settings_string(settings, "nvidia_api_key"),
                _settings_string(settings, "openai_access_token"),
                _settings_string(settings, "openai_api_key"),
                _settings_string(settings, "openrouter_api_key"),
            )
        )
        or (
            _settings_bool(settings, "use_codex_oauth")
            and has_saved_tokens(
                Path(
                    _settings_string(settings, "codex_auth_file", "~/.codex/auth.json")
                ).expanduser()
            )
        )
    )
    capability_details = {
        "db_backed_analysis_ready": {
            "ready": database_ready,
            "reason": "database_ok" if database_ready else "database_unavailable",
            "blocked_by": [] if database_ready else ["database"],
            "dependencies": ["database"],
        },
        "portfolio_ready": {
            "ready": database_ready,
            "reason": "database_ok" if database_ready else "database_unavailable",
            "blocked_by": [] if database_ready else ["database"],
            "dependencies": ["database"],
        },
        "agent_chat_ready": {
            "ready": agent_chat_ready,
            "reason": "llm_credentials_present" if agent_chat_ready else "llm_credentials_missing",
            "blocked_by": [] if agent_chat_ready else ["llm_credentials"],
            "dependencies": ["llm_credentials"],
        },
    }
    return {
        "status": status,
        "checks": checks,
        "database_target": {
            "host": parsed_db.hostname or "unknown",
            "port": parsed_db.port,
            "database": parsed_db.path.lstrip("/") or "unknown",
            "ssl_required": settings.database_require_ssl,
        },
        "capabilities": {
            "db_backed_analysis_ready": database_ready,
            "portfolio_ready": database_ready,
            "agent_chat_ready": agent_chat_ready,
        },
        "capability_details": capability_details,
        "runtime": {
            "startup_mode": _runtime_health["startup_mode"],
            "startup_warnings": list(_runtime_health["startup_warnings"]),
        },
    }


@app.get("/debug/traces")
async def debug_traces(limit: int = 10):
    """View recent MLflow traces — pipeline runs, LLM calls, tool use."""
    from plotlot.observability.tracing import mlflow as _mlflow

    if _mlflow is None:
        return {"error": "MLflow not installed"}

    try:
        client = _mlflow.MlflowClient()
        experiments = client.search_experiments(max_results=5)
        traces_out = []

        for exp in experiments:
            runs = client.search_runs(
                experiment_ids=[exp.experiment_id],
                max_results=limit,
                order_by=["start_time DESC"],
            )
            for run in runs:
                traces_out.append(
                    {
                        "run_id": run.info.run_id,
                        "run_name": run.info.run_name,
                        "status": run.info.status,
                        "start_time": run.info.start_time,
                        "end_time": run.info.end_time,
                        "params": dict(run.data.params),
                        "metrics": dict(run.data.metrics),
                        "tags": {
                            k: v for k, v in run.data.tags.items() if not k.startswith("mlflow.")
                        },
                    }
                )

        return {"experiment_count": len(experiments), "traces": traces_out[:limit]}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


@app.get("/debug/llm")
async def debug_llm():
    """LLM connectivity test for Groq/NVIDIA/OpenAI primary + OpenRouter fallback."""
    import time
    from openai import AsyncOpenAI
    from plotlot.config import settings as _s

    diag: dict = {"providers": {}}

    groq_api_key = _settings_string(_s, "groq_api_key")
    nvidia_api_key = _settings_string(_s, "nvidia_api_key")
    openai_api_key = _settings_string(_s, "openai_api_key")
    openai_access_token = _settings_string(_s, "openai_access_token")
    openrouter_api_key = _settings_string(_s, "openrouter_api_key")

    using_groq = _configured_string(groq_api_key)
    using_nvidia = _configured_string(nvidia_api_key) and not using_groq
    provider_key = "groq" if using_groq else ("nvidia" if using_nvidia else "openai")
    token = (
        groq_api_key
        if using_groq
        else (nvidia_api_key if using_nvidia else openai_access_token or openai_api_key)
    )
    if not token and not (using_groq or using_nvidia) and _settings_bool(_s, "use_codex_oauth"):
        from plotlot.oauth.openai_auth import get_valid_access_token, load_tokens

        auth_file = Path(
            _settings_string(_s, "codex_auth_file", "~/.codex/auth.json")
        ).expanduser()
        client_id = _settings_string(_s, "openai_oauth_client_id")
        if client_id:
            token = await get_valid_access_token(
                client_id=client_id,
                auth_file=auth_file,
                token_url=_settings_string(_s, "openai_oauth_token_url"),
            )
        else:
            saved_tokens = load_tokens(auth_file)
            token = saved_tokens.access if saved_tokens else ""
    if token:
        t0 = time.monotonic()
        try:
            client_kwargs: dict[str, Any] = {"api_key": token, "timeout": 15.0}
            base_url = (
                _settings_string(_s, "groq_base_url", "https://api.groq.com/openai/v1")
                if using_groq
                else (
                    _settings_string(_s, "nvidia_base_url")
                    if using_nvidia
                    else _settings_string(_s, "openai_base_url")
                )
            )
            if base_url:
                client_kwargs["base_url"] = base_url
            if not (using_groq or using_nvidia):
                openai_organization = _settings_string(_s, "openai_organization")
                openai_project = _settings_string(_s, "openai_project")
                if openai_organization:
                    client_kwargs["organization"] = openai_organization
                if openai_project:
                    client_kwargs["project"] = openai_project
            client = AsyncOpenAI(**client_kwargs)
            model = (
                _settings_string(_s, "groq_model", "llama-3.3-70b-versatile")
                if using_groq
                else (
                    _settings_string(_s, "nvidia_model")
                    if using_nvidia
                    else (_settings_string(_s, "openai_model") or "gpt-4.1")
                )
            )
            kwargs = {
                "model": model,
                "messages": (
                    [
                        {"role": "system", "content": "/no_think"},
                        {"role": "user", "content": "Say 'ok' in one word."},
                    ]
                    if using_nvidia
                    else [{"role": "user", "content": "Say 'ok' in one word."}]
                ),
                "max_completion_tokens": 8,
                "temperature": 0,
            }
            if not (using_groq or using_nvidia):
                kwargs["reasoning_effort"] = _settings_string(
                    _s,
                    "openai_reasoning_effort",
                    "medium",
                )
            resp = await client.chat.completions.create(**kwargs)
            elapsed = round(time.monotonic() - t0, 2)
            text = resp.choices[0].message.content or ""
            diag["providers"][provider_key] = {
                "status": "ok",
                "model": model,
                "base_url": base_url,
                "latency_s": elapsed,
                "response": text[:100],
            }
        except Exception as e:
            elapsed = round(time.monotonic() - t0, 2)
            diag["providers"][provider_key] = {
                "status": "error",
                "model": (
                    _settings_string(_s, "groq_model", "llama-3.3-70b-versatile")
                    if using_groq
                    else (
                        _settings_string(_s, "nvidia_model")
                        if using_nvidia
                        else (_settings_string(_s, "openai_model") or "gpt-4.1")
                    )
                ),
                "error": f"{type(e).__name__}: {e}",
                "elapsed_s": elapsed,
            }
    else:
        diag["providers"][provider_key] = {"status": "no_credentials"}

    # --- OpenRouter (fallback) ---
    if openrouter_api_key:
        t0 = time.monotonic()
        try:
            headers: dict[str, str] = {}
            openrouter_http_referer = _settings_string(_s, "openrouter_http_referer")
            openrouter_app_title = _settings_string(_s, "openrouter_app_title")
            if openrouter_http_referer:
                headers["HTTP-Referer"] = openrouter_http_referer
            if openrouter_app_title:
                headers["X-OpenRouter-Title"] = openrouter_app_title

            # If OPENROUTER_MODEL isn't set, derive from OPENAI_MODEL.
            openrouter_model = _settings_string(_s, "openrouter_model")
            openai_model = _settings_string(_s, "openai_model")
            if openrouter_model:
                model = openrouter_model
            elif openai_model and "/" not in openai_model:
                model = f"openai/{openai_model}"
            else:
                model = openai_model or "openai/gpt-4.1"

            client = AsyncOpenAI(
                api_key=openrouter_api_key,
                base_url=_settings_string(
                    _s,
                    "openrouter_base_url",
                    "https://openrouter.ai/api/v1",
                ),
                timeout=15.0,
                default_headers=headers or None,
            )
            resp = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Say 'ok' in one word."}],
                max_completion_tokens=8,
                temperature=0,
            )
            elapsed = round(time.monotonic() - t0, 2)
            text = resp.choices[0].message.content or ""
            diag["providers"]["openrouter"] = {
                "status": "ok",
                "model": model,
                "base_url": _settings_string(
                    _s,
                    "openrouter_base_url",
                    "https://openrouter.ai/api/v1",
                ),
                "latency_s": elapsed,
                "response": text[:100],
            }
        except Exception as e:
            elapsed = round(time.monotonic() - t0, 2)
            diag["providers"]["openrouter"] = {
                "status": "error",
                "model": _settings_string(_s, "openrouter_model") or "(derived)",
                "error": f"{type(e).__name__}: {e}",
                "elapsed_s": elapsed,
            }
    else:
        diag["providers"]["openrouter"] = {"status": "no_credentials"}

    # --- Circuit breaker states ---
    from plotlot.retrieval.llm import _breakers

    diag["circuit_breakers"] = {
        name: {"state": cb.state, "failures": cb._failure_count} for name, cb in _breakers.items()
    }

    return diag


def run():
    """Entry point for plotlot-api console script."""
    uvicorn.run("plotlot.api.main:app", host="0.0.0.0", port=8000, reload=True)
