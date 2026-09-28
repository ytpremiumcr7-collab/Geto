#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/docker-compose.prod.yml}"
DIR="${1:?usage: RESTORE_CONFIRM=YES restore.sh <backup-directory>}"
DB="${POSTGRES_DB:-geoint}"
APP_SERVICES=(
  geoint-api
  geoint-web
  geoint-scheduler
  geoint-worker
  geoint-outbox
  geoint-alert-notifier
)
ANALYTICS_ENABLED=0

[[ "${RESTORE_CONFIRM:-}" == "YES" ]] || {
  echo "refusing destructive restore; set RESTORE_CONFIRM=YES" >&2
  exit 2
}

need() {
  [[ -n "${!1:-}" ]] || {
    echo "missing required env: $1" >&2
    exit 1
  }
}

compose() {
  docker compose -f "$COMPOSE_FILE" "$@"
}

env_value() {
  local key="$1"
  awk -v key="$key" '
    {
      line = $0
      sub(/^[[:space:]]*/, "", line)
      if (index(line, key "=") == 1) {
        sub(/^[^=]*=/, "", line)
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", line)
        value = line
      }
    }
    END { print value }
  ' "$GEOINT_ENV_FILE"
}

need POSTGRES_USER
need POSTGRES_PASSWORD
need MINIO_ROOT_USER
need MINIO_ROOT_PASSWORD
need GEOINT_ENV_FILE

[[ -f "$GEOINT_ENV_FILE" ]] || {
  echo "GEOINT_ENV_FILE not found: $GEOINT_ENV_FILE" >&2
  exit 1
}

case "$(env_value CLICKHOUSE_ENABLED | tr '[:upper:]' '[:lower:]')" in
  true|1|yes)
    [[ -n "$(env_value CLICKHOUSE_USER)" ]] || {
      echo "CLICKHOUSE_USER is required for analytics restore" >&2
      exit 1
    }
    [[ -n "$(env_value CLICKHOUSE_PASSWORD)" ]] || {
      echo "CLICKHOUSE_PASSWORD is required for analytics restore" >&2
      exit 1
    }
    ANALYTICS_ENABLED=1
    if [[ ",${COMPOSE_PROFILES:-}," != *",analytics,"* ]]; then
      export COMPOSE_PROFILES="${COMPOSE_PROFILES:+$COMPOSE_PROFILES,}analytics"
    fi
    ;;
esac

bash "$ROOT/scripts/verify_backup.sh" "$DIR"

echo "[restore] stopping application services"
compose stop "${APP_SERVICES[@]}" >/dev/null 2>&1 || true

echo "[restore] starting authoritative storage"
compose up -d --wait postgres minio

echo "[restore] restoring PostgreSQL"
cat "$DIR/postgres.dump" | compose exec -T postgres \
  pg_restore -U "$POSTGRES_USER" -d "$DB" \
    --clean --if-exists --no-owner --no-privileges

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

echo "[restore] upgrading restored schema to current code"
compose run --rm --no-deps geoint-api alembic upgrade head

echo "[restore] resetting ephemeral Redis/NATS transport state"
compose up -d --wait redis nats
compose run --rm --no-deps \
  -e RESTORE_CONFIRM=YES \
  geoint-api python scripts/reset_transport.py

echo "[restore] reconciling durable leases/executions after transport reset"
compose exec -T postgres \
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$DB" \
  < "$ROOT/scripts/recover_after_restore.sql"

if [[ "$ANALYTICS_ENABLED" == "1" ]]; then
  echo "[restore] starting derived ClickHouse analytics"
  compose up -d --wait clickhouse

  echo "[restore] applying ClickHouse derived schema"
  compose run --rm --no-deps \
    geoint-api python scripts/clickhouse_bootstrap.py

  echo "[restore] rebuilding ClickHouse from authoritative PostgreSQL observations"
  compose run --rm --no-deps \
    -e GEOINT_SYSTEM_WORKER=1 \
    geoint-api python scripts/rebuild_clickhouse.py
fi

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
