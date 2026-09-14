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
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# Alert delivery worker (separate process)
python -m app.workers.alert_notifier

# Frontend
cd ../geoint-web
npm ci && npm run dev        # http://localhost:5173
```

## Staging

Use the staging pack before any formal verification audit:

```bash
cd geoint-platform
cp .env.staging.example .env.staging   # JWKS, secrets, ClickHouse
./scripts/staging_up.sh
python scripts/staging_verify.py       # JWKS + CH data + notifier health
```

Details: [`geoint-platform/docs/STAGING.md`](geoint-platform/docs/STAGING.md)

## Documentation

| Document | Topic |
|----------|--------|
| [geoint-platform/README.md](geoint-platform/README.md) | Backend architecture & workers |
| [geoint-web/README.md](geoint-web/README.md) | Frontend |
| [docs/PRODUCTION.md](geoint-platform/docs/PRODUCTION.md) | Production deploy checklist |
| [docs/STAGING.md](geoint-platform/docs/STAGING.md) | Staging: JWKS, ClickHouse, notifier |
| [docs/SECURITY.md](geoint-platform/docs/SECURITY.md) | Auth, secrets, CORS, bootstrap |
| [docs/TOPOGRAPHY.md](geoint-platform/docs/TOPOGRAPHY.md) | DEM, LOS, viewshed, quality grades |
| [docs/ALERTS.md](geoint-platform/docs/ALERTS.md) | Geofence alerts & notifiers |
| [docs/ANALYTICS.md](geoint-platform/docs/ANALYTICS.md) | ClickHouse product queries |
| [docs/RBAC.md](geoint-platform/docs/RBAC.md) | Roles & source permissions |
| [docs/INGESTION.md](geoint-platform/docs/INGESTION.md) | Sources, FIRMS proxy, tiles |
| [CHANGELOG.md](CHANGELOG.md) | Product version history |

## License

Proprietary / project-defined. Confirm with the repository owner before redistribution.
