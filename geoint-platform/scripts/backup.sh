#!/usr/bin/env bash
set -euo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/docker-compose.prod.yml}"
BACKUP_ROOT="${BACKUP_ROOT:-$ROOT/.backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="${1:-$BACKUP_ROOT/$STAMP}"
DB="${POSTGRES_DB:-geoint}"
BUCKETS="${S3_BACKUP_BUCKETS:-${S3_BUCKET_RAW:-geoint-raw}}"
APP_SERVICES=(geoint-api geoint-web geoint-scheduler geoint-worker geoint-outbox geoint-alert-notifier)

compose() { docker compose -f "$COMPOSE_FILE" "$@"; }
need() { [[ -n "${!1:-}" ]] || { echo "missing required env: $1" >&2; exit 1; }; }

need POSTGRES_USER
need POSTGRES_PASSWORD
need S3_ACCESS_KEY
need S3_SECRET_KEY
mkdir -p "$DEST/s3"
if [[ "$(id -u)" == "0" ]]; then
  SNAPSHOT_UID="${BACKUP_SNAPSHOT_UID:-10001}"
  SNAPSHOT_GID="${BACKUP_SNAPSHOT_GID:-10001}"
  chown -R "$SNAPSHOT_UID:$SNAPSHOT_GID" "$DEST/s3"
  SNAPSHOT_USER="$SNAPSHOT_UID:$SNAPSHOT_GID"
else
  SNAPSHOT_USER="$(id -u):$(id -g)"
fi

RUNNING_APPS=()
while IFS= read -r service; do
  for app in "${APP_SERVICES[@]}"; do
    if [[ "$service" == "$app" ]]; then
      RUNNING_APPS+=("$service")
      break
    fi
  done
done < <(compose ps --services --filter status=running)

restart_apps() {
  local exit_code=$?
  if (( ${#RUNNING_APPS[@]} > 0 )); then
    if ! compose up -d "${RUNNING_APPS[@]}" >/dev/null; then
      echo "[backup] failed to restart previously-running application services" >&2
      [[ "$exit_code" -ne 0 ]] || exit_code=1
    fi
  fi
  return "$exit_code"
}
trap restart_apps EXIT

# Quiesce all writers before taking the DB snapshot. With ingestion stopped,
# taking Postgres first and S3 second cannot create DB references to objects
# absent from the object backup.
compose stop "${APP_SERVICES[@]}" >/dev/null 2>&1 || true
compose up -d --wait postgres object-store

echo "[backup] PostgreSQL -> $DEST/postgres.dump"
compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$DB" -Fc > "$DEST/postgres.dump"

echo "[backup] S3 buckets ($BUCKETS) -> $DEST/s3"
compose run --rm --no-deps \
  --user "$SNAPSHOT_USER" \
  -v "$DEST/s3:/backup" \
  geoint-api python scripts/s3_snapshot.py export \
    --root /backup \
    --buckets "$BUCKETS"

(
  cd "$DEST"
  find postgres.dump s3 -type f -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS
)

cat > "$DEST/MANIFEST" <<EOF
created_at_utc=$STAMP
database=$DB
s3_buckets=$BUCKETS
git_commit=$(git -C "$ROOT/.." rev-parse HEAD 2>/dev/null || printf unknown)
format=geto-dr-v1
EOF

echo "[backup] verifying checksums"
bash "$ROOT/scripts/verify_backup.sh" "$DEST"
echo "[backup] complete: $DEST"
