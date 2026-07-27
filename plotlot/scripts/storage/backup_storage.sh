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

output_dir="$1"
work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT
mkdir -p "$output_dir"

pg_dump --format=custom --no-owner --file="$work_dir/database.dump" "$TEST_DATABASE_URL"
"$plotlot_python" -m plotlot.storage.archive export \
  --endpoint "$PLOTLOT_OBJECT_STORE_ENDPOINT" \
  --bucket "$PLOTLOT_OBJECT_STORE_BUCKET" \
  --archive "$work_dir/objects.tar" > "$work_dir/object-export.json"
database_sha="$(shasum -a 256 "$work_dir/database.dump" | awk '{print $1}')"
objects_sha="$(shasum -a 256 "$work_dir/objects.tar" | awk '{print $1}')"
created_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf '{"version":"1","created_at":"%s","rpo_minutes":15,"rto_hours":4,"database_sha256":"%s","objects_sha256":"%s"}\n' \
  "$created_at" "$database_sha" "$objects_sha" > "$work_dir/manifest.json"
tar -C "$work_dir" -cf - database.dump objects.tar object-export.json manifest.json |
  openssl enc -aes-256-cbc -salt -pbkdf2 -pass env:STORAGE_BACKUP_PASSPHRASE \
    -out "$output_dir/storage-backup.tar.enc"
shasum -a 256 "$output_dir/storage-backup.tar.enc" |
  awk '{print $1}' > "$output_dir/storage-backup.tar.enc.sha256"
