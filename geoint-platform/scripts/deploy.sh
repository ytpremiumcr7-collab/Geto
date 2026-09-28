#!/usr/bin/env bash
# GEOINT production/staging deploy — single runbook entrypoint.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/docker-compose.prod.yml}"
APP_ENV="${APP_ENV:-production}"
SEED_SQL="${SEED_SQL:-$ROOT/seed_source_jobs.sql}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:${GEOINT_API_PORT:-8000}/health/ready}"
MAX_WAIT_READY="${MAX_WAIT_READY:-120}"
APP_SERVICES=(
  geoint-api
  geoint-web
  geoint-scheduler
  geoint-worker
  geoint-outbox
  geoint-alert-notifier
)
ANALYTICS_ENABLED=0

log() {
  printf '[deploy] %s\n' "$*"
}

die() {
  printf '[deploy] ERROR: %s\n' "$*" >&2
  exit 1
}

require_var() {
  local name="$1"
  [[ -n "${!name:-}" ]] || die "Required environment variable $name is not set"
}

forbid_placeholder() {
  local name="$1"
  local val="${!name:-}"
  case "${val,,}" in
    ""|change-me*|password|geoint|secret|admin)
      die "$name has a forbidden placeholder/default value"
      ;;
  esac
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

preflight_secrets() {
  require_var POSTGRES_USER
  require_var POSTGRES_PASSWORD
  require_var S3_ACCESS_KEY
  require_var S3_SECRET_KEY
  require_var GEOINT_ENV_FILE

  forbid_placeholder POSTGRES_PASSWORD
  forbid_placeholder S3_SECRET_KEY
  forbid_placeholder S3_ACCESS_KEY

  [[ -f "$GEOINT_ENV_FILE" ]] || die "GEOINT_ENV_FILE not found: $GEOINT_ENV_FILE"
  [[ -f "$COMPOSE_FILE" ]] || die "Compose file not found: $COMPOSE_FILE"

  if ! grep -qE '^[[:space:]]*APP_ENV=(production|prod|staging)' "$GEOINT_ENV_FILE" \
    && [[ "$APP_ENV" != "development" ]]; then
    log "WARN: env file does not declare production/staging; compose overrides APP_ENV=$APP_ENV"
  fi

  if ! grep -qE '^[[:space:]]*JWT_JWKS_URL=https://' "$GEOINT_ENV_FILE"; then
    if ! grep -qE '^[[:space:]]*ALLOW_HS256_IN_PRODUCTION=true' "$GEOINT_ENV_FILE"; then
      die "GEOINT_ENV_FILE must set JWT_JWKS_URL=https://… or emergency HS256 override"
    fi
    log "WARN: ALLOW_HS256_IN_PRODUCTION break-glass enabled"
  fi

  grep -qE '^[[:space:]]*CORS_ORIGINS=https://' "$GEOINT_ENV_FILE" \
    || die "GEOINT_ENV_FILE must set CORS_ORIGINS=https://… (no wildcard)"

  if grep -qiE 'change-me|AUTH_DISABLED=true' "$GEOINT_ENV_FILE"; then
    die "GEOINT_ENV_FILE contains a forbidden placeholder or AUTH_DISABLED=true"
  fi

  case "$(env_value CLICKHOUSE_ENABLED | tr '[:upper:]' '[:lower:]')" in
    true|1|yes)
      local ch_user ch_password
      ch_user="$(env_value CLICKHOUSE_USER)"
      ch_password="$(env_value CLICKHOUSE_PASSWORD)"
      [[ -n "$ch_user" ]] || die "CLICKHOUSE_USER is required when analytics is enabled"
      [[ -n "$ch_password" ]] \
        || die "CLICKHOUSE_PASSWORD is required when analytics is enabled"
      case "${ch_password,,}" in
        change-me*|password|geoint_ch|secret|admin)
          die "CLICKHOUSE_PASSWORD has a forbidden placeholder/default value"
          ;;
      esac
      ANALYTICS_ENABLED=1
      if [[ ",${COMPOSE_PROFILES:-}," != *",analytics,"* ]]; then
        export COMPOSE_PROFILES="${COMPOSE_PROFILES:+$COMPOSE_PROFILES,}analytics"
      fi
      ;;
  esac
}

compose() {
  docker compose -f "$COMPOSE_FILE" "$@"
}

wait_ready() {
  local elapsed=0
  log "Waiting for $HEALTH_URL (max ${MAX_WAIT_READY}s)"
  until curl -fsS "$HEALTH_URL" >/dev/null 2>&1; do
    elapsed=$((elapsed + 2))
    if [[ "$elapsed" -ge "$MAX_WAIT_READY" ]]; then
      compose logs --tail=200 geoint-api >&2 || true
      die "Service not ready after ${MAX_WAIT_READY}s"
    fi
    sleep 2
  done
  log "Health ready OK"
}

pull_dependencies() {
  local deps=(postgres redis nats object-store)
  if [[ "$ANALYTICS_ENABLED" == "1" ]]; then
    deps+=(clickhouse)
  fi
  log "Pulling stateful dependency images: ${deps[*]}"
  compose pull "${deps[@]}"
}

start_dependencies() {
  log "Starting required stateful dependencies"
  compose up -d --wait postgres redis nats object-store
  if [[ "$ANALYTICS_ENABLED" == "1" ]]; then
    compose up -d --wait clickhouse
  fi
}

quiesce_apps() {
  log "Stopping existing application writers before schema migration"
  compose stop "${APP_SERVICES[@]}" >/dev/null 2>&1 || true
}

migrate() {
  log "Running alembic upgrade head"
  compose run --rm --no-deps geoint-api alembic upgrade head
}

seed() {
  if [[ ! -f "$SEED_SQL" ]]; then
    log "No seed file at $SEED_SQL — skipping"
    return 0
  fi

  local db="${POSTGRES_DB:-geoint}"
  log "Seeding source_jobs with tenant-scoped idempotency"
  compose exec -T postgres psql \
    -v ON_ERROR_STOP=1 \
    -U "$POSTGRES_USER" \
    -d "$db" \
    < "$SEED_SQL"
}

cmd_up() {
  preflight_secrets
  export APP_ENV

  log "Building stack (APP_ENV=$APP_ENV)"
  pull_dependencies
  compose build

  # Old application code must not write while the new schema is being applied.
  quiesce_apps
  start_dependencies
  migrate
  seed

  log "Starting application services after schema migration"
  compose up -d \
    --scale geoint-worker="${GEOINT_WORKER_REPLICAS:-2}" \
    geoint-api \
    geoint-web \
    geoint-scheduler \
    geoint-worker \
    geoint-outbox \
    geoint-alert-notifier

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
  curl -fsS "$HEALTH_URL"
  echo
}

cmd_remote_up() {
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

  up          preflight → build → quiesce → dependencies → migrate → seed → app → readiness
  migrate     alembic upgrade head only
  seed        apply seed_source_jobs.sql
  down        compose down
  status      compose ps + readiness
  remote-up   SSH to DEPLOY_HOST and run production deploy

Environment:
  GEOINT_ENV_FILE   path to application env
  POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB
  MINIO_ROOT_USER / MINIO_ROOT_PASSWORD
  APP_ENV           production|staging (default production)
  COMPOSE_FILE      default docker-compose.prod.yml
  DEPLOY_HOST / DEPLOY_USER / DEPLOY_PATH / DEPLOY_SSH_KEY
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
    -h|--help|help) usage ;;
    "") usage; exit 1 ;;
    *) die "Unknown command: $cmd" ;;
  esac
}

main "$@"
