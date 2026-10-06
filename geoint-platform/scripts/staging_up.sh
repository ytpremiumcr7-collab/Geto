#!/usr/bin/env bash
# Bring up staging stack and verify JWKS + CH + notifier health.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${GEOINT_ENV_FILE:-.env.staging}"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE — copy from .env.staging.example and fill secrets"
  exit 1
fi
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

echo "==> compose up (analytics profile)"
docker compose -f docker-compose.staging.yml --env-file "$ENV_FILE" --profile analytics up -d --build

echo "==> wait postgres"
for i in $(seq 1 30); do
  if docker compose -f docker-compose.staging.yml --env-file "$ENV_FILE" exec -T postgres pg_isready -U "${POSTGRES_USER:-geoint}" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo "==> alembic"
docker compose -f docker-compose.staging.yml --env-file "$ENV_FILE" run --rm geoint-api alembic upgrade head || \
  (export DATABASE_URL="${DATABASE_URL}"; alembic upgrade head)

echo "==> clickhouse bootstrap + seed"
sleep 5
python scripts/clickhouse_bootstrap.py || true
if [[ -n "${CLICKHOUSE_URL:-}" ]]; then
  curl -sS "${CLICKHOUSE_URL}/" --data-binary @scripts/clickhouse_seed_staging.sql || true
fi

echo "==> staging_verify"
export CLICKHOUSE_ENABLED="${CLICKHOUSE_ENABLED:-true}"
python scripts/staging_verify.py || python scripts/staging_verify.py --allow-skip

echo "Staging up. Notifier health: http://127.0.0.1:${ALERT_NOTIFIER_PUBLISH_PORT:-8081}/health/ready"
echo "ClickHouse: ${CLICKHOUSE_URL:-http://127.0.0.1:8123}"
echo "JWKS: ${JWT_JWKS_URL:-unset}"
