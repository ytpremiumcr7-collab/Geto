#!/usr/bin/env bash
set -euo pipefail

DIR="${1:?usage: verify_backup.sh <backup-directory>}"
[[ -f "$DIR/MANIFEST" ]] || { echo "missing MANIFEST" >&2; exit 1; }
[[ -f "$DIR/SHA256SUMS" ]] || { echo "missing SHA256SUMS" >&2; exit 1; }
[[ -s "$DIR/postgres.dump" ]] || { echo "missing/empty postgres.dump" >&2; exit 1; }
[[ -d "$DIR/minio" ]] || { echo "missing minio directory" >&2; exit 1; }

(
  cd "$DIR"
  sha256sum -c SHA256SUMS
)
echo "[verify] backup checksums OK: $DIR"
