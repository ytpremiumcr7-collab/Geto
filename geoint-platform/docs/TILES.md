# Vector tiles sobre osm_features (PostGIS)

El ETL materializa OSM en `osm_features`. Los tiles **no** se generan en Python en cada request.

## Opción recomendada: Martin

```bash
# ejemplo
martin --connection-string "postgres://geoint:xxx@localhost:5432/geoint"
```

Configurar table source `osm_features` (geometry 4326).

## Opción: pg_tileserv

```bash
pg_tileserv
# auto-descubre tablas con geometry
```

## Frontend (después)

MapLibre GL JS consumiendo:

```
https://tiles.example.com/osm_features/{z}/{x}/{y}
```

Backend GEOINT sigue siendo la fuente de observations/tracks/events; el mapa base/infra es capa cartográfica local.
