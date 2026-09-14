# Staging

Prove three pillars before a formal verification audit:

1. **JWKS** reachable with ≥1 key  
2. **ClickHouse** schema + rows in `geoint.observations`  
3. **Alert notifier** `/health/live` and `/health/ready`

## Start

```bash
cp .env.staging.example .env.staging
# Set secrets + JWT_JWKS_URL (real IdP or scripts/dev_jwks_server.py)

export GEOINT_ENV_FILE=.env.staging
./scripts/staging_up.sh
python scripts/staging_verify.py
```

Compose: `docker-compose.staging.yml` (publishes notifier **8081** and ClickHouse **8123**).

## Checks

```bash
curl -s "$JWT_JWKS_URL" | jq '.keys | length'
curl -s "$CLICKHOUSE_URL/ping"
curl -s "$CLICKHOUSE_URL/" -d "SELECT count() FROM geoint.observations"
curl -s http://127.0.0.1:8081/health/ready
curl -s http://127.0.0.1:8000/health/ready | jq '.status, .errors'
```
