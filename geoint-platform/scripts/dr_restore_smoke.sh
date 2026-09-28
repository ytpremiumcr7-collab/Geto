#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/docker-compose.prod.yml}"
BACKUP_DIR="${DR_BACKUP_DIR:-/tmp/geto-dr-backup}"
SENTINEL="geto-dr-sentinel-${GITHUB_RUN_ID:-local}"
JOB_ID="00000000-0000-4000-8000-0000000000d1"
EXECUTION_ID="00000000-0000-4000-8000-0000000000e1"

compose() {
  docker compose -f "$COMPOSE_FILE" "$@"
}

cleanup() {
  compose down -v --remove-orphans >/dev/null 2>&1 || true
  rm -rf "$BACKUP_DIR"
}
trap cleanup EXIT

: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${S3_ACCESS_KEY:?S3_ACCESS_KEY is required}"
: "${S3_SECRET_KEY:?S3_SECRET_KEY is required}"
: "${GEOINT_ENV_FILE:?GEOINT_ENV_FILE is required}"

rm -rf "$BACKUP_DIR"

echo "[dr-smoke] build production images"
compose build geoint-api geoint-web

echo "[dr-smoke] start stateful dependencies"
compose up -d --wait postgres object-store redis nats

echo "[dr-smoke] verify/provision raw S3 bucket"
compose run --rm --no-deps geoint-api \
  python scripts/s3_snapshot.py ensure --bucket geoint-raw

echo "[dr-smoke] migrate database"
compose run --rm --no-deps geoint-api alembic upgrade head

echo "[dr-smoke] create durable sentinels"
compose exec -T postgres psql -v ON_ERROR_STOP=1 \
  -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<SQL
CREATE TABLE dr_probe (
  id integer PRIMARY KEY,
  value text NOT NULL
);
INSERT INTO dr_probe(id, value) VALUES (1, '$SENTINEL');

BEGIN;
SELECT set_config('app.tenant_id', '__system__', true);
SELECT set_config('app.worker_mode', '1', true);
INSERT INTO source_jobs (
  id,
  tenant_id,
  name,
  source_id,
  job_type,
  status,
  interval_seconds,
  next_run_at,
  locked_until,
  locked_by,
  execution_id,
  attempts,
  max_attempts,
  config,
  enabled
) VALUES (
  '$JOB_ID'::uuid,
  'dr-ci',
  'dr-running-probe',
  'usgs_earthquake',
  'poll',
  'running',
  60,
  NOW(),
  NOW() + INTERVAL '5 minutes',
  'dr-smoke',
  '$EXECUTION_ID'::uuid,
  1,
  5,
  '{}'::jsonb,
  false
);
COMMIT;
SQL

printf '%s\n' "$SENTINEL" | compose run --rm -T --no-deps geoint-api \
  python scripts/s3_snapshot.py put --bucket geoint-raw --key dr/sentinel.txt

echo "[dr-smoke] take backup using production script"
BACKUP_ROOT="$(dirname "$BACKUP_DIR")" \
  "$ROOT/scripts/backup.sh" "$BACKUP_DIR"

echo "[dr-smoke] mutate authoritative state after backup"
compose exec -T postgres psql -v ON_ERROR_STOP=1 \
  -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "UPDATE dr_probe SET value = 'corrupted-after-backup' WHERE id = 1;"

compose run --rm --no-deps geoint-api \
  python scripts/s3_snapshot.py delete --bucket geoint-raw --key dr/sentinel.txt

compose exec -T redis redis-cli SET dr-stale-key should-disappear >/dev/null

echo "[dr-smoke] restore using production script"
RESTORE_CONFIRM=YES \
  HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:${GEOINT_API_PORT:-8000}/health/ready}" \
  "$ROOT/scripts/restore.sh" "$BACKUP_DIR"

echo "[dr-smoke] verify PostgreSQL sentinel"
restored="$(
  compose exec -T postgres psql -At \
    -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -c "SELECT value FROM dr_probe WHERE id = 1;"
)"
[[ "$restored" == "$SENTINEL" ]] || {
  echo "PostgreSQL sentinel mismatch: $restored" >&2
  exit 1
}

echo "[dr-smoke] verify execution reconciliation"
job_status="$(
  compose exec -T postgres psql -At \
    -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<SQL
BEGIN;
SELECT set_config('app.tenant_id', '__system__', true);
SELECT set_config('app.worker_mode', '1', true);
SELECT status FROM source_jobs WHERE id = '$JOB_ID'::uuid;
ROLLBACK;
SQL
)"
job_status="$(printf '%s\n' "$job_status" | grep -E '^(retry|running|queued|pending|failed)$' | tail -n1)"
[[ "$job_status" == "retry" ]] || {
  echo "source job was not reconciled to retry: $job_status" >&2
  exit 1
}

echo "[dr-smoke] verify S3 sentinel"
object_value="$(
  compose run --rm --no-deps geoint-api \
    python scripts/s3_snapshot.py get --bucket geoint-raw --key dr/sentinel.txt
)"
[[ "$(printf '%s' "$object_value" | tr -d '\r\n')" == "$SENTINEL" ]] || {
  echo "S3 sentinel mismatch" >&2
  exit 1
}

echo "[dr-smoke] verify Redis transport reset"
redis_value="$(compose exec -T redis redis-cli GET dr-stale-key | tr -d '\r\n')"
[[ -z "$redis_value" ]] || {
  echo "Redis stale transport state survived restore: $redis_value" >&2
  exit 1
}

echo "[dr-smoke] PASS"
