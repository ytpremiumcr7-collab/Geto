# geoint-platform

Backend: FastAPI API, ingestion workers, PostGIS, alert delivery, topography engine.

## Architecture (summary)

```
Clients ──► FastAPI (REST + WebSocket)
               ├── PostgreSQL / PostGIS  (tenant RLS)
               ├── NATS JetStream        (jobs / events)
               ├── MinIO                 (COGs / objects)
               └── ClickHouse (optional) (analytics)

Workers: job_scheduler · source_worker · alert_notifier · outbox
```

## Dependencies (hashed lock)

```bash
python -m pip install --upgrade pip
pip install --require-hashes -r requirements.lock.txt
pip install --no-deps -e .
```

Regenerate lock (maintainers):

```bash
# edit requirements.in (exact pins)
python scripts/generate_hashed_lock.py
```

## Run

```bash
cp .env.example .env
docker compose up -d postgres redis nats minio
alembic upgrade head
uvicorn app.main:app --reload --port 8000
python -m app.workers.alert_notifier
```

Production compose: `docker-compose.prod.yml`  
Staging: `docker-compose.staging.yml` + `docs/STAGING.md`

## Tests

```bash
pytest tests/unit -q
python scripts/e2e_ci_product_flow.py   # needs PostGIS + migrations
python scripts/staging_verify.py        # JWKS + CH + notifier
```

## Docs

See `docs/` and the [root README](../README.md).
