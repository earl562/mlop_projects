#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" != "--rls" || "$#" -ne 1 ]]; then
  echo "usage: $0 --rls" >&2
  exit 2
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(cd "$script_dir/../.." && pwd)"
"$script_dir/start_storage_stack.sh" --postgres >/dev/null

admin_url="postgresql+asyncpg://storage_admin:storage_test_password@127.0.0.1:55432/plotlot_storage"
(
  cd "$project_dir"
  DATABASE_URL="$admin_url" uv run alembic upgrade head
)

docker exec plotlot-storage-postgres psql \
  --username storage_admin \
  --dbname plotlot_storage \
  --set ON_ERROR_STOP=1 \
  --command "ALTER ROLE plotlot_app LOGIN PASSWORD 'plotlot_rls_test_password';"

echo "ephemeral PostgreSQL ready on 127.0.0.1:55432 (credentials redacted)"
