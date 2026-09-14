# Analytics (ClickHouse)

Optional product feature. No arbitrary SQL from clients — allowlisted templates only.

## Config

```bash
CLICKHOUSE_ENABLED=true
CLICKHOUSE_URL=http://clickhouse:8123
python scripts/clickhouse_bootstrap.py
CLICKHOUSE_SEED=1 python scripts/clickhouse_bootstrap.py
```

Schema: `deploy/clickhouse/init.sql`

## API

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/analytics/status` | Enabled + ping |
| `GET /api/v1/analytics/templates` | Template list |
| `GET /api/v1/analytics/query/{id}` | Run template for current tenant |

`tenant_id` is always taken from the principal.
