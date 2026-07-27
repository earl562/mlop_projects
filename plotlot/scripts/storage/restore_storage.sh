#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C

if [[ $# -ne 2 ]]; then
  echo "usage: restore_storage.sh ENCRYPTED_BACKUP RESTORE_DIR" >&2
  exit 2
fi
: "${TEST_DATABASE_URL:?TEST_DATABASE_URL is required}"
: "${STORAGE_BACKUP_PASSPHRASE:?STORAGE_BACKUP_PASSPHRASE is required}"
: "${PLOTLOT_OBJECT_STORE_ENDPOINT:?PLOTLOT_OBJECT_STORE_ENDPOINT is required}"
: "${PLOTLOT_OBJECT_STORE_BUCKET:?PLOTLOT_OBJECT_STORE_BUCKET is required}"
: "${PLOTLOT_OBJECT_STORE_ACCESS_KEY:?PLOTLOT_OBJECT_STORE_ACCESS_KEY is required}"
: "${PLOTLOT_OBJECT_STORE_SECRET_KEY:?PLOTLOT_OBJECT_STORE_SECRET_KEY is required}"
plotlot_python="${PLOTLOT_PYTHON:-python3}"

backup_file="$1"
restore_dir="$2"
work_dir="$(mktemp -d)"
stage_database=""
stage_bucket="plotlot-restore-$("$plotlot_python" -c 'import uuid; print(uuid.uuid4().hex)')"
restore_attempt=""
cleanup() {
  if [[ -n "$restore_attempt" ]]; then
    "$plotlot_python" -m plotlot.storage.restore_attempt failed \
      --attempt "$restore_attempt" --error "restore pipeline failed" >/dev/null || true
  fi
  if [[ -n "$stage_database" ]]; then
    "$plotlot_python" -m plotlot.storage.restore_database drop \
      --stage "$stage_database" >/dev/null || true
  fi
  rm -rf "$work_dir"
}
trap cleanup EXIT
mkdir -p "$restore_dir"

"$plotlot_python" -m plotlot.storage.backup_crypto decrypt \
  "$backup_file" "$work_dir/storage-backup.tar"
tar -C "$work_dir" -xf "$work_dir/storage-backup.tar"
expected_database_sha="$(sed -n 's/.*"database_sha256":"\([0-9a-f]*\)".*/\1/p' "$work_dir/manifest.json")"
expected_objects_sha="$(sed -n 's/.*"objects_sha256":"\([0-9a-f]*\)".*/\1/p' "$work_dir/manifest.json")"
actual_database_sha="$(shasum -a 256 "$work_dir/database.dump" | awk '{print $1}')"
actual_objects_sha="$(shasum -a 256 "$work_dir/objects.tar" | awk '{print $1}')"
[[ "$expected_database_sha" == "$actual_database_sha" ]]
[[ "$expected_objects_sha" == "$actual_objects_sha" ]]
pg_restore --list "$work_dir/database.dump" >/dev/null
"$plotlot_python" -m plotlot.storage.archive validate \
  --endpoint "$PLOTLOT_OBJECT_STORE_ENDPOINT" \
  --bucket "$PLOTLOT_OBJECT_STORE_BUCKET" \
  --archive "$work_dir/objects.tar" > "$restore_dir/staged-validation.json"

psql "$TEST_DATABASE_URL" -v ON_ERROR_STOP=1 -c \
  "DO \$\$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'plotlot_app') THEN
      CREATE ROLE plotlot_app NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'byright_engine') THEN
      CREATE ROLE byright_engine NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;
  END \$\$;" >/dev/null
stage_json="$("$plotlot_python" -m plotlot.storage.restore_database create)"
stage_database="$("$plotlot_python" -c 'import json,sys; print(json.load(sys.stdin)["stage"])' <<<"$stage_json")"
stage_url="$("$plotlot_python" -c 'import json,sys; print(json.load(sys.stdin)["url"])' <<<"$stage_json")"
archive_sha="$(shasum -a 256 "$backup_file" | awk '{print $1}')"
restore_attempt="$("$plotlot_python" -m plotlot.storage.restore_attempt register \
  --stage-bucket "$stage_bucket" --stage-database "$stage_database" \
  --archive-sha "$archive_sha")"
pg_restore --no-owner --dbname="$stage_url" "$work_dir/database.dump"
"$plotlot_python" -m plotlot.storage.archive restore \
  --endpoint "$PLOTLOT_OBJECT_STORE_ENDPOINT" \
  --bucket "$stage_bucket" \
  --archive "$work_dir/objects.tar" \
  --version-map "$work_dir/version-map.json" > "$restore_dir/object-restore.json"
"$plotlot_python" -m plotlot.storage.restore_attempt objects-restored \
  --attempt "$restore_attempt"
PLOTLOT_RESTORE_DATABASE_URL="$stage_url" \
PLOTLOT_RESTORE_STAGED_BUCKET="$stage_bucket" \
  "$plotlot_python" -m plotlot.storage.restore \
  --version-map "$work_dir/version-map.json" > "$restore_dir/database-remap.json"
"$plotlot_python" -m plotlot.storage.restore_attempt prepare \
  --attempt "$restore_attempt" --stage-bucket "$stage_bucket" \
  --stage-database "$stage_database" --stage-url "$stage_url" \
  --archive-sha "$archive_sha"
if [[ "${PLOTLOT_RESTORE_FAIL_AFTER_OBJECTS:-false}" == "true" ]]; then
  exit 91
fi
if [[ "${PLOTLOT_RESTORE_KILL_BEFORE_DB_RENAME:-false}" == "true" ]]; then
  kill -KILL "$$"
fi
"$plotlot_python" -m plotlot.storage.restore_database promote --stage "$stage_database"
stage_database=""
if [[ "${PLOTLOT_RESTORE_KILL_AFTER_DB_RENAME:-false}" == "true" ]]; then
  kill -KILL "$$"
fi
restore_attempt=""
cp "$work_dir/manifest.json" "$restore_dir/restore-manifest.json"
