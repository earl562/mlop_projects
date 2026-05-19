#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PLOTLOT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

if [[ ! -x "${PLOTLOT_ROOT}/.venv/bin/python" ]]; then
  echo "Missing ${PLOTLOT_ROOT}/.venv/bin/python. Run \`make install\` (or \`uv sync --extra dev\`) first." >&2
  exit 1
fi

# Opt-in to loading the Codex OAuth token from ~/.codex/auth.json.
export PLOTLOT_USE_CODEX_OAUTH=1

# If the monorepo root has a local .env (gitignored) with alternate provider
# credentials (for example GROQ_API_KEY or NVIDIA_API_KEY), load it so local
# runs don't hard-fail when Codex OAuth is rate-limited. Existing exported vars
# still win.
MONOREPO_ENV_FILE="${PLOTLOT_ROOT}/../../.env"
if [[ -f "${MONOREPO_ENV_FILE}" ]]; then
  while IFS= read -r line || [[ -n "${line:-}" ]]; do
    [[ -z "${line}" ]] && continue
    [[ "${line}" =~ ^[[:space:]]*# ]] && continue
    line="${line#"export "}"

    if [[ "${line}" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
      var_name="${BASH_REMATCH[1]}"
      var_value="${BASH_REMATCH[2]}"

      # Ignore empty assignments and anything already configured upstream.
      [[ -z "${var_value}" ]] && continue
      [[ -n "${!var_name-}" ]] && continue

      # Strip surrounding quotes, matching the common dotenv formats.
      if [[ "${var_value}" =~ ^\"(.*)\"$ ]] || [[ "${var_value}" =~ ^\'(.*)\'$ ]]; then
        var_value="${BASH_REMATCH[1]}"
      fi

      export "${var_name}=${var_value}"
    fi
  done < "${MONOREPO_ENV_FILE}"
fi

# Local dev defaults: Codex OAuth can be rate-limited for larger models.
# Keep this overrideable by exporting OPENAI_MODEL / OPENAI_REASONING_EFFORT.
export OPENAI_MODEL="${OPENAI_MODEL:-gpt-4.1-mini}"
export OPENAI_REASONING_EFFORT="${OPENAI_REASONING_EFFORT:-low}"

CODEX_AUTH_FILE="${PLOTLOT_CODEX_AUTH_FILE:-$HOME/.codex/auth.json}"
if [[ "${CODEX_AUTH_FILE}" == "~"* ]]; then
  CODEX_AUTH_FILE="${CODEX_AUTH_FILE/#\~/$HOME}"
fi

if [[ ! -f "${CODEX_AUTH_FILE}" ]]; then
  if [[ -n "${GROQ_API_KEY:-}${NVIDIA_API_KEY:-}${OPENAI_API_KEY:-}${OPENAI_ACCESS_TOKEN:-}${OPENROUTER_API_KEY:-}" ]]; then
    echo "Codex OAuth token file not found; continuing with configured non-Codex LLM credentials." >&2
    export PLOTLOT_USE_CODEX_OAUTH=0
  else
    echo "No LLM credentials found. Set GROQ_API_KEY, NVIDIA_API_KEY, OPENAI_API_KEY, OPENAI_ACCESS_TOKEN, OPENROUTER_API_KEY, or run ./scripts/login_with_codex_oauth.sh." >&2
    exit 1
  fi
fi

cd "${PLOTLOT_ROOT}"
exec "${PLOTLOT_ROOT}/.venv/bin/python" -m uvicorn plotlot.api.main:app --host 127.0.0.1 --port 8000
