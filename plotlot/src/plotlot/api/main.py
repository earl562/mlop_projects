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

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from plotlot.api.auth import get_current_user
from plotlot.api.chat import router as chat_router
from plotlot.api.geometry import router as geometry_router
from plotlot.api.middleware import rate_limiter
from plotlot.api.portfolio import router as portfolio_router
from plotlot.api.routes import router
from plotlot.config import settings
from plotlot.observability.logging import correlation_id, setup_logging
from plotlot.storage.db import get_session, init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB on startup, cleanup on shutdown."""
    setup_logging(json_format=settings.log_json, level=settings.log_level)

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
    from plotlot.observability.tracing import (
        set_tracking_uri,
        set_experiment,
        enable_async_logging,
        mlflow as _mlflow_mod,
    )

    if _mlflow_mod is not None:
        set_tracking_uri(settings.mlflow_tracking_uri)
        set_experiment(settings.mlflow_experiment_name)
        enable_async_logging()
        logger.info("MLflow tracing enabled: %s", settings.mlflow_tracking_uri)
    else:
        logger.info("MLflow not installed — tracing disabled")

    # Log the database URL (redacted) for debugging deployment issues
    from urllib.parse import urlparse

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
    except Exception as e:
        logger.error("Database initialization failed: %s — API will start in degraded mode", e)
    # Log auth and rate-limiting status
    if settings.auth_enabled:
        logger.info("Supabase auth ENABLED (JWT verification active)")
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
app.include_router(chat_router)
app.include_router(portfolio_router)
app.include_router(geometry_router)


@app.get("/health")
async def health():
    """Health check — verifies DB connectivity, ingestion freshness, MLflow."""
    checks = {}

    session = None
    try:
        from sqlalchemy import text

        session = await get_session()
        await session.execute(text("SELECT 1"))
        checks["database"] = "ok"

        # Ingestion freshness
        try:
            result = await session.execute(text("SELECT MAX(created_at) FROM ordinance_chunks"))
            latest = result.scalar()
            checks["last_ingestion"] = latest.isoformat() if latest else "never"
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
    return {"status": status, "checks": checks}


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
    """Multi-provider LLM connectivity test.

    Tests all three providers in the fallback chain:
    1. Claude Sonnet 4.6 (Anthropic)
    2. Google Gemini 2.5 Flash
    3. NVIDIA NIM (Llama + Kimi)
    """
    import time
    import httpx
    from plotlot.config import settings as _s

    diag: dict = {"providers": {}}

    # --- Provider 1: Claude ---
    if _s.anthropic_api_key:
        t0 = time.monotonic()
        try:
            import anthropic

            client = anthropic.AsyncAnthropic(
                api_key=_s.anthropic_api_key,
                timeout=15.0,
            )
            resp = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=10,
                messages=[{"role": "user", "content": "Say 'ok' in one word."}],
            )
            elapsed = round(time.monotonic() - t0, 2)
            text = resp.content[0].text if resp.content else ""
            diag["providers"]["claude"] = {
                "status": "ok",
                "model": "claude-sonnet-4-6",
                "latency_s": elapsed,
                "response": text[:100],
            }
        except Exception as e:
            elapsed = round(time.monotonic() - t0, 2)
            diag["providers"]["claude"] = {
                "status": "error",
                "model": "claude-sonnet-4-6",
                "error": f"{type(e).__name__}: {e}",
                "elapsed_s": elapsed,
            }
    else:
        diag["providers"]["claude"] = {"status": "no_api_key"}

    # --- Provider 2: Gemini ---
    if _s.google_api_key:
        gemini_url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        gemini_headers = {
            "Authorization": f"Bearer {_s.google_api_key}",
            "Content-Type": "application/json",
        }
        t0 = time.monotonic()
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=15.0, write=10.0, pool=5.0),
        ) as client:
            try:
                resp = await client.post(
                    gemini_url,
                    json={
                        "model": "gemini-2.5-flash",
                        "messages": [{"role": "user", "content": "Say 'ok' in one word."}],
                        "temperature": 0,
                        "max_tokens": 5,
                    },
                    headers=gemini_headers,
                )
                elapsed = round(time.monotonic() - t0, 2)
                diag["providers"]["gemini"] = {
                    "status": resp.status_code,
                    "model": "gemini-2.5-flash",
                    "latency_s": elapsed,
                    "body": resp.text[:300],
                }
            except Exception as e:
                elapsed = round(time.monotonic() - t0, 2)
                diag["providers"]["gemini"] = {
                    "status": "error",
                    "error": f"{type(e).__name__}: {e}",
                    "elapsed_s": elapsed,
                }
    else:
        diag["providers"]["gemini"] = {"status": "no_api_key"}

    # --- Provider 3: NVIDIA NIM ---
    nvidia_models = [
        "meta/llama-3.3-70b-instruct",
        "moonshotai/kimi-k2.5",
    ]

    api_key = _s.nvidia_api_key
    if not api_key:
        diag["providers"]["nvidia"] = {"status": "no_api_key"}
    else:
        diag["providers"]["nvidia"] = {}
        headers = {
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
        }
        url = "https://integrate.api.nvidia.com/v1/chat/completions"

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0),
        ) as client:
            for model in nvidia_models:
                t0 = time.monotonic()
                try:
                    resp = await client.post(
                        url,
                        json={
                            "model": model,
                            "messages": [{"role": "user", "content": "Say 'ok' in one word."}],
                            "temperature": 0,
                            "max_tokens": 5,
                        },
                        headers=headers,
                    )
                    elapsed = round(time.monotonic() - t0, 2)
                    diag["providers"]["nvidia"][model] = {
                        "status": resp.status_code,
                        "latency_s": elapsed,
                        "body": resp.text[:300],
                    }
                except Exception as e:
                    elapsed = round(time.monotonic() - t0, 2)
                    diag["providers"]["nvidia"][model] = {
                        "error": f"{type(e).__name__}: {e}",
                        "elapsed_s": elapsed,
                    }

    # --- Circuit breaker states ---
    from plotlot.retrieval.llm import _breakers

    diag["circuit_breakers"] = {
        name: {"state": cb.state, "failures": cb._failure_count} for name, cb in _breakers.items()
    }

    return diag


def run():
    """Entry point for plotlot-api console script."""
    uvicorn.run("plotlot.api.main:app", host="0.0.0.0", port=8000, reload=True)
