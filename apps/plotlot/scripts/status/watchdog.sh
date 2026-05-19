#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

TIMESTAMP="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
WATCHDOG_LOG_DIR="${WATCHDOG_LOG_DIR:-$ROOT_DIR/logs/runner}"
mkdir -p "$WATCHDOG_LOG_DIR"
WATCHDOG_LOG="$WATCHDOG_LOG_DIR/watchdog-$(date -u +"%Y%m%dT%H%M%SZ").log"

healthcheck_exit=0
if bash "$ROOT_DIR/scripts/status/healthcheck.sh" | tee "$WATCHDOG_LOG"; then
  healthcheck_exit=0
else
  healthcheck_exit=$?
fi

STATUS_JSON="${STATUS_JSON:-$ROOT_DIR/docs/status/runtime-status.json}"
python3 - <<'PY' "$STATUS_JSON" "$healthcheck_exit"
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    data = json.load(f)
healthcheck_exit = int(sys.argv[2])
backend = data.get("backend_status")
frontend = data.get("frontend_status")
db = (data.get("database") or {}).get("status")
backend_seen = (data.get("processes") or {}).get("backend_seen")
frontend_seen = (data.get("processes") or {}).get("frontend_seen")
analyze = data.get("analyze_smoke") or {}
chat = data.get("chat_smoke") or {}
portfolio = data.get("portfolio_smoke") or {}
capability_details = data.get("capability_details") or {}
problems = []
if backend != "healthy":
    problems.append(f"backend_status={backend}")
if frontend != "ok":
    problems.append(f"frontend_status={frontend}")
if db != "ok":
    problems.append(f"db_status={db}")
if not backend_seen:
    problems.append("backend process missing")
if not frontend_seen:
    problems.append("frontend process missing")
if analyze.get("enabled") and analyze.get("status") != "ok":
    problems.append(f"analyze_smoke={analyze.get('status')}")
if chat.get("enabled") and chat.get("status") != "ok":
    problems.append(f"chat_smoke={chat.get('status')}")
if portfolio.get("enabled") and portfolio.get("status") != "ok":
    problems.append(f"portfolio_smoke={portfolio.get('status')}")
db_backed = capability_details.get("db_backed_analysis_ready") or {}
if not db_backed.get("ready", False):
    problems.append(f"db_backed_reason={db_backed.get('reason', 'unknown')}")
agent_chat = capability_details.get("agent_chat_ready") or {}
if not agent_chat.get("ready", False):
    problems.append(f"agent_chat_reason={agent_chat.get('reason', 'unknown')}")
portfolio_ready = capability_details.get("portfolio_ready") or {}
if not portfolio_ready.get("ready", False):
    problems.append(f"portfolio_reason={portfolio_ready.get('reason', 'unknown')}")
if healthcheck_exit != 0:
    problems.append(f"healthcheck_exit={healthcheck_exit}")
if problems:
    print("WATCHDOG_STATUS=fail")
    capabilities = data.get("capabilities") or {}
    if capabilities:
        print(
            "WATCHDOG_CAPABILITIES="
            + ", ".join(
                f"{name}={'ready' if ready else 'blocked'}"
                for name, ready in capabilities.items()
            )
        )
    if capability_details:
        print(
            "WATCHDOG_BLOCKERS="
            + "; ".join(
                f"{name}={','.join(details.get('blocked_by', [])) or 'none'}"
                for name, details in capability_details.items()
            )
        )
        print(
            "WATCHDOG_DEPENDENCIES="
            + "; ".join(
                f"{name}={','.join(details.get('dependencies', [])) or 'none'}"
                for name, details in capability_details.items()
            )
        )
    print("WATCHDOG_PROBLEMS=" + "; ".join(problems))
    smoke_summaries = []
    if analyze.get("enabled"):
        smoke_summaries.append(
            f"analyze={analyze.get('summary') or analyze.get('error') or analyze.get('status')}"
        )
    if chat.get("enabled"):
        smoke_summaries.append(
            f"chat={chat.get('summary') or chat.get('error') or chat.get('status')}"
        )
    if portfolio.get("enabled"):
        smoke_summaries.append(
            f"portfolio={portfolio.get('summary') or portfolio.get('error') or portfolio.get('status')}"
        )
    if smoke_summaries:
        print("WATCHDOG_SMOKE_SUMMARY=" + " | ".join(smoke_summaries))
    runtime = data.get("runtime") or {}
    startup_mode = runtime.get("startup_mode")
    if startup_mode:
        print("WATCHDOG_RUNTIME_MODE=" + str(startup_mode))
    startup_warnings = runtime.get("startup_warnings") or []
    if startup_warnings:
        print("WATCHDOG_STARTUP_WARNINGS=" + ",".join(startup_warnings))
    database_target = data.get("database_target") or {}
    if database_target:
        print(
            "WATCHDOG_DATABASE_TARGET="
            + f"{database_target.get('host', 'unknown')}:{database_target.get('port', 'unknown')}/{database_target.get('database', 'unknown')}"
        )
    next_action = data.get("next_action")
    if next_action:
        print("WATCHDOG_NEXT_ACTION=" + str(next_action))
    raise SystemExit(1)
print("WATCHDOG_STATUS=ok")
PY

echo "[$TIMESTAMP] Watchdog OK" | tee -a "$WATCHDOG_LOG"
