# GEOINT Platform — cierre producción (v2.1)

## Cubierto en este cierre

| # | Ítem | Estado |
|---|------|--------|
| 1 | Auth JWT + API key + RBAC | Sí (`app/auth`) |
| 2 | Secretos / compose prod | Sí (`docker-compose.prod.yml`, sin passwords en imagen) |
| 3 | Migraciones | 0001→0002→0003 outbox |
| 4 | Outbox transaccional | Sí (`app/outbox` + enqueue en dispatcher) |
| 5 | Circuit breaker por fuente | Sí (`app/resilience`) |
| 9 | Shutdown graceful | SIGTERM en scheduler/worker |
| 10 | Métricas Prometheus | `/metrics` (flag) |
| 11 | Deploy prod compose | `docker-compose.prod.yml` |

## Pendiente (sprints siguientes)

- RLS PostgreSQL multi-tenant completo
- Geofencing ST_DWithin en pipeline
- API admin DLQ / reprocess
- Retención automática (jobs de purge)
- WebSocket multi-instancia vía NATS
- OIDC/RS256 en lugar de HS256 bootstrap

## Arranque staging

```bash
cp .env.example .env.prod
# Editar: JWT_SECRET, POSTGRES_*, MINIO_*, OPENSKY_*, FIRMS_*
# AUTH_DISABLED=false

docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
docker compose -f docker-compose.prod.yml exec geoint-api alembic upgrade head
# seed jobs
docker compose -f docker-compose.prod.yml exec postgres \
  psql -U $POSTGRES_USER -d geoint -f /path/seed_source_jobs.sql
```

## Token de prueba (solo si bootstrap o development)

```bash
curl -s -X POST http://localhost:8000/api/v1/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"ops","tenant_id":"default","roles":["admin"],"bootstrap_secret":"..."}'
```

## Checklist pre-prod

- [ ] JWT_SECRET >= 32 bytes aleatorios
- [ ] AUTH_DISABLED=false
- [ ] Passwords Postgres/MinIO no por defecto
- [ ] alembic upgrade head OK
- [ ] seed source_jobs
- [ ] /health/ready ok
- [ ] 1 fuente e2e (usgs o celestrak) sin credenciales
- [ ] /api/v1/sources con Bearer → 200; sin auth → 401

## Sprint 2–3 añadido (RLS / Geofence / Retention / DLQ)

- Migración `0004_rls_geofence`: tenant_id, RLS, geofences, geofence_state, dlq_messages
- `SET LOCAL app.tenant_id` vía `app.db.tenant.set_tenant`
- Geofencing enter/exit + outbox de eventos
- API `/api/v1/geofences` y `/api/v1/admin/dlq`
- Purge: `python -m app.retention.purge`

Tras desplegar: `alembic upgrade head` (hasta 0004).

## Bloque drop-zone + WebSocket

### MinIO drop zone
1. Sube GeoJSON a `s3://geoint-raw/incoming/archivo.geojson`
2. Job `minio_dropzone` lista, normaliza, mueve a `processed/` o `failed/`
3. Ejemplo: `samples/dropzone-example.geojson`

```bash
mc cp samples/dropzone-example.geojson local/geoint-raw/incoming/
```

### WebSocket multi-instancia
- Cliente: `ws://host/ws/events?token=<JWT>`
- `tenant_id` sale del JWT (no del query)
- Cada API se suscribe a `geoint.event.>` y reenvía a sockets locales

## OpenSky encapsulado (GOODMODE_ONLY)

- Lectura de datos: permiso `geoint.source.opensky.read` (rol `goodmode`)
- Admin: puede health/config (`geoint.source.opensky.admin`), **no** lee datos por defecto
- Operator: no ve OpenSky como available
- Ingestión worker: requiere `OPENSKY_INGESTION_ENABLED=true`
- `GET /api/v1/sources` filtra/enriquece por política (backend, no solo UI)
- `GET /api/v1/observations?source_id=opensky` → 403 sin permiso


## ADS-B local (readsb) + AIS archivo

### readsb_local
- Fuente **internal**, commercial_allowed, sin dependencia de OpenSky
- Path: `READSB_AIRCRAFT_JSON_PATH` (default `/run/readsb/aircraft.json`)
- Sample: `samples/aircraft.json`
- Job seed cada 2s (ajustar a hardware)

### ais_file
- CSV o GeoJSON (MarineCadastre / AccessAIS exports)
- Path: `AIS_FILE_PATH` o `config.path` del job
- Sample: `samples/ais-sample.csv`

AircraftObservation puede venir de `opensky` (goodmode), `readsb_local` o histórico;
el engine no depende de OpenSky.

## MarineCadastre batch / OSM ETL / JPL Horizons

```bash
# Validar + insertar CSV real
python -m scripts.ingest_marinecadastre /data/ais/export.csv --tenant default
python -m scripts.ingest_marinecadastre /data/ais/export.csv --dry-run

# OSM → PostGIS (AOI pequeño; respetar límites Overpass)
python -m app.osm.etl --west -99.2 --south 19.3 --east -99.0 --north 19.5

# Migración osm_features
alembic upgrade head   # incluye 0005_osm

# Tiles: ver docs/TILES.md (Martin / pg_tileserv)
```

NEXRAD/GOES, Timescale y MapLibre: pendientes a propósito.


## NEXRAD / GOES / Analytics

- `nexrad`: índice S3 Level II (AWS Open Data), metadatos de volumen → observations
- `goes`: índice ABI GOES-16/18 en S3 público
- ClickHouse: `CLICKHOUSE_ENABLED=true` + compose service `clickhouse`
- Timescale: helper `app/analytics/timescale.py` (requiere imagen con extensión)

PostGIS sigue siendo la fuente de verdad operacional; ClickHouse es analítica.
