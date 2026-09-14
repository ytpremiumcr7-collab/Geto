# Evidencia Ronda 3 — build real + E2E topography

Fecha: 2026-09-12

## 1. Frontend `npm run build` — VERIFICADO

```
tsc -b && vite build  → EXIT 0
✓ 49 modules transformed
dist/index.html                 0.72 kB
dist/assets/index-*.css        76.14 kB │ gzip 11.74 kB
dist/assets/index-*.js        998.12 kB │ gzip 281.49 kB
✓ built in ~4.3s
```

Fix aplicado: `attributionControl: { compact: true }` (MapLibre types).

## 2. E2E topography (`scripts/e2e_topography.py`) — VERIFICADO 10/10

COG de prueba: `samples/synthetic_cdmx_dem.tif` (200×200, EPSG:4326, ~127 KB)

| Check | Resultado |
|-------|-----------|
| dem_file_exists | PASS |
| sample_elevation | PASS elev≈2288.03 m |
| profile_points | PASS n=476 |
| profile_has_elev | PASS 476 samples |
| clip_bbox | PASS |
| clip_sample | PASS elev≈2177.63 m |
| LOS | PASS keys visible=False |
| terrarium_decode | PASS |
| terrarium_live_cdmx | PASS **2235.0 m** (HTTP real S3) |
| minio_mock_roundtrip | PASS |

## 3. Unit tests — VERIFICADO 10 passed, 2 skipped

Engine, clip, object_store mock, routes get_db, ingest script.

## 4. Slope overlay — VERIFICADO (engine + API + UI)

- `engine.slope_preview_png` → PNG colorizado (numpy gradient, sin GDAL)
- `GET /api/v1/topography/slope-preview?dem_id=` → PNG + headers X-Bounds-* / X-Slope-*
- MapLibre `image` source + raster layer
- Botón "Overlay slope" en TopographyPanel (requiere dem_id registrado)

Prueba local engine:
```
slope_min≈0.02  slope_max≈2.13  slope_mean≈1.30  png≈2.7 KB
```

## 5. Docker Compose E2E completo — NO VERIFICADO en este entorno

`docker` / `docker-compose` **no están disponibles** en el sandbox de build.
Por tanto no se levantó postgres+minio+api en contenedores aquí.

### Cómo correrlo en tu máquina (criterio de éxito)

```bash
cd geoint-platform
cp .env.example .env
# AUTH_DISABLED=true solo para smoke local; prod=false
docker compose up -d
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000

# registrar COG sintético
python -m scripts.ingest_inegi_cog samples/synthetic_cdmx_dem.tif \
  --provider local --product "synthetic CDMX" --resolution 220 --tenant default

# E2E motor
PYTHONPATH=. python scripts/e2e_topography.py

# API smoke
curl -s http://127.0.0.1:8000/health/live
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"ops","tenant_id":"default","roles":["operator"]}' | jq -r .access_token)
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8000/api/v1/topography/elevation?lat=19.43&lon=-99.13"

cd ../geoint-web && npm run dev
# Panel TOPOGRAFÍA → Overlay slope (con DEM registrado)
```

## Clasificación

| Ítem | Estado |
|------|--------|
| npm run build | VERIFICADO |
| E2E motor + COG sintético | VERIFICADO |
| Terrarium live | VERIFICADO |
| Slope PNG + overlay código | VERIFICADO (engine); UI integrado |
| Docker compose full stack | NO VERIFICADO (sin docker en sandbox) |
| MinIO real (no mock) | NO VERIFICADO aquí |
