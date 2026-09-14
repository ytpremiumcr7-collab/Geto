# Staging real — JWKS, ClickHouse, notifier health

## Objetivo

Antes de la auditoría formal de verificación, el entorno de **staging** debe demostrar:

1. **JWKS** alcanzable y con al menos una clave (`JWT_JWKS_URL`)
2. **ClickHouse** con schema + filas en `geoint.observations`
3. **Alert notifier** respondiendo `/health/live` y preferible `/health/ready`

## Arranque rápido

```bash
cd geoint-platform
cp .env.staging.example .env.staging
# Editar secretos (PG, MinIO, CH) y JWT_JWKS_URL

# Con IdP real:
#   JWT_JWKS_URL=https://idp/.../jwks.json

# Sin IdP (lab):
python scripts/dev_jwks_server.py --port 9090 &
# En .env.staging:
#   JWT_JWKS_URL=http://127.0.0.1:9090/jwks.json
#   JWT_ISSUER=http://127.0.0.1:9090
#   JWT_AUDIENCE=geoint-api
#   JWT_ALGORITHM=RS256

export GEOINT_ENV_FILE=.env.staging
./scripts/staging_up.sh

# Verificación explícita
export JWT_JWKS_URL=... CLICKHOUSE_ENABLED=true CLICKHOUSE_URL=http://127.0.0.1:8123
python scripts/staging_verify.py
```

## Compose

- `docker-compose.staging.yml` incluye prod + publica **8081** (notifier) y **8123** (CH)
- Profile `analytics` levanta ClickHouse

## Checklist post-up

| Check | Comando |
|-------|---------|
| JWKS | `curl -s "$JWT_JWKS_URL" \| jq '.keys\|length'` |
| CH ping | `curl -s "$CLICKHOUSE_URL/ping"` |
| CH data | `curl -s "$CLICKHOUSE_URL/" -d "SELECT count() FROM geoint.observations"` |
| Notifier | `curl -s http://127.0.0.1:8081/health/ready` |
| API | `curl -s http://127.0.0.1:8000/health/live` |

Cuando los tres pilares (JWKS + CH con datos + notifier health) pasen `staging_verify.py`, proceder a la **auditoría de verificación** archivo/endpoint vs docs.
