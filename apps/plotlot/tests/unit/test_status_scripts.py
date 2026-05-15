"""Regression tests for PlotLot runtime health scripts."""

from __future__ import annotations

import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
HEALTHCHECK_SCRIPT = REPO_ROOT / "scripts/status/healthcheck.sh"
WATCHDOG_SCRIPT = REPO_ROOT / "scripts/status/watchdog.sh"


def _start_server(routes: dict[tuple[str, str], tuple[int, dict | str]]):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self._respond()

        def do_POST(self):
            length = int(self.headers.get("content-length", "0"))
            if length:
                self.rfile.read(length)
            self._respond()

        def _respond(self):
            status, body = routes.get((self.command, self.path), (404, {"detail": "not found"}))
            if isinstance(body, dict):
                payload = json.dumps(body).encode("utf-8")
                content_type = "application/json"
            else:
                payload = str(body).encode("utf-8")
                content_type = "text/plain; charset=utf-8"
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format, *args):  # noqa: A003
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _script_env(tmp_path: Path, *, frontend_url: str, backend_url: str) -> dict[str, str]:
    status_json = tmp_path / "docs/status/runtime-status.json"
    state_md = tmp_path / "docs/status/CURRENT_STATE.md"
    health_log_dir = tmp_path / "logs/health"
    runner_log_dir = tmp_path / "logs/runner"
    return {
        **os.environ,
        "FRONTEND_URL": frontend_url,
        "BACKEND_URL": backend_url,
        "STATUS_JSON": str(status_json),
        "STATE_MD": str(state_md),
        "HEALTH_LOG_DIR": str(health_log_dir),
        "RUNNER_LOG_DIR": str(runner_log_dir),
        "WATCHDOG_LOG_DIR": str(runner_log_dir),
        "PROCESS_LINES_OVERRIDE": (
            "python -m uvicorn plotlot.api.main:app --reload\nnode next dev --port 3002"
        ),
        "ANALYZE_SMOKE_ENABLED": "1",
        "ANALYZE_SMOKE_TIMEOUT": "5",
        "CHAT_SMOKE_ENABLED": "1",
        "CHAT_SMOKE_TIMEOUT": "5",
        "PORTFOLIO_SMOKE_ENABLED": "1",
        "PORTFOLIO_SMOKE_TIMEOUT": "5",
    }


def test_healthcheck_writes_runtime_status_with_successful_smoke_test(tmp_path):
    backend = _start_server(
        {
            (
                "GET",
                "/health",
            ): (
                200,
                {
                    "status": "healthy",
                    "checks": {
                        "database": "ok",
                        "mlflow": "ok",
                        "last_ingestion": "2026-04-10T00:11:08.832126+00:00",
                    },
                    "capabilities": {
                        "db_backed_analysis_ready": True,
                        "portfolio_ready": True,
                        "agent_chat_ready": False,
                    },
                    "database_target": {
                        "host": "localhost",
                        "port": 5433,
                        "database": "plotlot",
                        "ssl_required": False,
                    },
                    "capability_details": {
                        "db_backed_analysis_ready": {
                            "ready": True,
                            "reason": "database_ok",
                            "blocked_by": [],
                            "dependencies": ["database"],
                        },
                        "portfolio_ready": {
                            "ready": True,
                            "reason": "database_ok",
                            "blocked_by": [],
                            "dependencies": ["database"],
                        },
                        "agent_chat_ready": {
                            "ready": False,
                            "reason": "llm_credentials_missing",
                            "blocked_by": ["llm_credentials"],
                            "dependencies": ["llm_credentials"],
                        },
                    },
                    "runtime": {
                        "startup_mode": "healthy",
                        "startup_warnings": [],
                    },
                },
            ),
            (
                "POST",
                "/api/v1/analyze",
            ): (
                200,
                {
                    "address": "171 NE 209th Ter, Miami, FL 33179",
                    "formatted_address": "171 NE 209th Ter, Miami Gardens, FL 33179",
                    "municipality": "Miami Gardens",
                    "confidence": "high",
                },
            ),
            (
                "POST",
                "/api/v1/chat",
            ): (
                200,
                'event: session\ndata: {"session_id":"abc"}\n\nevent: done\ndata: {"full_content":"ok"}\n\n',
            ),
            (
                "GET",
                "/api/v1/portfolio",
            ): (
                200,
                [],
            ),
        }
    )
    frontend = _start_server({("GET", "/"): (200, "ok")})
    try:
        env = _script_env(
            tmp_path,
            frontend_url=f"http://127.0.0.1:{frontend.server_port}",
            backend_url=f"http://127.0.0.1:{backend.server_port}",
        )
        result = subprocess.run(
            ["bash", str(HEALTHCHECK_SCRIPT)],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        backend.shutdown()
        backend.server_close()
        frontend.shutdown()
        frontend.server_close()

    assert result.returncode == 0, result.stderr or result.stdout

    status_path = Path(env["STATUS_JSON"])
    assert status_path.exists()
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["health_ok"] is True
    assert payload["backend_status"] == "healthy"
    assert payload["frontend_status"] == "ok"
    assert payload["database_target"]["host"] == "localhost"
    assert payload["database_target"]["port"] == 5433
    assert payload["database_target"]["database"] == "plotlot"
    assert payload["database"]["host"] == "localhost"
    assert payload["database"]["port"] == 5433
    assert payload["database"]["name"] == "plotlot"
    assert payload["database"]["ssl_required"] is False
    assert payload["capabilities"]["db_backed_analysis_ready"] is True
    assert payload["capabilities"]["portfolio_ready"] is True
    assert payload["capability_details"]["db_backed_analysis_ready"]["reason"] == "database_ok"
    assert payload["capability_details"]["db_backed_analysis_ready"]["blocked_by"] == []
    assert payload["capability_details"]["db_backed_analysis_ready"]["dependencies"] == ["database"]
    assert "Agent chat unavailable: llm_credentials_missing" in payload["open_issues"]
    assert "Portfolio unavailable: database_ok" not in payload["open_issues"]
    assert (
        payload["next_action"]
        == "Set OPENAI_API_KEY or OPENAI_ACCESS_TOKEN to re-enable agent chat"
    )
    assert payload["runtime"]["startup_mode"] == "healthy"
    assert payload["runtime"]["startup_warnings"] == []
    assert payload["analyze_smoke"]["enabled"] is True
    assert payload["analyze_smoke"]["status"] == "ok"
    assert "Miami Gardens" in payload["analyze_smoke"]["summary"]
    assert payload["chat_smoke"]["enabled"] is True
    assert payload["chat_smoke"]["status"] == "ok"
    assert payload["chat_smoke"]["summary"] == "chat_sse_completed"
    assert payload["portfolio_smoke"]["enabled"] is True
    assert payload["portfolio_smoke"]["status"] == "ok"
    assert payload["portfolio_smoke"]["summary"] == "entries=0"

    health_logs = list(Path(env["HEALTH_LOG_DIR"]).glob("healthcheck-*.log"))
    assert len(health_logs) == 1


def test_watchdog_fails_when_analyze_smoke_fails(tmp_path):
    backend = _start_server(
        {
            (
                "GET",
                "/health",
            ): (
                200,
                {
                    "status": "healthy",
                    "checks": {
                        "database": "ok",
                        "mlflow": "ok",
                        "last_ingestion": "2026-04-10T00:11:08.832126+00:00",
                    },
                    "capabilities": {
                        "db_backed_analysis_ready": False,
                        "portfolio_ready": False,
                        "agent_chat_ready": False,
                    },
                    "database_target": {
                        "host": "localhost",
                        "port": 5433,
                        "database": "plotlot",
                        "ssl_required": False,
                    },
                    "capability_details": {
                        "db_backed_analysis_ready": {
                            "ready": False,
                            "reason": "database_unavailable",
                            "blocked_by": ["database"],
                            "dependencies": ["database"],
                        },
                        "portfolio_ready": {
                            "ready": False,
                            "reason": "database_unavailable",
                            "blocked_by": ["database"],
                            "dependencies": ["database"],
                        },
                        "agent_chat_ready": {
                            "ready": False,
                            "reason": "llm_credentials_missing",
                            "blocked_by": ["llm_credentials"],
                            "dependencies": ["llm_credentials"],
                        },
                    },
                    "runtime": {
                        "startup_mode": "degraded",
                        "startup_warnings": ["database_unavailable"],
                    },
                },
            ),
            ("POST", "/api/v1/analyze"): (500, {"detail": "pipeline unavailable"}),
            ("POST", "/api/v1/chat"): (
                200,
                'event: error\ndata: {"detail":"Chat unavailable"}\n\n',
            ),
            ("GET", "/api/v1/portfolio"): (500, {"detail": "portfolio unavailable"}),
        }
    )
    frontend = _start_server({("GET", "/"): (200, "ok")})
    try:
        env = _script_env(
            tmp_path,
            frontend_url=f"http://127.0.0.1:{frontend.server_port}",
            backend_url=f"http://127.0.0.1:{backend.server_port}",
        )
        result = subprocess.run(
            ["bash", str(WATCHDOG_SCRIPT)],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        backend.shutdown()
        backend.server_close()
        frontend.shutdown()
        frontend.server_close()

    assert result.returncode == 1
    assert "WATCHDOG_STATUS=fail" in result.stdout
    assert (
        "WATCHDOG_CAPABILITIES=db_backed_analysis_ready=blocked, portfolio_ready=blocked, agent_chat_ready=blocked"
        in result.stdout
    )
    assert (
        "WATCHDOG_BLOCKERS=db_backed_analysis_ready=database; portfolio_ready=database; agent_chat_ready=llm_credentials"
        in result.stdout
    )
    assert (
        "WATCHDOG_DEPENDENCIES=db_backed_analysis_ready=database; portfolio_ready=database; agent_chat_ready=llm_credentials"
        in result.stdout
    )
    assert "WATCHDOG_SMOKE_SUMMARY=" in result.stdout
    assert 'analyze={"detail": "pipeline unavailable"}' in result.stdout
    assert 'chat=event: error\ndata: {"detail":"Chat unavailable"}' in result.stdout
    assert 'portfolio={"detail": "portfolio unavailable"}' in result.stdout
    assert "analyze_smoke=failed" in result.stdout
    assert "chat_smoke=failed" in result.stdout
    assert "portfolio_smoke=failed" in result.stdout
    assert "db_backed_reason=database_unavailable" in result.stdout
    assert "agent_chat_reason=llm_credentials_missing" in result.stdout
    assert "portfolio_reason=database_unavailable" in result.stdout
    assert "WATCHDOG_RUNTIME_MODE=degraded" in result.stdout
    assert "WATCHDOG_STARTUP_WARNINGS=database_unavailable" in result.stdout
    assert "WATCHDOG_DATABASE_TARGET=localhost:5433/plotlot" in result.stdout
    assert (
        "WATCHDOG_NEXT_ACTION=Investigate /api/v1/analyze failure before continuing product work"
        in result.stdout
    )

    payload = json.loads(Path(env["STATUS_JSON"]).read_text(encoding="utf-8"))
    assert payload["health_ok"] is False
    assert payload["analyze_smoke"]["status"] == "failed"
    assert payload["chat_smoke"]["status"] == "failed"
    assert payload["portfolio_smoke"]["status"] == "failed"
    assert payload["database_target"]["host"] == "localhost"
    assert payload["database"]["host"] == "localhost"
    assert payload["database"]["port"] == 5433
    assert payload["database"]["name"] == "plotlot"
    assert payload["database"]["ssl_required"] is False
    assert payload["capabilities"]["db_backed_analysis_ready"] is False
    assert (
        payload["capability_details"]["db_backed_analysis_ready"]["reason"]
        == "database_unavailable"
    )
    assert payload["capability_details"]["db_backed_analysis_ready"]["blocked_by"] == ["database"]
    assert payload["capability_details"]["db_backed_analysis_ready"]["dependencies"] == ["database"]
    assert "DB-backed analysis unavailable: database_unavailable" in payload["open_issues"]
    assert "Portfolio unavailable: database_unavailable" in payload["open_issues"]
    assert (
        payload["next_action"]
        == "Investigate /api/v1/analyze failure before continuing product work"
    )
    assert payload["runtime"]["startup_mode"] == "degraded"
    assert "database_unavailable" in payload["runtime"]["startup_warnings"]


def test_healthcheck_prioritizes_portfolio_smoke_when_only_portfolio_fails(tmp_path):
    backend = _start_server(
        {
            (
                "GET",
                "/health",
            ): (
                200,
                {
                    "status": "healthy",
                    "checks": {
                        "database": "ok",
                        "mlflow": "ok",
                        "last_ingestion": "2026-04-10T00:11:08.832126+00:00",
                    },
                    "capabilities": {
                        "db_backed_analysis_ready": True,
                        "portfolio_ready": True,
                        "agent_chat_ready": True,
                    },
                    "database_target": {
                        "host": "localhost",
                        "port": 5433,
                        "database": "plotlot",
                        "ssl_required": False,
                    },
                    "capability_details": {
                        "db_backed_analysis_ready": {
                            "ready": True,
                            "reason": "database_ok",
                            "blocked_by": [],
                            "dependencies": ["database"],
                        },
                        "portfolio_ready": {
                            "ready": True,
                            "reason": "database_ok",
                            "blocked_by": [],
                            "dependencies": ["database"],
                        },
                        "agent_chat_ready": {
                            "ready": True,
                            "reason": "llm_credentials_present",
                            "blocked_by": [],
                            "dependencies": ["llm_credentials"],
                        },
                    },
                    "runtime": {
                        "startup_mode": "healthy",
                        "startup_warnings": [],
                    },
                },
            ),
            ("POST", "/api/v1/analyze"): (
                200,
                {
                    "address": "171 NE 209th Ter",
                    "municipality": "Miami Gardens",
                    "confidence": "high",
                },
            ),
            ("POST", "/api/v1/chat"): (
                200,
                'event: session\ndata: {"session_id":"abc"}\n\nevent: done\ndata: {"full_content":"ok"}\n\n',
            ),
            ("GET", "/api/v1/portfolio"): (500, {"detail": "portfolio unavailable"}),
        }
    )
    frontend = _start_server({("GET", "/"): (200, "ok")})
    try:
        env = _script_env(
            tmp_path,
            frontend_url=f"http://127.0.0.1:{frontend.server_port}",
            backend_url=f"http://127.0.0.1:{backend.server_port}",
        )
        result = subprocess.run(
            ["bash", str(HEALTHCHECK_SCRIPT)],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        backend.shutdown()
        backend.server_close()
        frontend.shutdown()
        frontend.server_close()

    assert result.returncode == 1

    payload = json.loads(Path(env["STATUS_JSON"]).read_text(encoding="utf-8"))
    assert payload["analyze_smoke"]["status"] == "ok"
    assert payload["chat_smoke"]["status"] == "ok"
    assert payload["portfolio_smoke"]["status"] == "failed"
    assert (
        payload["next_action"]
        == "Investigate /api/v1/portfolio failure before continuing product work"
    )


def test_healthcheck_prioritizes_chat_smoke_when_only_chat_fails(tmp_path):
    backend = _start_server(
        {
            (
                "GET",
                "/health",
            ): (
                200,
                {
                    "status": "healthy",
                    "checks": {
                        "database": "ok",
                        "mlflow": "ok",
                        "last_ingestion": "2026-04-10T00:11:08.832126+00:00",
                    },
                    "capabilities": {
                        "db_backed_analysis_ready": True,
                        "portfolio_ready": True,
                        "agent_chat_ready": True,
                    },
                    "database_target": {
                        "host": "localhost",
                        "port": 5433,
                        "database": "plotlot",
                        "ssl_required": False,
                    },
                    "capability_details": {
                        "db_backed_analysis_ready": {
                            "ready": True,
                            "reason": "database_ok",
                            "blocked_by": [],
                            "dependencies": ["database"],
                        },
                        "portfolio_ready": {
                            "ready": True,
                            "reason": "database_ok",
                            "blocked_by": [],
                            "dependencies": ["database"],
                        },
                        "agent_chat_ready": {
                            "ready": True,
                            "reason": "llm_credentials_present",
                            "blocked_by": [],
                            "dependencies": ["llm_credentials"],
                        },
                    },
                    "runtime": {
                        "startup_mode": "healthy",
                        "startup_warnings": [],
                    },
                },
            ),
            ("POST", "/api/v1/analyze"): (
                200,
                {
                    "address": "171 NE 209th Ter",
                    "municipality": "Miami Gardens",
                    "confidence": "high",
                },
            ),
            ("POST", "/api/v1/chat"): (
                200,
                'event: error\ndata: {"detail":"Chat unavailable"}\n\n',
            ),
            ("GET", "/api/v1/portfolio"): (200, []),
        }
    )
    frontend = _start_server({("GET", "/"): (200, "ok")})
    try:
        env = _script_env(
            tmp_path,
            frontend_url=f"http://127.0.0.1:{frontend.server_port}",
            backend_url=f"http://127.0.0.1:{backend.server_port}",
        )
        result = subprocess.run(
            ["bash", str(HEALTHCHECK_SCRIPT)],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        backend.shutdown()
        backend.server_close()
        frontend.shutdown()
        frontend.server_close()

    assert result.returncode == 1

    payload = json.loads(Path(env["STATUS_JSON"]).read_text(encoding="utf-8"))
    assert payload["analyze_smoke"]["status"] == "ok"
    assert payload["chat_smoke"]["status"] == "failed"
    assert payload["portfolio_smoke"]["status"] == "ok"
    assert (
        payload["next_action"] == "Investigate /api/v1/chat failure before continuing product work"
    )
