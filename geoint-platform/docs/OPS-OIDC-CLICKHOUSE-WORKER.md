# Ops: OIDC / ClickHouse / Alert worker health

## 1. JWT_JWKS_URL → IdP

Production (`APP_ENV=production|staging`) **requires** OIDC JWKS (see `security_bootstrap`).

```bash
# .env / GEOINT_ENV_FILE
APP_ENV=production
AUTH_DISABLED=false
JWT_ALGORITHM=RS256
JWT_JWKS_URL=https://<idp>/.well-known/jwks.json
# or Keycloak: https://keycloak.example/realms/<realm>/protocol/openid-connect/certs
JWT_ISSUER=https://<idp>/realms/<realm>
JWT_AUDIENCE=geoint-api
JWT_TENANT_CLAIM=tenant_id
```

Break-glass HS256 only with `ALLOW_HS256_IN_PRODUCTION=true` + strong `JWT_SECRET` (not recommended).

Discovery helper:

```bash
python scripts/oidc_check.py --issuer https://<idp>/realms/<realm>
```

## 2. ClickHouse enabled + tables

```bash
# compose profile
export CLICKHOUSE_PASSWORD=...   # strong
docker compose -f docker-compose.prod.yml --profile analytics up -d clickhouse

# or any CH endpoint
export CLICKHOUSE_URL=http://localhost:8123
export CLICKHOUSE_ENABLED=true
python scripts/clickhouse_bootstrap.py
# optional seed
CLICKHOUSE_SEED=1 python scripts/clickhouse_bootstrap.py
```

API:

```bash
CLICKHOUSE_ENABLED=true
CLICKHOUSE_URL=http://clickhouse:8123
```

Templates: `/api/v1/analytics/templates|query/{id}`.

Populate `geoint.observations` via your ETL / outbox consumer (schema in `deploy/clickhouse/init.sql`).

## 3. Alert notifier health (orchestrator)

Worker listens on **8081**:

| Path | Meaning |
|------|---------|
| `GET /health/live` | process up |
| `GET /health/ready` | tick reciente + sin error duro |

Docker Compose `geoint-alert-notifier` includes `healthcheck` against `/health/ready`.

Kubernetes example:

```yaml
livenessProbe:
  httpGet: { path: /health/live, port: 8081 }
readinessProbe:
  httpGet: { path: /health/ready, port: 8081 }
  periodSeconds: 10
```

Heartbeat file: `/tmp/geoint_alert_notifier_heartbeat` (JSON).
