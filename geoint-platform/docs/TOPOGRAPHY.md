# Topography Engine — Tezcatlipoca MVP

## Qué es

Motor topográfico real sobre la base existente (PostGIS + MinIO + GDAL + MapLibre).

**No** reutiliza el adapter `copernicus` (ese es Sentinel-2 imagery).

## Arquitectura

```
MapLibre (AWS Terrarium)     ← visualización 3D / hillshade cliente
         │
FastAPI /api/v1/topography
         │
TopographyService
    ├── AwsTerrariumProvider   (punto global, sin key)
    ├── LocalRasterProvider    (COG en MinIO)
    ├── InegiProvider          (ingest-first)
    └── CopernicusDemProvider  (ingest-first, CDSE)
         │
TopographyEngine (GDAL + RasterIO + NumPy)
    elevación | perfil | slope | aspect | hillshade | LOS | viewshed
         │
MinIO: dem/ + derived/
PostgreSQL: dem_assets (catálogo + RLS)
```

## Endpoints

| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/api/v1/topography/providers` | Info de providers + guías INEGI/Copernicus |
| GET | `/api/v1/topography/dem` | Listar DEMs del tenant |
| POST | `/api/v1/topography/dem/register` | Registrar COG ya subido a MinIO |
| GET | `/api/v1/topography/elevation?lat=&lon=` | Elevación puntual (DEM local o Terrarium) |
| POST | `/api/v1/topography/profile` | Perfil A→B densificado |
| POST | `/api/v1/topography/slope` | Raster de pendiente → MinIO derived/ |
| POST | `/api/v1/topography/aspect` | Orientación |
| POST | `/api/v1/topography/hillshade` | Hillshade analítico |
| POST | `/api/v1/topography/los` | Línea de vista A→B |
| POST | `/api/v1/topography/viewshed` | Cuenca visual (GDAL ViewshedGenerate) |

Todos requieren auth (JWT / API key) excepto si `AUTH_DISABLED=true`.

## Flujo INEGI (México)

1. Descargar MDE/CEM desde https://www.inegi.org.mx/app/geo2/elevacionesmex/
2. `mc cp archivo.tif local/geoint-raw/dem/mexico/inegi/`
3. `POST /api/v1/topography/dem/register` con bbox, resolución, `file_uri=s3://geoint-raw/dem/mexico/inegi/...`
4. Usar `dem_id` en elevation/profile/los/viewshed

## Flujo Copernicus DEM

1. Registro CDSE + S3 credentials
2. Descargar tiles GLO-30 del AOI
3. Subir COG a MinIO `dem/global/copernicus/`
4. Registrar igual que INEGI

## Respuesta trazable (ejemplo)

```json
{
  "elevation_m": 2240.5,
  "source": "inegi",
  "provider": "inegi",
  "product_name": "MDE terreno 1.5m F13D79C3",
  "resolution_m": 1.5,
  "crs": "EPSG:4326",
  "vertical_datum": "NAVD88 / local",
  "dem_id": "…",
  "sampled_at": "2026-…"
}
```

## Migración

```bash
alembic upgrade head   # incluye 0008_dem_assets
```

## Tests

```bash
pytest tests/unit/test_topography_engine.py -v
```

## Dependencias nuevas

- `rasterio>=1.4`
- `pillow>=10` (decode Terrarium opcional; hay fallback zlib)

GDAL ya estaba en el Dockerfile (`gdal-bin`, `libgdal-dev`).

## Lo que NO hace este MVP

- Descarga automática masiva de todo México / todo el planeta
- Google Elevation / Mapbox Terrain / Open-Elevation público
- PostGIS Raster (innecesario para MVP)
- ClickHouse para topografía

## Ronda 2

- UI `TopographyPanel` en Dashboard (elevación / perfil / LOS)
- MapView: click-to-pick, línea de perfil, línea LOS + punto de obstrucción
- `scripts/ingest_inegi_cog.py` — sube COG a MinIO y registra en `dem_assets`
- `clip_bbox` antes de slope/aspect/hillshade (rasterio window; GDAL Warp si CRS proyectado)
- Fix: routes usan `get_db` (antes `get_session` inexistente)
- Evidencia tests: 10 passed, 2 skipped; Terrarium live CDMX 2235 m

## Precisión LOS / Viewshed

Ver [TOPOGRAPHY-LOS-VIEWSHED.md](./TOPOGRAPHY-LOS-VIEWSHED.md).

