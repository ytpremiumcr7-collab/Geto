#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv 2>/dev/null || python3 -m virtualenv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
# The lockfile pins application dependencies; avoid mutating them via an implicit upgrade.
python -m pip --version
if [[ -f requirements.lock.txt ]]; then
  python -m pip install -r requirements.lock.txt
fi
python -m pip install -e ".[dev]"
if command -v gdal-config >/dev/null 2>&1; then
  pip install "gdal==$(gdal-config --version)" || true
fi
if [[ ! -f .env ]]; then
  cp .env.example .env
  if command -v openssl >/dev/null; then
    HEX=$(openssl rand -hex 32)
    # replace empty JWT_SECRET line if present
    grep -q '^JWT_SECRET=' .env && sed -i.bak "s/^JWT_SECRET=.*/JWT_SECRET=${HEX}/" .env || echo "JWT_SECRET=${HEX}" >> .env
  fi
  echo "Created .env with strong JWT_SECRET"
fi
echo "venv OK. Run: alembic upgrade head && pytest tests/unit/test_auth_security.py -v"
