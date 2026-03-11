#!/usr/bin/env bash
# Pre-edit hook: block edits to sensitive files
# Exit code 2 = block the tool call

set -euo pipefail

FILE=$(cat | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('file_path',''))")

if [[ -z "$FILE" ]]; then
    exit 0
fi

# Block .env files (but allow .env.example)
if [[ "$FILE" == *.env && "$FILE" != *.env.example ]]; then
    echo "BLOCKED: Cannot edit .env file — use .env.example as template" >&2
    exit 2
fi

# Block credentials and secrets
case "$FILE" in
    *credentials*|*secret*|*private_key*)
        echo "BLOCKED: Cannot edit sensitive file: $FILE" >&2
        exit 2
        ;;
esac

# Block lock files (investigate before modifying)
case "$FILE" in
    *uv.lock|*package-lock.json|*yarn.lock|*pnpm-lock.yaml)
        echo "BLOCKED: Cannot directly edit lock file — use package manager instead" >&2
        exit 2
        ;;
esac

exit 0
