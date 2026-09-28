#!/usr/bin/env bash
# GEOINT production/staging deploy — single runbook entrypoint.
#
# Usage (on the target host, with secrets already available):
#   export GEOINT_ENV_FILE=/run/secrets/geoint.env
#   export POSTGRES_USER=... POSTGRES_PASSWORD=... MINIO_ROOT_USER=... MINIO_ROOT_PASSWORD=...
#   ./scripts/deploy.sh up
#
# Or via CI SSH:
#   ./scripts/deploy.sh remote-up
#
# Required secrets are NEVER defaulted to change-me. Missing vars fail the script.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/docker-compose.prod.yml}"
APP_ENV="${APP_ENV:-production}"
SEED_SQL="${SEED_SQL:-$ROOT/seed_source_jobs.sql}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:${GEOINT_API_PORT:-8000}/health/ready}"
MAX_WAIT_READY="${MAX_WAIT_READY:-120}"
APP_SERVICES=(geoint-api geoint-web geoint-scheduler geoint-worker geoint-outbox geoint-alert-notifier)
ANALYTICS_ENABLED=0

log() { printf '[deploy] %s\n' "$*"; }
die() { printf '[deploy] ERROR: %s\n' "$*" >&2; exit 1; }

require_var() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    die "Required environment variable $name is not set"
  fi
}

forbid_placeholder() {
  local name="$1"
  local val="${!name:-}"
  case "${val,,}" in
    ""|change-me*|password|minioadmin*|geoint|secret|admin)
      die "$name has a forbidden placeholder/default value"
      ;;
  esac
}

preflight_secrets() {
  require_var POSTGRES_USER
  require_var POSTGRES_PASSWORD
  require_var MINIO_ROOT_USER
  require_var MINIO_ROOT_PASSWORD
  require_var GEOINT_ENV_FILE
  forbid_placeholder POSTGRES_PASSWORD
  forbid_placeholder MINIO_ROOT_PASSWORD
  forbid_placeholder MINIO_ROOT_USER
  [[ -f "$GEOINT_ENV_FILE" ]] || die "GEOINT_ENV_FILE not found: $GEOINT_ENV_FILE"
  [[ -f "$COMPOSE_FILE" ]] || die "Compose file not found: $COMPOSE_FILE"

  # API env must declare production guards
  if ! grep -qE '^[[:space:]]*APP_ENV=(production|prod|staging)' "$GEOINT_ENV_FILE" \
    && [[ "${APP_ENV}" != "development" ]]; then
    log "WARN: APP_ENV not production/staging inside $GEOINT_ENV_FILE (compose will set APP_ENV=${APP_ENV})"
  fi
  if ! grep -qE '^[[:space:]]*JWT_JWKS_URL=https://' "$GEOINT_ENV_FILE"; then
    if ! grep -qE '^[[:space:]]*ALLOW_HS256_IN_PRODUCTION=true' "$GEOINT_ENV_FILE"; then
      die "GEOINT_ENV_FILE must set JWT_JWKS_URL=https://… (or emergency ALLOW_HS256_IN_PRODUCTION=true)"
    fi
    log "WARN: ALLOW_HS256_IN_PRODUCTION break-glass enabled"
  fi
  if ! grep -qE '^[[:space:]]*CORS_ORIGINS=https://' "$GEOINT_ENV_FILE"; then
    die "GEOINT_ENV_FILE must set CORS_ORIGINS=https://… (comma-separated, no *)"
  fi
  if grep -qiE 'change-me|AUTH_DISABLED=true' "$GEOINT_ENV_FILE"; then
    die "GEOINT_ENV_FILE contains change-me or AUTH_DISABLED=true"
  fi

  if grep -qiE '^[[:space:]]*CLICKHOUSE_ENABLED=(true|1|yes)[[:space:]]*
compose() {
  docker compose -f "$COMPOSE_FILE" "$@"
}

wait_ready() {
  local i=0
  log "Waiting for $HEALTH_URL (max ${MAX_WAIT_READY}s)"
  until curl -fsS "$HEALTH_URL" >/dev/null 2>&1; do
    i=$((i + 2))
    if [[ "$i" -ge "$MAX_WAIT_READY" ]]; then
      die "Service not ready after ${MAX_WAIT_READY}s — check: compose logs geoint-api"
    fi
    sleep 2
  done
  log "Health ready OK"
  curl -fsS "$HEALTH_URL" || true
  echo
}

pull_dependencies() {
  local deps=(postgres redis nats minio)
  if [[ "$ANALYTICS_ENABLED" == "1" ]]; then
    deps+=(clickhouse)
  fi
  log "Pulling stateful dependency images: ${deps[*]}"
  compose pull "${deps[@]}"
}

start_dependencies() {
  compose up -d postgres redis nats minio
  if [[ "$ANALYTICS_ENABLED" == "1" ]]; then
    compose up -d clickhouse
  fi
}

quiesce_apps() {
  log "Stopping existing application writers before schema migration"
  compose stop "${APP_SERVICES[@]}" >/dev/null 2>&1 || true
}

migrate() {
  log "Running alembic upgrade head before application services start"
  compose run --rm --no-deps geoint-api alembic upgrade head
}

seed() {
  if [[ ! -f "$SEED_SQL" ]]; then
    log "No seed file at $SEED_SQL — skipping"
    return 0
  fi
  log "Seeding source_jobs (idempotent ON CONFLICT DO NOTHING)"
  # Copy seed into postgres container and apply
  local db="${POSTGRES_DB:-geoint}"
  compose exec -T postgres \
    psql -U "$POSTGRES_USER" -d "$db" < "$SEED_SQL" \
    || log "WARN: seed returned non-zero (may already be applied)"
}

cmd_up() {
  preflight_secrets
  export APP_ENV
  log "Building stack (APP_ENV=$APP_ENV)"
  pull_dependencies
  compose build

  # A redeploy may still have previous API/workers running. Quiesce them before
  # any schema transition; otherwise old code can write while Alembic changes
  # invariants underneath it.
  quiesce_apps

  # Bring up only stateful dependencies first. New application code must never
  # execute against the previous schema.
  start_dependencies
  migrate
  seed

  # Start API/workers only after schema migration and seed complete.
  compose up -d geoint-api geoint-web geoint-scheduler geoint-worker geoint-outbox geoint-alert-notifier
  wait_ready
  log "Deploy complete"
  compose ps
}

cmd_migrate() {
  preflight_secrets
  migrate
}

cmd_seed() {
  preflight_secrets
  seed
}

cmd_down() {
  compose down
}

cmd_status() {
  compose ps
  curl -fsS "$HEALTH_URL" || true
  echo
}

cmd_remote_up() {
  # CI entry: expects SSH access configured and remote path with repo + secrets
  require_var DEPLOY_HOST
  require_var DEPLOY_USER
  local remote_path="${DEPLOY_PATH:-/opt/geoint}"
  local ssh_opts=(-o BatchMode=yes -o StrictHostKeyChecking=accept-new)
  if [[ -n "${DEPLOY_SSH_KEY:-}" ]]; then
    ssh_opts+=(-i "$DEPLOY_SSH_KEY")
  fi
  log "Remote deploy to ${DEPLOY_USER}@${DEPLOY_HOST}:${remote_path}"
  ssh "${ssh_opts[@]}" "${DEPLOY_USER}@${DEPLOY_HOST}" \
    "set -euo pipefail; cd '$remote_path'; git fetch --depth 1 origin main; git checkout -f origin/main; ./geoint-platform/scripts/deploy.sh up"
}

usage() {
  cat <<EOF
Usage: $0 <up|migrate|seed|down|status|remote-up>

  up          preflight → build → dependencies → migrate → seed → app → readiness
  migrate     alembic upgrade head only
  seed        apply seed_source_jobs.sql
  down        compose down
  status      compose ps + health
  remote-up   SSH to DEPLOY_HOST and run up (for GitHub Actions)

Environment:
  GEOINT_ENV_FILE   path to API env (JWT_JWKS_URL, CORS_ORIGINS, …)
  POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB
  MINIO_ROOT_USER / MINIO_ROOT_PASSWORD
  APP_ENV           production|staging (default production)
  COMPOSE_FILE      default docker-compose.prod.yml
  DEPLOY_HOST / DEPLOY_USER / DEPLOY_PATH / DEPLOY_SSH_KEY  (remote-up)
EOF
}

main() {
  local cmd="${1:-}"
  case "$cmd" in
    up) cmd_up ;;
    migrate) cmd_migrate ;;
    seed) cmd_seed ;;
    down) cmd_down ;;
    status) cmd_status ;;
    remote-up) cmd_remote_up ;;
    -h|--help|help|"") usage; [[ -n "$cmd" ]] || exit 1 ;;
    *) die "Unknown command: $cmd" ;;
  esac
}

main "$@"
 "$GEOINT_ENV_FILE"; then
    local ch_user ch_password
    ch_user="$(grep -E '^[[:space:]]*CLICKHOUSE_USER=' "$GEOINT_ENV_FILE" | tail -n1 | cut -d= -f2- | xargs)"
    ch_password="$(grep -E '^[[:space:]]*CLICKHOUSE_PASSWORD=' "$GEOINT_ENV_FILE" | tail -n1 | cut -d= -f2- | xargs)"
    [[ -n "$ch_user" ]] || die "CLICKHOUSE_USER is required when CLICKHOUSE_ENABLED=true"
    [[ -n "$ch_password" ]] || die "CLICKHOUSE_PASSWORD is required when CLICKHOUSE_ENABLED=true"
    case "${ch_password,,}" in
      change-me*|password|geoint_ch|secret|admin)
        die "CLICKHOUSE_PASSWORD has a forbidden placeholder/default value"
        ;;
    esac
    ANALYTICS_ENABLED=1
    if [[ ",${COMPOSE_PROFILES:-}," != *",analytics,"* ]]; then
      export COMPOSE_PROFILES="${COMPOSE_PROFILES:+$COMPOSE_PROFILES,}analytics"
    fi
  fi
}

compose() {
  docker compose -f "$COMPOSE_FILE" "$@"
}

wait_ready() {
  local i=0
  log "Waiting for $HEALTH_URL (max ${MAX_WAIT_READY}s)"
  until curl -fsS "$HEALTH_URL" >/dev/null 2>&1; do
    i=$((i + 2))
    if [[ "$i" -ge "$MAX_WAIT_READY" ]]; then
      die "Service not ready after ${MAX_WAIT_READY}s — check: compose logs geoint-api"
    fi
    sleep 2
  done
  log "Health ready OK"
  curl -fsS "$HEALTH_URL" || true
  echo
}

quiesce_apps() {
  log "Stopping existing application writers before schema migration"
  compose stop "${APP_SERVICES[@]}" >/dev/null 2>&1 || true
}

migrate() {
  log "Running alembic upgrade head before application services start"
  compose run --rm --no-deps geoint-api alembic upgrade head
}

seed() {
  if [[ ! -f "$SEED_SQL" ]]; then
    log "No seed file at $SEED_SQL — skipping"
    return 0
  fi
  log "Seeding source_jobs (idempotent ON CONFLICT DO NOTHING)"
  # Copy seed into postgres container and apply
  local db="${POSTGRES_DB:-geoint}"
  compose exec -T postgres \
    psql -U "$POSTGRES_USER" -d "$db" < "$SEED_SQL" \
    || log "WARN: seed returned non-zero (may already be applied)"
}

cmd_up() {
  preflight_secrets
  export APP_ENV
  log "Building stack (APP_ENV=$APP_ENV)"
  compose pull || true
  compose build

  # A redeploy may still have previous API/workers running. Quiesce them before
  # any schema transition; otherwise old code can write while Alembic changes
  # invariants underneath it.
  quiesce_apps

  # Bring up only stateful dependencies first. New application code must never
  # execute against the previous schema.
  compose up -d postgres redis nats minio
  migrate
  seed

  # Start API/workers only after schema migration and seed complete.
  compose up -d geoint-api geoint-web geoint-scheduler geoint-worker geoint-outbox geoint-alert-notifier
  wait_ready
  log "Deploy complete"
  compose ps
}

cmd_migrate() {
  preflight_secrets
  migrate
}

cmd_seed() {
  preflight_secrets
  seed
}

cmd_down() {
  compose down
}

cmd_status() {
  compose ps
  curl -fsS "$HEALTH_URL" || true
  echo
}

cmd_remote_up() {
  # CI entry: expects SSH access configured and remote path with repo + secrets
  require_var DEPLOY_HOST
  require_var DEPLOY_USER
  local remote_path="${DEPLOY_PATH:-/opt/geoint}"
  local ssh_opts=(-o BatchMode=yes -o StrictHostKeyChecking=accept-new)
  if [[ -n "${DEPLOY_SSH_KEY:-}" ]]; then
    ssh_opts+=(-i "$DEPLOY_SSH_KEY")
  fi
  log "Remote deploy to ${DEPLOY_USER}@${DEPLOY_HOST}:${remote_path}"
  ssh "${ssh_opts[@]}" "${DEPLOY_USER}@${DEPLOY_HOST}" \
    "set -euo pipefail; cd '$remote_path'; git fetch --depth 1 origin main; git checkout -f origin/main; ./geoint-platform/scripts/deploy.sh up"
}

usage() {
  cat <<EOF
Usage: $0 <up|migrate|seed|down|status|remote-up>

  up          preflight → build → dependencies → migrate → seed → app → readiness
  migrate     alembic upgrade head only
  seed        apply seed_source_jobs.sql
  down        compose down
  status      compose ps + health
  remote-up   SSH to DEPLOY_HOST and run up (for GitHub Actions)

Environment:
  GEOINT_ENV_FILE   path to API env (JWT_JWKS_URL, CORS_ORIGINS, …)
  POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB
  MINIO_ROOT_USER / MINIO_ROOT_PASSWORD
  APP_ENV           production|staging (default production)
  COMPOSE_FILE      default docker-compose.prod.yml
  DEPLOY_HOST / DEPLOY_USER / DEPLOY_PATH / DEPLOY_SSH_KEY  (remote-up)
EOF
}

main() {
  local cmd="${1:-}"
  case "$cmd" in
    up) cmd_up ;;
    migrate) cmd_migrate ;;
    seed) cmd_seed ;;
    down) cmd_down ;;
    status) cmd_status ;;
    remote-up) cmd_remote_up ;;
    -h|--help|help|"") usage; [[ -n "$cmd" ]] || exit 1 ;;
    *) die "Unknown command: $cmd" ;;
  esac
}

main "$@"
