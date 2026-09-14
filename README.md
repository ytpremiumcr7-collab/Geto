# GEOINT Platform (Geto)

Multi-tenant geospatial intelligence platform: open-source feeds → observations → map → geofences → alerts → delivery.

| | |
|--|--|
| **Status** | Pre-production |
| **Version** | See [`VERSION`](./VERSION) |
| **Stack** | FastAPI · PostGIS · NATS · MinIO · React · MapLibre |
| **CI** | Lint · unit · e2e (PostGIS) · frontend build · images |

## Repository layout

```
Geto/
├── geoint-platform/   # API, workers, migrations, ops scripts
├── geoint-web/        # Operator UI
├── CHANGELOG.md
└── VERSION
```

## Quick start (development)

**Requirements:** Docker, Python 3.12+, Node 22+

```bash
git clone git@github.com:ytpremiumcr7-collab/Geto.git && cd Geto

# Backend
cd geoint-platform
cp .env.example .env          # set JWT_SECRET (≥32 chars); never use change-me in staging/prod
docker compose up -d postgres redis nats minio
export DATABASE_URL=postgresql+asyncpg://geoint:geoint@localhost:5432/geoint
pip install --require-hashes -r requirements.lock.txt && pip install --no-deps -e .
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# Alert delivery worker (separate process)
python -m app.workers.alert_notifier

# Frontend
cd ../geoint-web
npm ci && npm run dev        # http://localhost:5173
```

## Staging

```bash
cd geoint-platform
cp .env.staging.example .env.staging
./scripts/staging_up.sh
python scripts/staging_verify.py
```

Full guide: [geoint-platform/docs/STAGING.md](geoint-platform/docs/STAGING.md)

## Documentation

| Path | Topic |
|------|--------|
| [geoint-platform/README.md](geoint-platform/README.md) | Backend architecture & workers |
| [geoint-web/README.md](geoint-web/README.md) | Frontend |
| [geoint-platform/docs/PRODUCTION.md](geoint-platform/docs/PRODUCTION.md) | Production deploy checklist |
| [geoint-platform/docs/STAGING.md](geoint-platform/docs/STAGING.md) | Staging: JWKS, ClickHouse, notifier |
| [geoint-platform/docs/SECURITY.md](geoint-platform/docs/SECURITY.md) | Auth, secrets, CORS, bootstrap |
| [geoint-platform/docs/TOPOGRAPHY.md](geoint-platform/docs/TOPOGRAPHY.md) | DEM, LOS, viewshed, quality grades |
| [geoint-platform/docs/ALERTS.md](geoint-platform/docs/ALERTS.md) | Geofence alerts & notifiers |
| [geoint-platform/docs/ANALYTICS.md](geoint-platform/docs/ANALYTICS.md) | ClickHouse product queries |
| [geoint-platform/docs/RBAC.md](geoint-platform/docs/RBAC.md) | Roles & source permissions |
| [geoint-platform/docs/INGESTION.md](geoint-platform/docs/INGESTION.md) | Sources, FIRMS proxy, tiles |
| [CHANGELOG.md](CHANGELOG.md) | Product version history |

## License

Proprietary / project-defined. Confirm with the repository owner before redistribution.
