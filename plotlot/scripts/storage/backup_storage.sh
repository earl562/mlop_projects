#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C

if [[ $# -ne 1 ]]; then
  echo "usage: backup_storage.sh OUTPUT_DIR" >&2
  exit 2
fi
: "${TEST_DATABASE_URL:?TEST_DATABASE_URL is required}"
: "${STORAGE_BACKUP_PASSPHRASE:?STORAGE_BACKUP_PASSPHRASE is required}"
: "${PLOTLOT_OBJECT_STORE_ENDPOINT:?PLOTLOT_OBJECT_STORE_ENDPOINT is required}"
: "${PLOTLOT_OBJECT_STORE_BUCKET:?PLOTLOT_OBJECT_STORE_BUCKET is required}"
: "${PLOTLOT_OBJECT_STORE_ACCESS_KEY:?PLOTLOT_OBJECT_STORE_ACCESS_KEY is required}"
: "${PLOTLOT_OBJECT_STORE_SECRET_KEY:?PLOTLOT_OBJECT_STORE_SECRET_KEY is required}"
plotlot_python="${PLOTLOT_PYTHON:-python3}"

"$plotlot_python" -m plotlot.storage.backup "$1"
