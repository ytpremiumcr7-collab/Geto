# ClickHouse como feature de producto

## API

| Endpoint | Descripción |
|----------|-------------|
| `GET /api/v1/analytics/status` | enabled + ping |
| `GET /api/v1/analytics/templates` | plantillas allowlisted |
| `GET /api/v1/analytics/query/{template_id}` | ejecuta plantilla con `tenant_id` del principal |

## Templates

- `observations_by_source_24h`
- `observations_per_hour_24h`
- `entity_types_24h`
- `top_entities_24h`

SQL arbitrario **no** está expuesto. Parámetro `tenant` inyectado por el servidor.

## Config

```bash
CLICKHOUSE_ENABLED=true
CLICKHOUSE_URL=http://clickhouse:8123
```

Sin enable, los endpoints responden `enabled: false` y `rows: []` (no error duro).
