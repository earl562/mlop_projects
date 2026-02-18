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

from plotlot.api.chat import router as chat_router
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
    # Log the database URL (redacted) for debugging deployment issues
    from urllib.parse import urlparse
    parsed = urlparse(settings.database_url)
    redacted_host = f"{parsed.hostname}:{parsed.port}" if parsed.port else parsed.hostname
    logger.info("Connecting to database at %s/%s", redacted_host, parsed.path.lstrip("/"))
    try:
        await asyncio.wait_for(init_db(), timeout=15)
        logger.info("Database initialized successfully")
    except asyncio.TimeoutError:
        logger.error("Database initialization timed out after 15s — API will start in degraded mode")
    except Exception as e:
        logger.error("Database initialization failed: %s — API will start in degraded mode", e)
    logger.info("PlotLot API ready")
    yield
    logger.info("Shutting down")


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


app = FastAPI(
    title="PlotLot",
    description="AI-powered zoning analysis for South Florida real estate. "
    "Covers 104 municipalities across Miami-Dade, Broward, and Palm Beach counties.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(CorrelationIDMiddleware)
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


@app.get("/debug/llm")
async def debug_llm():
    """Test LLM provider connectivity — returns latency or error per provider."""
    import time
    import httpx
    from plotlot.config import settings as _s

    results = {}
    test_payload = {
        "messages": [{"role": "user", "content": "Say 'ok' in one word."}],
        "temperature": 0,
        "max_tokens": 5,
    }

    providers = [
        ("groq", _s.groq_api_key, "https://api.groq.com/openai/v1/chat/completions",
         "llama-3.3-70b-versatile", {}),
        ("nvidia", _s.nvidia_api_key, "https://integrate.api.nvidia.com/v1/chat/completions",
         "moonshotai/kimi-k2.5", {}),
        ("openrouter", _s.openrouter_api_key, "https://openrouter.ai/api/v1/chat/completions",
         "deepseek/deepseek-v3.2", {"HTTP-Referer": "https://plotlot.dev"}),
    ]

    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=45.0, write=10.0, pool=5.0)) as client:
        for name, api_key, url, model, extra_headers in providers:
            if not api_key:
                results[name] = {"error": "no_api_key"}
                continue
            try:
                headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", **extra_headers}
                t0 = time.monotonic()
                resp = await client.post(url, json={**test_payload, "model": model}, headers=headers)
                elapsed = round(time.monotonic() - t0, 2)
                results[name] = {"status": resp.status_code, "latency_s": elapsed, "body": resp.text[:200]}
            except Exception as e:
                results[name] = {"error": f"{type(e).__name__}: {e}", "key_prefix": api_key[:8] + "..."}

    return results


def run():
    """Entry point for plotlot-api console script."""
    uvicorn.run("plotlot.api.main:app", host="0.0.0.0", port=8000, reload=True)
