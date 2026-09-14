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
