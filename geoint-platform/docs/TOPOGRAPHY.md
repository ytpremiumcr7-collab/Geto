# Topography

DEM catalog + engine (elevation, profile, slope, aspect, hillshade, LOS, viewshed).

Providers supply **rasters**; Tezcatlipoca derives products. Imagery adapters (e.g. Sentinel) are separate.

## API (prefix `/api/v1/topography`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/providers` | Provider metadata |
| GET | `/dem` | List tenant DEMs |
| POST | `/dem/register` | Register COG (`resolution_m` GSD, **required** `vertical_datum`) |
| GET | `/elevation` | Point sample |
| POST | `/profile` | Densified profile |
| POST | `/los` | Line of sight |
| POST | `/viewshed` | GDAL Wang viewshed |
| POST | `/slope` `/aspect` `/hillshade` | Derived rasters |

## LOS

- Profile densified at `sample_distance_m`, **clamped to ≤ DEM GSD**
- Optional effective-Earth refraction (`refraction_k`, default 4/3)
- Response includes `quality`: grade, H/V uncertainty, confidence, **certification disclaimer**

## Decision-support (not safety-of-life)

| Grade | Meaning |
|-------|---------|
| `exploratory` | Rough planning; higher uncertainty |
| `operational_support` | Inform operators who carry uncertainty forward |

Products are **not** ICAO/FAA certified. Clients must display `quality.certification` (UI does).

## Ops tips

- Prefer high-resolution COGs with documented vertical datum  
- Keep `sample_distance_m ≤ resolution_m`  
- Clip DEM to AOI before large viewsheds  
