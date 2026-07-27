#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C

if [[ $# -ne 2 ]]; then
  echo "usage: restore_storage.sh ENCRYPTED_BACKUP RESTORE_DIR" >&2
  exit 2
fi
: "${TEST_DATABASE_URL:?TEST_DATABASE_URL is required}"
: "${STORAGE_BACKUP_PASSPHRASE:?STORAGE_BACKUP_PASSPHRASE is required}"

backup_file="$1"
restore_dir="$2"
work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT
mkdir -p "$restore_dir"

openssl enc -d -aes-256-cbc -pbkdf2 -pass env:STORAGE_BACKUP_PASSPHRASE \
  -in "$backup_file" |
  tar -C "$work_dir" -xf -
expected_database_sha="$(sed -n 's/.*"database_sha256":"\([0-9a-f]*\)".*/\1/p' "$work_dir/manifest.json")"
expected_objects_sha="$(sed -n 's/.*"objects_sha256":"\([0-9a-f]*\)".*/\1/p' "$work_dir/manifest.json")"
actual_database_sha="$(shasum -a 256 "$work_dir/database.dump" | awk '{print $1}')"
actual_objects_sha="$(shasum -a 256 "$work_dir/objects.tar" | awk '{print $1}')"
[[ "$expected_database_sha" == "$actual_database_sha" ]]
[[ "$expected_objects_sha" == "$actual_objects_sha" ]]

psql "$TEST_DATABASE_URL" -v ON_ERROR_STOP=1 -c \
  "DO \$\$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'plotlot_app') THEN
      CREATE ROLE plotlot_app NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'byright_engine') THEN
      CREATE ROLE byright_engine NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;
  END \$\$;" >/dev/null
pg_restore --clean --if-exists --no-owner --dbname="$TEST_DATABASE_URL" "$work_dir/database.dump"
tar -C "$restore_dir" -xf "$work_dir/objects.tar"
cp "$work_dir/manifest.json" "$restore_dir/restore-manifest.json"
