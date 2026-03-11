#!/usr/bin/env bash
# Post-edit hook: auto-lint Python files with ruff
# Reads tool input from stdin, extracts file_path, runs ruff if .py

set -euo pipefail

FILE=$(cat | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('file_path',''))")

# Only process Python files
if [[ "$FILE" != *.py ]]; then
    exit 0
fi

# Only process files within the plotlot project
if [[ "$FILE" != */plotlot/* ]]; then
    exit 0
fi

cd /Users/earlperry/Desktop/Projects/EP/plotlot

# Run ruff check with auto-fix (non-blocking)
if uv run ruff check --fix "$FILE" 2>&1 | tail -5; then
    # Also run ruff format
    uv run ruff format "$FILE" 2>&1 | tail -3
fi

exit 0
