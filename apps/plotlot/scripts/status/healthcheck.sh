#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

TIMESTAMP="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
FRONTEND_URL="${FRONTEND_URL:-http://localhost:3002}"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8000}"
HEALTH_URL="$BACKEND_URL/health"
ANALYZE_SMOKE_ENABLED="${ANALYZE_SMOKE_ENABLED:-0}"
ANALYZE_SMOKE_URL="${ANALYZE_SMOKE_URL:-$BACKEND_URL/api/v1/analyze}"
ANALYZE_SMOKE_ADDRESS="${ANALYZE_SMOKE_ADDRESS:-171 NE 209th Ter, Miami, FL 33179}"
ANALYZE_SMOKE_TIMEOUT="${ANALYZE_SMOKE_TIMEOUT:-60}"
ANALYZE_SMOKE_PAYLOAD="${ANALYZE_SMOKE_PAYLOAD:-}"
CHAT_SMOKE_ENABLED="${CHAT_SMOKE_ENABLED:-0}"
CHAT_SMOKE_URL="${CHAT_SMOKE_URL:-$BACKEND_URL/api/v1/chat}"
CHAT_SMOKE_MESSAGE="${CHAT_SMOKE_MESSAGE:-What can I build here?}"
CHAT_SMOKE_TIMEOUT="${CHAT_SMOKE_TIMEOUT:-60}"
CHAT_SMOKE_PAYLOAD="${CHAT_SMOKE_PAYLOAD:-}"
PORTFOLIO_SMOKE_ENABLED="${PORTFOLIO_SMOKE_ENABLED:-0}"
PORTFOLIO_SMOKE_URL="${PORTFOLIO_SMOKE_URL:-$BACKEND_URL/api/v1/portfolio}"
PORTFOLIO_SMOKE_TIMEOUT="${PORTFOLIO_SMOKE_TIMEOUT:-60}"
STATUS_JSON="${STATUS_JSON:-$ROOT_DIR/docs/status/runtime-status.json}"
STATE_MD="${STATE_MD:-$ROOT_DIR/docs/status/CURRENT_STATE.md}"
HEALTH_LOG_DIR="${HEALTH_LOG_DIR:-$ROOT_DIR/logs/health}"
RUNNER_LOG_DIR="${RUNNER_LOG_DIR:-$ROOT_DIR/logs/runner}"
PROCESS_LINES_OVERRIDE="${PROCESS_LINES_OVERRIDE:-}"
mkdir -p "$HEALTH_LOG_DIR" "$RUNNER_LOG_DIR" "$ROOT_DIR/docs/status"
mkdir -p "$(dirname "$STATUS_JSON")" "$(dirname "$STATE_MD")"

HEALTH_LOG="$HEALTH_LOG_DIR/healthcheck-$(date -u +"%Y%m%dT%H%M%SZ").log"

backend_raw=""
backend_error=""
if ! backend_raw="$(curl -fsS "$HEALTH_URL" 2>&1)"; then
  backend_error="$backend_raw"
  backend_raw='{"status":"unreachable","checks":{}}'
fi

frontend_code="000"
frontend_error=""
frontend_stderr="$(mktemp)"
if ! frontend_code="$(curl -o /dev/null -sS -w "%{http_code}" "$FRONTEND_URL" 2>"$frontend_stderr")"; then
  frontend_error="$(cat "$frontend_stderr")"
  frontend_code="000"
fi
rm -f "$frontend_stderr"

if [[ -n "$PROCESS_LINES_OVERRIDE" ]]; then
  process_lines="$PROCESS_LINES_OVERRIDE"
else
  process_lines="$(ps aux | egrep 'uvicorn plotlot|next dev --port 3002|next-server' | grep -v grep || true)"
fi

parsed_output="$(python3 - <<'PY' "$backend_raw"
import json, sys
raw = sys.argv[1]
try:
    data = json.loads(raw)
except json.JSONDecodeError:
    print("invalid")
    print("unknown")
    print("unknown")
    print("unknown")
    print("unknown")
    print("[]")
    raise SystemExit(0)
checks = data.get("checks", {})
runtime = data.get("runtime", {})
print(data.get("status", "unknown"))
print(checks.get("database", "unknown"))
print(checks.get("mlflow", "unknown"))
print(checks.get("last_ingestion", "unknown"))
print(runtime.get("startup_mode", "unknown"))
print(json.dumps(runtime.get("startup_warnings", [])))
PY
)"

backend_status="$(printf '%s\n' "$parsed_output" | sed -n '1p')"
database_status="$(printf '%s\n' "$parsed_output" | sed -n '2p')"
mlflow_status="$(printf '%s\n' "$parsed_output" | sed -n '3p')"
last_ingestion="$(printf '%s\n' "$parsed_output" | sed -n '4p')"
runtime_startup_mode="$(printf '%s\n' "$parsed_output" | sed -n '5p')"
runtime_startup_warnings="$(printf '%s\n' "$parsed_output" | sed -n '6p')"

frontend_status="ok"
if [[ "$frontend_code" != "200" ]]; then
  frontend_status="unreachable"
fi

backend_seen="false"
frontend_seen="false"
if grep -q 'uvicorn plotlot.api.main:app' <<< "$process_lines"; then
  backend_seen="true"
fi
if grep -q 'next dev --port 3002\|next-server' <<< "$process_lines"; then
  frontend_seen="true"
fi

analyze_smoke_status="skipped"
analyze_smoke_http_code=""
analyze_smoke_error=""
analyze_smoke_summary=""
analyze_smoke_body=""
chat_smoke_status="skipped"
chat_smoke_http_code=""
chat_smoke_error=""
chat_smoke_summary=""
chat_smoke_body=""
portfolio_smoke_status="skipped"
portfolio_smoke_http_code=""
portfolio_smoke_error=""
portfolio_smoke_summary=""
portfolio_smoke_body=""

if [[ "$ANALYZE_SMOKE_ENABLED" == "1" ]]; then
  analyze_smoke_status="failed"
  payload="$ANALYZE_SMOKE_PAYLOAD"
  if [[ -z "$payload" ]]; then
    payload="$(python3 - <<'PY' "$ANALYZE_SMOKE_ADDRESS"
import json, sys
print(json.dumps({"address": sys.argv[1]}))
PY
)"
  fi

  smoke_body_file="$(mktemp)"
  smoke_stderr_file="$(mktemp)"
  if analyze_smoke_http_code="$(
    curl \
      -o "$smoke_body_file" \
      -sS \
      -w "%{http_code}" \
      -m "$ANALYZE_SMOKE_TIMEOUT" \
      -H "Content-Type: application/json" \
      -X POST \
      -d "$payload" \
      "$ANALYZE_SMOKE_URL" 2>"$smoke_stderr_file"
  )"; then
    analyze_smoke_body="$(cat "$smoke_body_file")"
    if [[ "$analyze_smoke_http_code" == "200" ]]; then
      analyze_smoke_status="ok"
      analyze_smoke_summary="$(python3 - <<'PY' "$analyze_smoke_body"
import json, sys
body = sys.argv[1]
try:
    data = json.loads(body)
except json.JSONDecodeError:
    print("")
    raise SystemExit(0)
address = data.get("formatted_address") or data.get("address") or ""
municipality = data.get("municipality") or ""
confidence = data.get("confidence") or ""
parts = [part for part in (address, municipality, confidence) if part]
print(" | ".join(parts))
PY
)"
    else
      analyze_smoke_error="$analyze_smoke_body"
    fi
  else
    analyze_smoke_http_code="000"
    analyze_smoke_error="$(cat "$smoke_stderr_file")"
  fi
  rm -f "$smoke_body_file" "$smoke_stderr_file"
fi

if [[ "$CHAT_SMOKE_ENABLED" == "1" ]]; then
  chat_smoke_status="failed"
  payload="$CHAT_SMOKE_PAYLOAD"
  if [[ -z "$payload" ]]; then
    payload="$(python3 - <<'PY' "$CHAT_SMOKE_MESSAGE"
import json, sys
print(json.dumps({"message": sys.argv[1], "history": [], "report_context": None}))
PY
)"
  fi

  smoke_body_file="$(mktemp)"
  smoke_stderr_file="$(mktemp)"
  if chat_smoke_http_code="$(
    curl \
      -o "$smoke_body_file" \
      -sS \
      -w "%{http_code}" \
      -m "$CHAT_SMOKE_TIMEOUT" \
      -H "Content-Type: application/json" \
      -X POST \
      -d "$payload" \
      "$CHAT_SMOKE_URL" 2>"$smoke_stderr_file"
  )"; then
    chat_smoke_body="$(cat "$smoke_body_file")"
    if [[ "$chat_smoke_http_code" == "200" ]]; then
      if grep -q "event: error" <<< "$chat_smoke_body"; then
        chat_smoke_error="$chat_smoke_body"
      elif grep -q "event: done" <<< "$chat_smoke_body"; then
        chat_smoke_status="ok"
        chat_smoke_summary="chat_sse_completed"
      else
        chat_smoke_error="$chat_smoke_body"
      fi
    else
      chat_smoke_error="$chat_smoke_body"
    fi
  else
    chat_smoke_http_code="000"
    chat_smoke_error="$(cat "$smoke_stderr_file")"
  fi
  rm -f "$smoke_body_file" "$smoke_stderr_file"
fi

if [[ "$PORTFOLIO_SMOKE_ENABLED" == "1" ]]; then
  portfolio_smoke_status="failed"
  smoke_body_file="$(mktemp)"
  smoke_stderr_file="$(mktemp)"
  if portfolio_smoke_http_code="$(
    curl \
      -o "$smoke_body_file" \
      -sS \
      -w "%{http_code}" \
      -m "$PORTFOLIO_SMOKE_TIMEOUT" \
      "$PORTFOLIO_SMOKE_URL" 2>"$smoke_stderr_file"
  )"; then
    portfolio_smoke_body="$(cat "$smoke_body_file")"
    if [[ "$portfolio_smoke_http_code" == "200" ]]; then
      portfolio_smoke_status="ok"
      portfolio_smoke_summary="$(python3 - <<'PY' "$portfolio_smoke_body"
import json, sys
body = sys.argv[1]
try:
    data = json.loads(body)
except json.JSONDecodeError:
    print("")
    raise SystemExit(0)
if isinstance(data, list):
    print(f"entries={len(data)}")
else:
    print("entries=unknown")
PY
)"
    else
      portfolio_smoke_error="$portfolio_smoke_body"
    fi
  else
    portfolio_smoke_http_code="000"
    portfolio_smoke_error="$(cat "$smoke_stderr_file")"
  fi
  rm -f "$smoke_body_file" "$smoke_stderr_file"
fi

health_ok="true"
if [[ "$backend_status" != "healthy" || "$frontend_status" != "ok" || "$database_status" != "ok" ]]; then
  health_ok="false"
fi
if [[ "$ANALYZE_SMOKE_ENABLED" == "1" && "$analyze_smoke_status" != "ok" ]]; then
  health_ok="false"
fi
if [[ "$CHAT_SMOKE_ENABLED" == "1" && "$chat_smoke_status" != "ok" ]]; then
  health_ok="false"
fi
if [[ "$PORTFOLIO_SMOKE_ENABLED" == "1" && "$portfolio_smoke_status" != "ok" ]]; then
  health_ok="false"
fi

cat > "$HEALTH_LOG" <<EOF
[$TIMESTAMP] PlotLot healthcheck
frontend_url=$FRONTEND_URL
frontend_http_code=$frontend_code
frontend_status=$frontend_status
frontend_error=$frontend_error
backend_url=$BACKEND_URL
backend_status=$backend_status
backend_error=$backend_error
database_status=$database_status
mlflow_status=$mlflow_status
last_ingestion=$last_ingestion
runtime_startup_mode=$runtime_startup_mode
runtime_startup_warnings=$runtime_startup_warnings
backend_seen=$backend_seen
frontend_seen=$frontend_seen
analyze_smoke_enabled=$ANALYZE_SMOKE_ENABLED
analyze_smoke_url=$ANALYZE_SMOKE_URL
analyze_smoke_http_code=$analyze_smoke_http_code
analyze_smoke_status=$analyze_smoke_status
analyze_smoke_summary=$analyze_smoke_summary
analyze_smoke_error=$analyze_smoke_error
chat_smoke_enabled=$CHAT_SMOKE_ENABLED
chat_smoke_url=$CHAT_SMOKE_URL
chat_smoke_http_code=$chat_smoke_http_code
chat_smoke_status=$chat_smoke_status
chat_smoke_summary=$chat_smoke_summary
chat_smoke_error=$chat_smoke_error
portfolio_smoke_enabled=$PORTFOLIO_SMOKE_ENABLED
portfolio_smoke_url=$PORTFOLIO_SMOKE_URL
portfolio_smoke_http_code=$portfolio_smoke_http_code
portfolio_smoke_status=$portfolio_smoke_status
portfolio_smoke_summary=$portfolio_smoke_summary
portfolio_smoke_error=$portfolio_smoke_error
health_ok=$health_ok

processes:
$process_lines

backend_raw:
$backend_raw

analyze_smoke_body:
$analyze_smoke_body

chat_smoke_body:
$chat_smoke_body

portfolio_smoke_body:
$portfolio_smoke_body
EOF

python3 - <<'PY' "$STATUS_JSON" "$TIMESTAMP" "$FRONTEND_URL" "$frontend_status" "$frontend_error" "$BACKEND_URL" "$backend_raw" "$backend_error" "$database_status" "$mlflow_status" "$last_ingestion" "$runtime_startup_mode" "$runtime_startup_warnings" "$backend_seen" "$frontend_seen" "$ANALYZE_SMOKE_ENABLED" "$ANALYZE_SMOKE_URL" "$ANALYZE_SMOKE_ADDRESS" "$analyze_smoke_status" "$analyze_smoke_http_code" "$analyze_smoke_summary" "$analyze_smoke_error" "$CHAT_SMOKE_ENABLED" "$CHAT_SMOKE_URL" "$CHAT_SMOKE_MESSAGE" "$chat_smoke_status" "$chat_smoke_http_code" "$chat_smoke_summary" "$chat_smoke_error" "$PORTFOLIO_SMOKE_ENABLED" "$PORTFOLIO_SMOKE_URL" "$portfolio_smoke_status" "$portfolio_smoke_http_code" "$portfolio_smoke_summary" "$portfolio_smoke_error" "$health_ok"
import json, sys
(
    path,
    ts,
    frontend_url,
    frontend_status,
    frontend_error,
    backend_url,
    backend_raw,
    backend_error,
    database_status,
    mlflow_status,
    last_ingestion,
    runtime_startup_mode,
    runtime_startup_warnings,
    backend_seen,
    frontend_seen,
    analyze_enabled,
    analyze_url,
    analyze_address,
    analyze_status,
    analyze_http_code,
    analyze_summary,
    analyze_error,
    chat_enabled,
    chat_url,
    chat_message,
    chat_status,
    chat_http_code,
    chat_summary,
    chat_error,
    portfolio_enabled,
    portfolio_url,
    portfolio_status,
    portfolio_http_code,
    portfolio_summary,
    portfolio_error,
    health_ok,
) = sys.argv[1:]
try:
    backend = json.loads(backend_raw)
except json.JSONDecodeError:
    backend = {"status": "invalid", "checks": {}}
try:
    startup_warnings = json.loads(runtime_startup_warnings)
except json.JSONDecodeError:
    startup_warnings = []
capability_details = backend.get("capability_details", {})
open_issues = []
if backend.get("status") != "healthy":
    open_issues.append("Backend healthcheck is failing")
if frontend_status != "ok":
    open_issues.append("Frontend HTTP probe is failing")
if database_status != "ok":
    open_issues.append("Database healthcheck is failing")
if analyze_enabled == "1" and analyze_status != "ok":
    open_issues.append("Analyze smoke test is failing")
if chat_enabled == "1" and chat_status != "ok":
    open_issues.append("Chat smoke test is failing")
if portfolio_enabled == "1" and portfolio_status != "ok":
    open_issues.append("Portfolio smoke test is failing")
db_backed = capability_details.get("db_backed_analysis_ready") or {}
if not db_backed.get("ready", False):
    open_issues.append(
        f"DB-backed analysis unavailable: {db_backed.get('reason', 'unknown')}"
    )
agent_chat = capability_details.get("agent_chat_ready") or {}
if not agent_chat.get("ready", False):
    open_issues.append(
        f"Agent chat unavailable: {agent_chat.get('reason', 'unknown')}"
    )
portfolio_ready = capability_details.get("portfolio_ready") or {}
if not portfolio_ready.get("ready", False):
    open_issues.append(
        f"Portfolio unavailable: {portfolio_ready.get('reason', 'unknown')}"
    )
open_issues.extend(
    [
        "No automated heartbeat to Discord/origin yet",
        "No enforced handoff protocol across sessions",
    ]
)
if analyze_enabled == "1" and analyze_status != "ok":
    next_action = "Investigate /api/v1/analyze failure before continuing product work"
elif chat_enabled == "1" and chat_status != "ok":
    next_action = "Investigate /api/v1/chat failure before continuing product work"
elif portfolio_enabled == "1" and portfolio_status != "ok":
    next_action = "Investigate /api/v1/portfolio failure before continuing product work"
elif db_backed.get("reason") == "database_unavailable":
    next_action = "Restore Postgres on localhost:5433 to re-enable db-backed analysis and portfolio flows"
elif agent_chat.get("reason") == "llm_credentials_missing":
    next_action = "Set OPENAI_API_KEY or OPENAI_ACCESS_TOKEN to re-enable agent chat"
elif health_ok != "true":
    next_action = "Fix failing health checks before continuing product work"
else:
    next_action = "Review CURRENT_STATE.md and continue highest-priority fix"
payload = {
    "updated_at": ts,
    "frontend_url": frontend_url,
    "frontend_status": frontend_status,
    "frontend_error": frontend_error,
    "backend_url": backend_url,
    "backend_status": backend.get("status", "unknown"),
    "backend_health_raw": backend,
    "backend_error": backend_error,
    "database_target": backend.get("database_target", {}),
    "database": {
        "host": (backend.get("database_target") or {}).get("host", "localhost"),
        "port": (backend.get("database_target") or {}).get("port", 5433),
        "name": (backend.get("database_target") or {}).get("database", "unknown"),
        "ssl_required": (backend.get("database_target") or {}).get("ssl_required", False),
        "status": database_status,
    },
    "mlflow_status": mlflow_status,
    "last_ingestion": last_ingestion,
    "capabilities": backend.get("capabilities", {}),
    "capability_details": backend.get("capability_details", {}),
    "runtime": {
        "startup_mode": runtime_startup_mode,
        "startup_warnings": startup_warnings,
    },
    "processes": {
        "backend_seen": backend_seen == "true",
        "frontend_seen": frontend_seen == "true",
    },
    "analyze_smoke": {
        "enabled": analyze_enabled == "1",
        "url": analyze_url,
        "address": analyze_address,
        "status": analyze_status,
        "http_status": analyze_http_code,
        "summary": analyze_summary,
        "error": analyze_error,
    },
    "chat_smoke": {
        "enabled": chat_enabled == "1",
        "url": chat_url,
        "message": chat_message,
        "status": chat_status,
        "http_status": chat_http_code,
        "summary": chat_summary,
        "error": chat_error,
    },
    "portfolio_smoke": {
        "enabled": portfolio_enabled == "1",
        "url": portfolio_url,
        "status": portfolio_status,
        "http_status": portfolio_http_code,
        "summary": portfolio_summary,
        "error": portfolio_error,
    },
    "health_ok": health_ok == "true",
    "open_issues": open_issues,
    "next_action": next_action,
}
with open(path, "w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2)
    f.write("\n")
PY

echo "Healthcheck written: $HEALTH_LOG"
echo "Status JSON updated: $STATUS_JSON"
echo "Backend: $backend_status | Frontend: $frontend_status | DB: $database_status | MLflow: $mlflow_status | Analyze smoke: $analyze_smoke_status | Chat smoke: $chat_smoke_status | Portfolio smoke: $portfolio_smoke_status"

echo "NOTE: Update $STATE_MD manually with human summary before ending a work session."

if [[ "$health_ok" != "true" ]]; then
  exit 1
fi
