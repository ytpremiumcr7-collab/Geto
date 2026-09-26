#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/docker-compose.prod.yml}"
BACKUP_ROOT="${BACKUP_ROOT:-$ROOT/.backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="${1:-$BACKUP_ROOT/$STAMP}"
DB="${POSTGRES_DB:-geoint}"
BUCKETS="${MINIO_BACKUP_BUCKETS:-${MINIO_BUCKET_RAW:-geoint-raw}}"
APP_SERVICES=(geoint-api geoint-web geoint-scheduler geoint-worker geoint-outbox geoint-alert-notifier)

compose() { docker compose -f "$COMPOSE_FILE" "$@"; }
need() { [[ -n "${!1:-}" ]] || { echo "missing required env: $1" >&2; exit 1; }; }

need POSTGRES_USER
need POSTGRES_PASSWORD
need MINIO_ROOT_USER
need MINIO_ROOT_PASSWORD
mkdir -p "$DEST/minio"

restart=0
restart_apps() {
  if [[ "$restart" == "1" ]]; then
    compose up -d "${APP_SERVICES[@]}" >/dev/null || true
  fi
}
trap restart_apps EXIT

# Quiesce all writers before taking the DB snapshot. With ingestion stopped,
# taking Postgres first and MinIO second cannot create DB references to objects
# absent from the object backup.
compose stop "${APP_SERVICES[@]}" >/dev/null 2>&1 || true
restart=1
compose up -d postgres minio

echo "[backup] PostgreSQL -> $DEST/postgres.dump"
compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$DB" -Fc > "$DEST/postgres.dump"

echo "[backup] MinIO buckets ($BUCKETS) -> $DEST/minio"
docker compose -f "$COMPOSE_FILE" --profile ops run --rm \
  -e MINIO_BACKUP_BUCKETS="$BUCKETS" \
  -v "$DEST/minio:/backup" \
  minio-mc '
    set -eu
    mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
    oldifs="$IFS"; IFS=","
    for bucket in $MINIO_BACKUP_BUCKETS; do
      bucket="$(echo "$bucket" | xargs)"
      [ -n "$bucket" ] || continue
      mc stat "local/$bucket" >/dev/null
      mkdir -p "/backup/$bucket"
      mc mirror --overwrite "local/$bucket" "/backup/$bucket"
    done
    IFS="$oldifs"
  '

(
  cd "$DEST"
  find postgres.dump minio -type f -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS
)

cat > "$DEST/MANIFEST" <<EOF
created_at_utc=$STAMP
database=$DB
minio_buckets=$BUCKETS
git_commit=$(git -C "$ROOT/.." rev-parse HEAD 2>/dev/null || printf unknown)
format=geto-dr-v1
EOF

echo "[backup] verifying checksums"
bash "$ROOT/scripts/verify_backup.sh" "$DEST"
echo "[backup] complete: $DEST"
