# Ingestion & layers

## Sources

Adapters under `app/sources/` (OpenSky, CelesTrak, USGS, FIRMS, aviation weather, AIS, readsb, dropzone, …).

Jobs: scheduler → JetStream → `source_worker` → normalize → PostGIS (tenant-scoped).

## FIRMS tiles

Browser never receives `FIRMS_MAP_KEY`.

1. `GET /api/v1/sources/nasa_firms/wms` → proxy `tile_url` + HMAC ticket  
2. `GET /api/v1/sources/nasa_firms/wms/proxy` → server fetches NASA WMS  

## Map tiles (frontend)

Base maps and DEM (e.g. Carto, Terrarium, GIBS) are configured in the web app; they are not the topography engine.
