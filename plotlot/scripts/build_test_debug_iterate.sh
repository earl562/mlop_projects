#!/usr/bin/env bash
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
ARTIFACT_ROOT="${PLOTLOT_BTDI_ARTIFACT_ROOT:-$ROOT_DIR/.artifacts/btdi}"
RUN_ID="${PLOTLOT_BTDI_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
RUN_DIR="$ARTIFACT_ROOT/$RUN_ID"

RUN_BUILD=1
CONNECTED=0
HEADED=0

usage() {
  cat <<'EOF'
Usage: scripts/build_test_debug_iterate.sh [options]

Options:
  --skip-build  Skip the production frontend build.
  --connected   Run the DB/API-backed visual walkthrough instead of the deterministic lane.
  --headed      Show the browser while Playwright runs.
  -h, --help    Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-build) RUN_BUILD=0 ;;
    --connected) CONNECTED=1 ;;
    --headed) HEADED=1 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

mkdir -p "$RUN_DIR"
export PLOTLOT_PLAYWRIGHT_OUTPUT_DIR="$RUN_DIR/test-results"
export PLOTLOT_PLAYWRIGHT_REPORT_DIR="$RUN_DIR/playwright-report"
export PLOTLOT_PLAYWRIGHT_JSON="$RUN_DIR/results.json"

if [[ "$RUN_BUILD" -eq 1 ]]; then
  printf '[BTDI] Build\n'
  (
    cd "$FRONTEND_DIR"
    npm run build
  ) 2>&1 | tee "$RUN_DIR/build.log"
  build_status="${PIPESTATUS[0]}"
  if [[ "$build_status" -ne 0 ]]; then
    printf '[BTDI] Build failed. Evidence: %s\n' "$RUN_DIR"
    exit "$build_status"
  fi
fi

test_file="tests/btdi.visual.spec.ts"
projects=(--project=chromium --project=mobile-chrome)
if [[ "$CONNECTED" -eq 1 ]]; then
  test_file="tests/visual-walkthrough.spec.ts"
fi

playwright_args=(npx playwright test "$test_file" "${projects[@]}")
if [[ "$HEADED" -eq 1 ]]; then
  playwright_args+=(--headed)
fi

printf '[BTDI] Test and capture\n'
(
  cd "$FRONTEND_DIR"
  "${playwright_args[@]}"
) 2>&1 | tee "$RUN_DIR/playwright.log"
test_status="${PIPESTATUS[0]}"

node -e '
const fs = require("fs");
const path = require("path");
const runDir = process.argv[1];
const status = Number(process.argv[2]);
const payload = {
  runId: path.basename(runDir),
  status: status === 0 ? "pass" : "needs_debug",
  connected: process.argv[3] === "1",
  createdAt: new Date().toISOString(),
  artifacts: {
    buildLog: path.join(runDir, "build.log"),
    playwrightLog: path.join(runDir, "playwright.log"),
    results: path.join(runDir, "results.json"),
    report: path.join(runDir, "playwright-report"),
    testResults: path.join(runDir, "test-results"),
  },
};
fs.writeFileSync(path.join(runDir, "iteration.json"), JSON.stringify(payload, null, 2) + "\n");
' "$RUN_DIR" "$test_status" "$CONNECTED"

if [[ "$test_status" -ne 0 ]]; then
  printf '[BTDI] Needs debug. Inspect screenshots, traces, and browser-diagnostics in %s\n' "$RUN_DIR"
  exit "$test_status"
fi

printf '[BTDI] Pass. Fresh visual evidence: %s\n' "$RUN_DIR"
