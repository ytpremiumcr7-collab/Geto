# NASA FIRMS

## MAP_KEY
1. https://firms.modaps.eosdis.nasa.gov/api/map_key
2. Ponla **solo** en `.env` (nunca en git):

```env
FIRMS_MAP_KEY=tu_key_aqui
```

3. Activa el job:

```sql
UPDATE source_jobs SET enabled = true WHERE source_id = 'nasa_firms';
```

## Dos usos
| Modo | Qué hace |
|------|----------|
| **API CSV** (adapter `nasa_firms`) | Ingestión → PostGIS observations (hotspots como puntos) |
| **WMS** (mapa) | Capa visual tiles: `.../mapserver/wms/fires/{MAP_KEY}/` |

Capas útiles WMS: `fires_viirs_24`, `fires_modis_24`, `fires_landsat_24`, etc.

## Seguridad
Si pegaste la key en un chat o issue, **rota** la MAP_KEY en el portal FIRMS.
