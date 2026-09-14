# GEOINT Platform — producción

## P0 enforced in code

1. **CORS / edge** — `CORS_ORIGINS` obligatorio en prod; ver `docs/EDGE-AND-SECRETS.md`
2. **OIDC/JWKS** — obligatorio si `APP_ENV=production|staging` (`app/core/security_bootstrap.py`)
3. **Deploy real** — `scripts/deploy.sh` (migrate + seed + health); CI SSH cuando hay secrets
4. **Secretos** — compose prod sin defaults; preflight rechaza `change-me`

## Checklist pre-arranque

- [ ] Secret manager materializa env file (mode 0600)
- [ ] `APP_ENV=production` (o `staging`)
- [ ] `AUTH_DISABLED=false`
- [ ] `JWT_JWKS_URL=https://…` + `JWT_ALGORITHM=RS256`
- [ ] `CORS_ORIGINS=https://app…` (sin `*`)
- [ ] `POSTGRES_PASSWORD` / `MINIO_ROOT_*` fuertes
- [ ] TLS en reverse proxy delante de `:8000`

## Arranque

```bash
cd geoint-platform
export GEOINT_ENV_FILE=/run/secrets/geoint.env
export POSTGRES_USER=geoint POSTGRES_PASSWORD='…'
export MINIO_ROOT_USER='…' MINIO_ROOT_PASSWORD='…'
export APP_ENV=production
./scripts/deploy.sh up
```

## CI staging

Secrets del Environment `staging`: `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, opcional `DEPLOY_PATH`.
Sin ellos el job omite el deploy (no finge éxito).
