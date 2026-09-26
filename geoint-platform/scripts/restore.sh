#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/docker-compose.prod.yml}"
DIR="${1:?usage: RESTORE_CONFIRM=YES restore.sh <backup-directory>}"
DB="${POSTGRES_DB:-geoint}"
APP_SERVICES=(geoint-api geoint-web geoint-scheduler geoint-worker geoint-outbox geoint-alert-notifier)

[[ "${RESTORE_CONFIRM:-}" == "YES" ]] || {
  echo "refusing destructive restore; set RESTORE_CONFIRM=YES" >&2
  exit 2
}

need() { [[ -n "${!1:-}" ]] || { echo "missing required env: $1" >&2; exit 1; }; }
compose() { docker compose -f "$COMPOSE_FILE" "$@"; }

need POSTGRES_USER
need POSTGRES_PASSWORD
need MINIO_ROOT_USER
need MINIO_ROOT_PASSWORD
need GEOINT_ENV_FILE

bash "$ROOT/scripts/verify_backup.sh" "$DIR"

echo "[restore] stopping application services"
compose stop "${APP_SERVICES[@]}" >/dev/null 2>&1 || true
compose up -d postgres minio

echo "[restore] restoring PostgreSQL"
cat "$DIR/postgres.dump" | compose exec -T postgres \
  pg_restore -U "$POSTGRES_USER" -d "$DB" --clean --if-exists --no-owner --no-privileges

echo "[restore] restoring MinIO buckets"
docker compose -f "$COMPOSE_FILE" --profile ops run --rm \
  -v "$DIR/minio:/backup:ro" \
  minio-mc '
    set -eu
    mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
    for dir in /backup/*; do
      [ -d "$dir" ] || continue
      bucket="$(basename "$dir")"
      mc mb --ignore-existing "local/$bucket" >/dev/null
      mc mirror --overwrite --remove "$dir" "local/$bucket"
    done
  '

# A backup can be restored by newer application code; advance schema only after
# the restore is complete and before any workers are allowed to run.
echo "[restore] upgrading restored schema to current code"
compose run --rm --no-deps geoint-api alembic upgrade head

echo "[restore] starting application services"
compose up -d "${APP_SERVICES[@]}"

HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:${GEOINT_API_PORT:-8000}/health/ready}"
for _ in $(seq 1 60); do
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    echo "[restore] readiness OK"
    echo "[restore] complete"
    exit 0
  fi
  sleep 2
done

echo "[restore] application did not become ready" >&2
exit 1
