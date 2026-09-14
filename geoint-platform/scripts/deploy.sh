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

migrate() {
  log "Running alembic upgrade head"
  compose exec -T geoint-api alembic upgrade head
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
  log "Building and starting stack (APP_ENV=$APP_ENV)"
  compose pull || true
  compose build
  compose up -d
  wait_ready
  migrate
  seed
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

  up          preflight secrets → build → up → wait ready → migrate → seed
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
