#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PLOTLOT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

if [[ ! -x "${PLOTLOT_ROOT}/.venv/bin/python" ]]; then
  echo "Missing ${PLOTLOT_ROOT}/.venv/bin/python. Run \`make install\` (or \`uv sync --extra dev\`) first." >&2
  exit 1
fi

if [[ -z "${OPENAI_OAUTH_CLIENT_ID:-}" ]]; then
  echo "OPENAI_OAUTH_CLIENT_ID is required for the PKCE login flow." >&2
  exit 1
fi

cd "${PLOTLOT_ROOT}"
exec uv run plotlot-codex-login
