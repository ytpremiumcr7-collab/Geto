# Production

## Checklist

1. `APP_ENV=production`
2. OIDC: `JWT_ALGORITHM=RS256`, `JWT_JWKS_URL`, `JWT_ISSUER`, `JWT_AUDIENCE`
3. Strong DB, MinIO, Redis credentials (no placeholders)
4. `CORS_ORIGINS` = explicit HTTPS origins
5. `AUTH_DISABLED=false`
6. Run migrations: `alembic upgrade head`
7. Processes: API · `alert_notifier` · scheduler/source workers as needed
8. Health: `GET /health/live`, `GET /health/ready` (inspect `errors[]`)
9. Notifier: `GET :8081/health/ready`

## Deploy

```bash
export GEOINT_ENV_FILE=/path/to/prod.env
./scripts/deploy.sh          # or compose prod
docker compose -f docker-compose.prod.yml up -d
```

Optional analytics profile:

```bash
docker compose -f docker-compose.prod.yml --profile analytics up -d clickhouse
CLICKHOUSE_ENABLED=true python scripts/clickhouse_bootstrap.py
```

## Feature flags

| Variable | Default | Notes |
|----------|---------|--------|
| `CLICKHOUSE_ENABLED` | false | Product analytics API |
| `AUTH_DISABLED` | false | Forbidden in staging/prod |
| `ALLOW_HS256_IN_PRODUCTION` | false | Break-glass only |
