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

    # Initialize MLflow tracing
    from plotlot.observability.tracing import (
        set_tracking_uri, set_experiment, enable_async_logging, mlflow as _mlflow_mod,
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
                traces_out.append({
                    "run_id": run.info.run_id,
                    "run_name": run.info.run_name,
                    "status": run.info.status,
                    "start_time": run.info.start_time,
                    "end_time": run.info.end_time,
                    "params": dict(run.data.params),
                    "metrics": dict(run.data.metrics),
                    "tags": {k: v for k, v in run.data.tags.items() if not k.startswith("mlflow.")},
                })

        return {"experiment_count": len(experiments), "traces": traces_out[:limit]}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


@app.get("/debug/llm")
async def debug_llm():
    """Network diagnostics + multi-model LLM connectivity test.

    Tests DNS resolution, TCP connect, and multiple NVIDIA models to
    pinpoint whether the issue is network-level or model-specific.
    """
    import socket
    import time
    import httpx
    from plotlot.config import settings as _s

    diag: dict = {}

    # --- Step 1: DNS resolution ---
    host = "integrate.api.nvidia.com"
    try:
        t0 = time.monotonic()
        addrs = socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)
        dns_ms = round((time.monotonic() - t0) * 1000, 1)
        resolved_ips = list({a[4][0] for a in addrs})
        diag["dns"] = {"host": host, "ips": resolved_ips, "latency_ms": dns_ms}
    except Exception as e:
        diag["dns"] = {"host": host, "error": f"{type(e).__name__}: {e}"}

    # --- Step 2: TCP connect to resolved IP ---
    if diag["dns"].get("ips"):
        ip = diag["dns"]["ips"][0]
        try:
            t0 = time.monotonic()
            sock = socket.create_connection((ip, 443), timeout=10)
            tcp_ms = round((time.monotonic() - t0) * 1000, 1)
            sock.close()
            diag["tcp"] = {"ip": ip, "port": 443, "latency_ms": tcp_ms}
        except Exception as e:
            diag["tcp"] = {"ip": ip, "port": 443, "error": f"{type(e).__name__}: {e}"}

    # --- Step 3: Test multiple NVIDIA models ---
    test_payload = {
        "messages": [{"role": "user", "content": "Say 'ok' in one word."}],
        "temperature": 0,
        "max_tokens": 5,
    }

    nvidia_models = [
        "moonshotai/kimi-k2.5",
        "meta/llama-3.3-70b-instruct",
        "minimaxai/minimax-m2.1",
    ]

    api_key = _s.nvidia_api_key
    if not api_key:
        diag["nvidia_models"] = {"error": "no_api_key"}
    else:
        key_info = {
            "key_len": len(api_key),
            "key_prefix": api_key[:8] + "...",
            "has_whitespace": api_key != api_key.strip(),
            "has_newline": "\n" in api_key or "\r" in api_key,
        }
        diag["nvidia_key"] = key_info
        diag["nvidia_models"] = {}

        headers = {
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
        }
        url = "https://integrate.api.nvidia.com/v1/chat/completions"

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0),
        ) as client:
            for model in nvidia_models:
                try:
                    t0 = time.monotonic()
                    resp = await client.post(
                        url, json={**test_payload, "model": model}, headers=headers,
                    )
                    elapsed = round(time.monotonic() - t0, 2)
                    diag["nvidia_models"][model] = {
                        "status": resp.status_code,
                        "latency_s": elapsed,
                        "body": resp.text[:300],
                    }
                except Exception as e:
                    elapsed = round(time.monotonic() - t0, 2)
                    diag["nvidia_models"][model] = {
                        "error": f"{type(e).__name__}: {e}",
                        "elapsed_s": elapsed,
                    }

    # --- Step 4: Gemini connectivity (if key exists) ---
    if _s.gemini_api_key:
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0),
            ) as client:
                t0 = time.monotonic()
                resp = await client.post(
                    "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                    json={**test_payload, "model": "gemini-2.5-flash"},
                    headers={
                        "Authorization": f"Bearer {_s.gemini_api_key.strip()}",
                        "Content-Type": "application/json",
                    },
                )
                elapsed = round(time.monotonic() - t0, 2)
                diag["gemini"] = {"status": resp.status_code, "latency_s": elapsed, "body": resp.text[:300]}
        except Exception as e:
            diag["gemini"] = {"error": f"{type(e).__name__}: {e}"}
    else:
        diag["gemini"] = {"error": "no_api_key"}

    return diag


def run():
    """Entry point for plotlot-api console script."""
    uvicorn.run("plotlot.api.main:app", host="0.0.0.0", port=8000, reload=True)
