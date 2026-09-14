# Security

## Bootstrap (fail-fast)

On process start (`APP_ENV=production|staging`), `app/core/security_bootstrap.py` refuses to run if:

- `AUTH_DISABLED=true`
- Missing or weak `JWT_SECRET` when HS256 is used
- Missing `JWT_JWKS_URL` for OIDC (required in staging/prod)
- `CORS_ORIGINS` empty or contains `*`
- Placeholder passwords in `DATABASE_URL` (`change-me`, etc.)
- `RATE_LIMIT_FAIL_OPEN=true` in staging/prod

## Auth

| Mode | When |
|------|------|
| OIDC / JWKS (`RS256`) | Staging & production |
| HS256 + strong secret | Development only (or break-glass with `ALLOW_HS256_IN_PRODUCTION`) |
| API keys | Optional; prefer hashed `api_key_hashes` |

Tenant and roles come **only** from the token or API key — never from request body.

## Multi-tenant

- `set_tenant(session, principal.tenant_id)` on DB routes
- PostgreSQL **FORCE ROW LEVEL SECURITY**
- Worker system tenant: `app.tenant_id=__system__` for cross-tenant claim only

## Secrets

- Never commit `.env` / `.env.staging`
- Inject via secret manager or env in compose (`${VAR:?required}` in prod patterns)
- FIRMS `MAP_KEY` stays on the server; tiles use a short-lived HMAC ticket + proxy

## Lab JWKS

Without an IdP, for staging lab only:

```bash
python scripts/dev_jwks_server.py --port 9090
# JWT_JWKS_URL=http://127.0.0.1:9090/jwks.json
```


## API keys

- Staging/production: **only** `API_KEY_HASHES` (plaintext `API_KEYS` rejected at bootstrap)
- Development may still use plaintext for convenience

## Trusted hosts

- Production requires `TRUSTED_HOSTS` (comma-separated)
- Metrics (`/metrics`) require auth **and** role `admin`, `metrics`, or `geoint.metrics.read` unless `METRICS_PUBLIC=true`

## MinIO

- Set `MINIO_CREATE_BUCKET=false` in staging/prod; provision buckets out-of-band


## System worker claim

RLS system policies require **both**:

- `app.tenant_id = '__system__'`
- `app.worker_mode = '1'`

Application code must call `set_system_worker(session)` (not `set_tenant(..., "__system__")`).
The process must run with `GEOINT_SYSTEM_WORKER=1` (workers only — never the public API).

## Composite tenant FKs

- `saved_layers (tenant_id, workspace_id)` → `workspaces (tenant_id, id)`
- `geofence_alert_rules (tenant_id, geofence_id)` → `geofences (tenant_id, id)`

## HttpOnly cookies

Set `AUTH_COOKIE_MODE=true`. `POST /api/v1/auth/token` sets cookie `geoint_access` (HttpOnly).
`POST /api/v1/auth/logout` clears it. SPA uses `credentials: "include"`. Bearer still works.
