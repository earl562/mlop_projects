"""PlotLot API — FastAPI application for zoning analysis.

Run:
    uvicorn plotlot.api.main:app --reload
    # or
    plotlot-api
"""

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TypedDict
from urllib.parse import urlparse

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from plotlot.api.security_middleware import TenantAuthorizationMiddleware
from plotlot.api.billing import router as billing_router  # noqa: F401 — registered below
from plotlot.api.chat import router as chat_router
from plotlot.api.connectors.email import router as email_connector_router
from plotlot.api.approvals import router as approvals_router
from plotlot.api.workspaces import router as workspaces_router
from plotlot.api.analyses import router as analyses_router
from plotlot.api.tools import router as tools_router
from plotlot.api.evidence import router as evidence_router
from plotlot.api.mcp import router as mcp_router
from plotlot.api.geometry import router as geometry_router
from plotlot.api.harness_jobs import (
    admin_router as harness_jobs_admin_router,
    router as harness_jobs_router,
)
from plotlot.api.middleware import rate_limiter
from plotlot.api.ordinance import router as ordinance_router
from plotlot.api.portfolio import router as portfolio_router
from plotlot.api.render import router as render_router
from plotlot.api.releases import router as releases_router
from plotlot.api.routes import router
from plotlot.api.screening import router as screening_router
from plotlot.config import settings
from plotlot.observability.logging import correlation_id, setup_logging
from plotlot.observability.tracing import configure_mlflow
from plotlot.oauth.openai_auth import has_saved_tokens
from plotlot.protocol.openapi import install_engine_protocol
from plotlot.retrieval.geocode import geocode_address
from plotlot.storage.db import get_session, init_db

logger = logging.getLogger(__name__)


class _RuntimeHealth(TypedDict):
    startup_mode: str
    startup_warnings: list[str]


_runtime_health: _RuntimeHealth = {
    "startup_mode": "starting",
    "startup_warnings": [],
}


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
app.add_middleware(TenantAuthorizationMiddleware)
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
app.include_router(billing_router)
app.include_router(chat_router)
app.include_router(email_connector_router)
app.include_router(approvals_router)
app.include_router(workspaces_router)
app.include_router(analyses_router)
app.include_router(tools_router)
app.include_router(evidence_router)
app.include_router(mcp_router)
app.include_router(portfolio_router)
app.include_router(geometry_router)
app.include_router(harness_jobs_router)
app.include_router(harness_jobs_admin_router)
app.include_router(ordinance_router)
app.include_router(render_router)
app.include_router(screening_router)
app.include_router(releases_router)
install_engine_protocol(app)

# Clause builder document generation (LOI, PSA, Deal Summary, Pro Forma)
from plotlot.api.documents import router as documents_router  # noqa: E402

app.include_router(documents_router)


# ---------------------------------------------------------------------------
# Address autocomplete (Geocodio-backed, replaces Google Places dependency)
# ---------------------------------------------------------------------------


@app.get("/api/v1/autocomplete")
async def autocomplete(q: str = ""):
    """Return address suggestions using Geocodio, then Census-backed geocoding fallback."""
    if len(q) < 3:
        return {"suggestions": []}

    import httpx

    suggestions = []

    if settings.geocodio_api_key:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(
                    "https://api.geocod.io/v1.7/geocode",
                    params={"q": q, "api_key": settings.geocodio_api_key, "limit": 5},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            data = {}

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

    if suggestions:
        return {"suggestions": suggestions}

    fallback = await geocode_address(q)
    if not fallback or not fallback.get("formatted_address"):
        return {"suggestions": []}

    formatted = str(fallback["formatted_address"])
    street, _, remainder = formatted.partition(",")
    remainder_parts = [part.strip() for part in remainder.split(",") if part.strip()]
    city = fallback.get("municipality", "")
    state = ""
    zip_code = ""
    if remainder_parts:
        city = city or remainder_parts[0]
    if len(remainder_parts) > 1:
        state_zip_parts = " ".join(remainder_parts[1:]).split()
        if state_zip_parts:
            state = state_zip_parts[0]
        if len(state_zip_parts) > 1:
            zip_code = state_zip_parts[1]

    suggestions.append(
        {
            "address": formatted,
            "street": street.strip() or formatted,
            "city": city,
            "state": state,
            "zip": zip_code,
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

    def _has_text_setting(name: str) -> bool:
        """Return true only for explicitly configured string settings.

        Several health tests patch ``settings`` with ``MagicMock``.  Accessing
        an unset attribute on that mock creates a truthy mock object, so the
        health endpoint must not rely on raw truthiness for optional credential
        fields.
        """

        value = getattr(settings, name, "")
        return isinstance(value, str) and bool(value.strip())

    agent_chat_ready = bool(
        _has_text_setting("openai_access_token")
        or _has_text_setting("openai_api_key")
        or _has_text_setting("nvidia_api_key")
        or _has_text_setting("groq_api_key")
        # Legacy compatibility for tests/deployments that still use the old
        # OpenRouter setting name while the runtime uses Groq as the fallback.
        or _has_text_setting("openrouter_api_key")
        or (
            bool(getattr(settings, "use_codex_oauth", False))
            and has_saved_tokens(Path(settings.codex_auth_file).expanduser())
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
    if not settings.debug_mode:
        raise HTTPException(status_code=404, detail="Not found")
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
    """LLM connectivity test for the primary provider + Groq fallback."""
    if not settings.debug_mode:
        raise HTTPException(status_code=404, detail="Not found")
    import time
    from openai import AsyncOpenAI

    diag: dict = {"providers": {}}

    using_nvidia = bool(settings.nvidia_api_key)
    token = (
        settings.nvidia_api_key
        if using_nvidia
        else (settings.openai_access_token or settings.openai_api_key)
    )
    if token:
        t0 = time.monotonic()
        try:
            client_kwargs = {"api_key": token, "timeout": 15.0}
            base_url = settings.nvidia_base_url if using_nvidia else settings.openai_base_url
            if base_url:
                client_kwargs["base_url"] = base_url
            if settings.openai_organization and not using_nvidia:
                client_kwargs["organization"] = settings.openai_organization
            if settings.openai_project and not using_nvidia:
                client_kwargs["project"] = settings.openai_project
            client = AsyncOpenAI(**client_kwargs)
            kwargs = {
                "model": settings.nvidia_model
                if using_nvidia
                else (settings.openai_model or "gpt-4.1"),
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
            if not using_nvidia:
                kwargs["reasoning_effort"] = settings.openai_reasoning_effort
            resp = await client.chat.completions.create(**kwargs)
            elapsed = round(time.monotonic() - t0, 2)
            text = resp.choices[0].message.content or ""
            diag["providers"]["nvidia" if using_nvidia else "openai"] = {
                "status": "ok",
                "model": settings.nvidia_model
                if using_nvidia
                else (settings.openai_model or "gpt-4.1"),
                "base_url": base_url,
                "latency_s": elapsed,
                "response": text[:100],
            }
        except Exception as e:
            elapsed = round(time.monotonic() - t0, 2)
            diag["providers"]["nvidia" if using_nvidia else "openai"] = {
                "status": "error",
                "model": settings.nvidia_model
                if using_nvidia
                else (settings.openai_model or "gpt-4.1"),
                "error": f"{type(e).__name__}: {e}",
                "elapsed_s": elapsed,
            }
    else:
        diag["providers"]["nvidia" if using_nvidia else "openai"] = {"status": "no_credentials"}

    # --- Groq (fallback) ---
    if settings.groq_api_key:
        t0 = time.monotonic()
        try:
            model = settings.groq_model or "meta-llama/llama-4-scout-17b-16e-instruct"

            client = AsyncOpenAI(
                api_key=settings.groq_api_key,
                base_url=settings.groq_base_url,
                timeout=15.0,
            )
            resp = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Say 'ok' in one word."}],
                max_completion_tokens=8,
                temperature=0,
            )
            elapsed = round(time.monotonic() - t0, 2)
            text = resp.choices[0].message.content or ""
            diag["providers"]["groq"] = {
                "status": "ok",
                "model": model,
                "base_url": settings.groq_base_url,
                "latency_s": elapsed,
                "response": text[:100],
            }
        except Exception as e:
            elapsed = round(time.monotonic() - t0, 2)
            diag["providers"]["groq"] = {
                "status": "error",
                "model": settings.groq_model or "meta-llama/llama-4-scout-17b-16e-instruct",
                "error": f"{type(e).__name__}: {e}",
                "elapsed_s": elapsed,
            }
    else:
        diag["providers"]["groq"] = {"status": "no_credentials"}

    # --- Circuit breaker states ---
    from plotlot.retrieval.llm import _breakers

    diag["circuit_breakers"] = {
        name: {"state": cb.state, "failures": cb._failure_count} for name, cb in _breakers.items()
    }

    return diag


def run():
    """Entry point for plotlot-api console script.

    Environment overrides (useful for local port conflicts + deployments):
    - PLOTLOT_API_HOST (fallback HOST, default 0.0.0.0)
    - PLOTLOT_API_PORT (fallback PORT, default 8000)
    - PLOTLOT_API_RELOAD (default 1)
    """

    host = os.environ.get("PLOTLOT_API_HOST") or os.environ.get("HOST") or "0.0.0.0"
    port_raw = os.environ.get("PLOTLOT_API_PORT") or os.environ.get("PORT") or "8000"
    try:
        port = int(port_raw)
    except ValueError as e:
        raise ValueError(f"Invalid API port: {port_raw!r}") from e

    reload_raw = os.environ.get("PLOTLOT_API_RELOAD", "1")
    reload = reload_raw not in {"0", "false", "False", "no", "NO"}
    uvicorn.run("plotlot.api.main:app", host=host, port=port, reload=reload)
