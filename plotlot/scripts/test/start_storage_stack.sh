#!/usr/bin/env bash
set -euo pipefail

docker_resources="/Applications/Docker.app/Contents/Resources/bin"
if [[ -d "$docker_resources" ]]; then
  export PATH="$docker_resources:$PATH"
fi

start_postgres=false
start_object_store=false
for argument in "$@"; do
  case "$argument" in
    --postgres) start_postgres=true ;;
    --object-store) start_object_store=true ;;
    *) echo "unknown argument: $argument" >&2; exit 2 ;;
  esac
done

if [[ "$start_postgres" == false && "$start_object_store" == false ]]; then
  echo "select --postgres and/or --object-store" >&2
  exit 2
fi

if [[ "$start_postgres" == true ]]; then
  docker rm -f plotlot-storage-postgres >/dev/null 2>&1 || true
  docker run --detach --name plotlot-storage-postgres \
    --env POSTGRES_USER=storage_admin \
    --env POSTGRES_PASSWORD=storage_test_password \
    --env POSTGRES_DB=plotlot_storage \
    --publish 55432:5432 \
    pgvector/pgvector:pg16 >/dev/null
  for _ in {1..60}; do
    if docker exec plotlot-storage-postgres pg_isready -U storage_admin -d plotlot_storage \
      >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  docker exec plotlot-storage-postgres pg_isready -U storage_admin -d plotlot_storage >/dev/null
fi

if [[ "$start_object_store" == true ]]; then
  docker rm -f plotlot-storage-minio >/dev/null 2>&1 || true
  docker run --detach --name plotlot-storage-minio \
    --env MINIO_ROOT_USER=storage_admin \
    --env MINIO_ROOT_PASSWORD=storage_test_password \
    --publish 59000:9000 \
    --publish 59001:9001 \
    minio/minio:latest server /data --console-address :9001 >/dev/null
  for _ in {1..60}; do
    if curl --fail --silent http://127.0.0.1:59000/minio/health/ready >/dev/null; then
      break
    fi
    sleep 1
  done
  curl --fail --silent http://127.0.0.1:59000/minio/health/ready >/dev/null
fi

printf '%s\n' \
  'DATABASE_URL=postgresql+asyncpg://storage_admin:storage_test_password@127.0.0.1:55432/plotlot_storage' \
  'TEST_DATABASE_URL=postgresql://storage_admin:storage_test_password@127.0.0.1:55432/plotlot_storage' \
  'S3_ENDPOINT=http://127.0.0.1:59000'
