#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_INSTALL=0
RUN_BACKEND=1
RUN_FRONTEND=1
RUN_BROWSER=1
RUN_BUILD=1
CHECK_AUTH=0
STRICT_AUTH=0

usage() {
  cat <<'USAGE'
Usage: bash scripts/verify_local_success.sh [options]

Runs PlotLot's deterministic local TDD success gate.

Options:
  --install        Sync/install existing project toolchains before verification.
                   Runs: uv sync --extra dev, npm install, npx playwright install chromium.
  --skip-backend   Skip backend hygiene/lint/unit checks.
  --skip-frontend  Skip all frontend checks.
  --skip-browser   Skip Playwright browser checks.
  --skip-build     Skip frontend production build.
  --check-auth     Report credential readiness without failing on missing live credentials.
  --strict-auth    Report credential readiness and fail if any live credential group is blocked.
  -h, --help       Show this help.
USAGE
}

log() {
  printf '\n\033[1;36m==> %s\033[0m\n' "$*"
}

run() {
  printf '\033[1;34m$ %s\033[0m\n' "$*"
  "$@"
}

require_cli() {
  if ! command -v "$1" >/dev/null 2>&1; then
    printf 'Missing required CLI: %s\n' "$1" >&2
    printf 'Install/sync local tools with: bash scripts/verify_local_success.sh --install\n' >&2
    return 1
  fi
}

run_ruff() {
  if [[ -x "$ROOT_DIR/.venv/bin/ruff" ]]; then
    run "$ROOT_DIR/.venv/bin/ruff" "$@"
    return
  fi
  if [[ -x "$ROOT_DIR/../.venv/bin/ruff" ]]; then
    run "$ROOT_DIR/../.venv/bin/ruff" "$@"
    return
  fi
  run uv run ruff "$@"
}

run_pytest() {
  if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
    if "$ROOT_DIR/.venv/bin/python" -c 'import pytest' >/dev/null 2>&1; then
      run env PYTHONPATH="$ROOT_DIR/src" MLFLOW_TRACKING_URI=file:///tmp/plotlot-mlruns MLFLOW_ALLOW_FILE_STORE=true "$ROOT_DIR/.venv/bin/python" -m pytest "$@"
      return
    fi
  fi
  if [[ -x "$ROOT_DIR/../.venv/bin/python" ]]; then
    run env PYTHONPATH="$ROOT_DIR/src" MLFLOW_TRACKING_URI=file:///tmp/plotlot-mlruns MLFLOW_ALLOW_FILE_STORE=true "$ROOT_DIR/../.venv/bin/python" -m pytest "$@"
    return
  fi
  run env MLFLOW_TRACKING_URI=file:///tmp/plotlot-mlruns MLFLOW_ALLOW_FILE_STORE=true uv run pytest "$@"
}

clean_playwright_artifacts() {
  rm -rf frontend/test-results frontend/playwright-report
}

can_listen_locally() {
  python3 - <<'PY' >/dev/null 2>&1
import socket

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    s.bind(("127.0.0.1", 0))
    s.listen(1)
except OSError:
    raise SystemExit(1)
finally:
    try:
        s.close()
    except Exception:
        pass
PY
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install) RUN_INSTALL=1 ;;
    --skip-backend) RUN_BACKEND=0 ;;
    --skip-frontend) RUN_FRONTEND=0 ;;
    --skip-browser) RUN_BROWSER=0 ;;
    --skip-build) RUN_BUILD=0 ;;
    --check-auth) CHECK_AUTH=1 ;;
    --strict-auth) CHECK_AUTH=1; STRICT_AUTH=1 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

cd "$ROOT_DIR"

log "Checking required CLIs"
require_cli python3
require_cli uv
require_cli node
require_cli npm
require_cli npx

if [[ "$RUN_BROWSER" -eq 1 ]] && ! can_listen_locally; then
  log "Playwright browser tests disabled: environment blocks localhost port binding (rerun without --skip-browser on a normal dev machine)"
  RUN_BROWSER=0
fi

if [[ "$RUN_INSTALL" -eq 1 ]]; then
  log "Syncing existing backend toolchain"
  run uv sync --extra dev

  log "Installing existing frontend dependencies"
  (cd frontend && run npm install)

  log "Installing Playwright Chromium browser"
  (cd frontend && run npx playwright install chromium)
fi

if [[ "$RUN_BACKEND" -eq 1 ]]; then
  log "Removing generated Playwright artifacts before hygiene"
  clean_playwright_artifacts

  log "Repository hygiene"
  run python3 scripts/check_repo_hygiene.py

  if [[ "$CHECK_AUTH" -eq 1 ]]; then
    log "Credential/auth readiness"
    if [[ "$STRICT_AUTH" -eq 1 ]]; then
      run python3 scripts/check_auth_readiness.py --strict
    else
      run python3 scripts/check_auth_readiness.py
    fi
  fi

  log "Backend/static lint"
  run_ruff check src/ tests/ scripts/

  log "Backend unit tests"
  run_pytest tests/unit -q
fi

if [[ "$RUN_FRONTEND" -eq 1 ]]; then
  log "Frontend lint"
  (cd frontend && run npm run lint)

  log "Frontend typecheck"
  (cd frontend && run npx tsc --noEmit)

  log "Frontend UI unit tests"
  (cd frontend && run npm run test:ui)

  if [[ "$RUN_BROWSER" -eq 1 ]]; then
    log "Frontend Playwright design-system tests"
    (cd frontend && run npx playwright test tests/design-system.spec.ts --project=chromium)
    log "Removing generated Playwright artifacts after successful browser tests"
    clean_playwright_artifacts
  else
    log "Skipping Playwright browser tests"
  fi

  if [[ "$RUN_BUILD" -eq 1 ]]; then
    log "Frontend production build"
    (cd frontend && run npm run build)
  else
    log "Skipping frontend production build"
  fi
fi

log "Local success gate passed"
