# Edge, CORS, OIDC y secretos (P0)

## Arranque fail-fast

`app.core.security_bootstrap.validate_settings` corre al iniciar **API, scheduler, worker y outbox**.

Si `APP_ENV` es `production`, `prod` o `staging`, el proceso **no arranca** cuando:

| Condición | Motivo |
|-----------|--------|
| `AUTH_DISABLED=true` | Auth apagada |
| Falta `JWT_JWKS_URL` | OIDC obligatorio |
| `JWT_ALGORITHM=HS256` sin `ALLOW_HS256_IN_PRODUCTION=true` | Solo OIDC/RS* en prod |
| `DATABASE_URL` con `change-me` / password débil conocida | Secretos inyectados |
| MinIO keys default / vacías | Secretos inyectados |
| `CORS_ORIGINS` vacío o `*` | Edge explícito |
| Origen CORS no-`https://` (salvo lab con flag) | TLS en edge |
| `RATE_LIMIT_FAIL_OPEN=true` | Disponibilidad ≠ seguridad |

## CORS

| Entorno | Comportamiento |
|---------|----------------|
| development / test | `CORS_ORIGINS` vacío → `allow_origins=["*"]` |
| production / staging | Solo orígenes listados; sin `*` |

Ejemplo:

```bash
CORS_ORIGINS=https://app.example.com,https://ops.example.com
TRUSTED_HOSTS=api.example.com,localhost
```

Reverse proxy (recomendado):

```nginx
# TLS termina en el proxy; API solo red interna
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
add_header X-Content-Type-Options nosniff always;
proxy_set_header Host $host;
proxy_set_header X-Forwarded-Proto https;
```

## OIDC / JWKS

```bash
APP_ENV=production
JWT_ALGORITHM=RS256
JWT_JWKS_URL=https://login.example.com/.well-known/jwks.json
JWT_ISSUER=https://login.example.com/
JWT_AUDIENCE=geoint-api
JWT_TENANT_CLAIM=tenant_id
```

Break-glass (emergencia, temporal):

```bash
ALLOW_HS256_IN_PRODUCTION=true
JWT_ALGORITHM=HS256
JWT_SECRET=<openssl rand -hex 32>
JWT_JWKS_URL=https://still-required.example/jwks.json
```

## Secretos — nunca en git

| Secreto | Origen |
|---------|--------|
| `POSTGRES_PASSWORD` | Secret manager → env del host / systemd / K8s Secret |
| `MINIO_ROOT_PASSWORD` | Idem |
| Contenido de `GEOINT_ENV_FILE` | Archivo materializado en `/run/secrets/geoint.env` (mode 0600) |
| API keys | Solo hashes en `API_KEY_HASHES` |

```bash
# Ejemplo materialización (AWS SSM)
aws ssm get-parameter --name /geoint/prod/env --with-decryption \
  --query Parameter.Value --output text > /run/secrets/geoint.env
chmod 600 /run/secrets/geoint.env
```

`docker-compose.prod.yml` usa `${VAR:?message}`: **falla si falta la variable**. No hay defaults `change-me`.

## Deploy único

```bash
export GEOINT_ENV_FILE=/run/secrets/geoint.env
export POSTGRES_USER=... POSTGRES_PASSWORD=... 
export MINIO_ROOT_USER=... MINIO_ROOT_PASSWORD=...
./scripts/deploy.sh up
# → preflight → build → up → health → alembic upgrade head → seed
```

CI (`deploy-staging`): si existen `DEPLOY_HOST` + `DEPLOY_SSH_KEY`, ejecuta `remote-up`; si no, el job se omite con mensaje claro (no un `echo` falso de éxito).
