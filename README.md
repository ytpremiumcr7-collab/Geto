# GEOINT Platform (Geto)

Multi-tenant geospatial intelligence: sources → observations → map → geofences → alerts → delivery.

**Status:** pre-production (v2.5.0). CI must be green on `main` (lint, unit, e2e PostGIS, frontend build).

## Quick start (local pre-prod)

### Prerequisites

- Docker + Docker Compose
- Node 22+, Python 3.12+
- (Optional) GDAL for topography workers

### 1. Clone and env

```bash
git clone git@github.com:ytpremiumcr7-collab/Geto.git
cd Geto/geoint-platform
cp .env.example .env
# Edit .env: JWT_SECRET (≥32 chars), DATABASE_URL, no change-me values
```

### 2. Infrastructure

```bash
docker compose up -d postgres redis nats minio
# wait for healthy
export DATABASE_URL=postgresql+asyncpg://geoint:geoint@localhost:5432/geoint
alembic upgrade head
```

### 3. API + workers

```bash
# terminal 1
uvicorn app.main:app --reload --port 8000

# terminal 2 — alert delivery (24/7 path)
python -m app.workers.alert_notifier

# terminal 3 — optional ingestion scheduler
python -m app.workers.job_scheduler
```

### 4. Frontend

```bash
cd ../geoint-web
npm ci
npm run dev
# http://localhost:5173 — login issues dev token → onboarding → map
```

### 5. Verify product path

```bash
cd ../geoint-platform
python scripts/verify_alert_notifier_flow.py   # offline
python scripts/e2e_ci_product_flow.py          # needs API+DB (or AUTH_DISABLED ASGI)
```

Flow: **login → /me permissions → sources → map → geofence enter → alert → delivery (log/webhook/SMTP)**.

## Production

- `APP_ENV=production` enforces OIDC/JWKS, strong secrets, closed CORS (`docs/EDGE-AND-SECRETS.md`, `security_bootstrap`).
- Deploy: `scripts/deploy.sh` + `docker-compose.prod.yml` (`${VAR:?required}`).
- Feature flags: `CLICKHOUSE_ENABLED`, `AUTH_DISABLED` (never true in prod).

## CI

GitHub Actions: Ruff → unit tests → **E2E PostGIS smoke + product flow** → frontend Vite build → security → docker.

## Docs

| Doc | Topic |
|-----|--------|
| `geoint-platform/docs/TOPOGRAPHY-LOS-VIEWSHED.md` | LOS/viewshed precision limits |
| `geoint-platform/docs/ALERT-NOTIFIERS.md` | Delivery channels |
| `geoint-platform/docs/RBAC-CLIENT.md` | Permissions to UI |
| `geoint-platform/docs/ANALYTICS-CLICKHOUSE.md` | Analytics templates |
| `geoint-platform/docs/PRODUCTION.md` | Prod checklist |

## DEM / LOS

Terrain products are **decision-support**, not certified flight/safety outputs. See topography docs for algorithm assumptions and DEM resolution limits.

## Staging

See [geoint-platform/docs/STAGING.md](geoint-platform/docs/STAGING.md) for JWKS + ClickHouse + notifier health before formal verification audit.

