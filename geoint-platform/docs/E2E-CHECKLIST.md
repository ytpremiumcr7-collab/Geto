# Checklist e2e — GEOINT Platform

## 0. Requisitos
- Docker + Docker Compose
- Python 3.11+
- Node 18+
- (Opcional) readsb / archivo AIS real

## 1. Infra
```bash
cd geoint-platform
cp .env.example .env
# Editar: JWT_SECRET (largo), POSTGRES_PASSWORD, no dejes change-me en prod
docker compose up -d
# Esperar healthy: postgres, nats, minio
docker compose ps
```

## 2. Migraciones + seed
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
psql $DATABASE_URL -f seed_source_jobs.sql
# OpenSky queda enabled=false a propósito
```

## 3. API
```bash
export AUTH_DISABLED=false   # usar JWT real
# APP_ENV=development permite emitir tokens sin bootstrap
uvicorn app.main:app --host 0.0.0.0 --port 8000
curl -s http://127.0.0.1:8000/health/live
curl -s http://127.0.0.1:8000/health/ready
```

## 4. Token
```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"ops1","tenant_id":"default","roles":["operator"]}'
# Guardar access_token → export TOKEN=...
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/v1/sources | head
```

## 5. Workers (mínimo 1 fuente)
```bash
# Terminal A — scheduler
python -m app.workers.job_scheduler
# Terminal B — source worker
python -m app.workers.source_worker
# Opcional: outbox dispatcher
python -m app.ingestion.dispatcher   # si aplica entrypoint del proyecto
```
Sin receptor: prueba USGS (sin credenciales) o:
```bash
python -m scripts.ingest_marinecadastre samples/ais-sample.csv --dry-run
# Con DB up (path real):
python -m scripts.ingest_marinecadastre /data/ais/export.csv
```
Readsb:
```bash
export READSB_AIRCRAFT_JSON_PATH=/ruta/a/aircraft.json
# job readsb_local cada 2s
```

## 6. Verificar datos
```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  'http://127.0.0.1:8000/api/v1/observations?limit=5'
# Debe traer lon/lat si hay geometry
```

## 7. Frontend
```bash
cd ../geoint-web
npm install
npm run dev
# http://localhost:5173
# Login: user_id + tenant default + rol operator
# Mapa: markers si hay obs; Geofence: dibujar + doble-click
# Filtros temporales en barra
```

## 8. Criterios de éxito
- [ ] `/health/ready` con postgres true (nats/minio según compose)
- [ ] Token JWT y `/api/v1/sources` 200
- [ ] Al menos 1 observation con lon/lat
- [ ] UI muestra marker
- [ ] Geofence creado aparece tras refresh
- [ ] WS LIVE o OFF sin tumbar la UI
- [ ] OpenSky no available para operator; sí intent con goodmode

## 9. Fallos frecuentes
| Síntoma | Causa |
|---------|--------|
| ready degraded | NATS/MinIO no up |
| 401 en API | Token / JWT_SECRET distinto |
| Mapa vacío | Sin ingestión / sin lon lat |
| 403 opensky | Política goodmode_only |
| Geofence 403 | Rol sin operator/admin |
