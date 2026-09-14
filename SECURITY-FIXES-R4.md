# R4 — Fixes de seguridad y runtime (respuesta a auditoría)

## P0 resueltos (VERIFICADO con tests)

| ID | Hallazgo | Fix |
|----|----------|-----|
| P0 | JWT aceptaba `change-me-jwt` al **decodificar** | `JWTService._decode_hs256` llama `_assert_hs256_secret_usable`; lista de secrets prohibidos + mínimo 32 bytes |
| P0 | API key rota con `compare_digest` | Comparación **siempre** sobre SHA-256 hex (64 chars) vía `hmac.compare_digest`; plaintext legacy hashea ambos lados |
| P0 | TopographyService `structlog` sin import | try/import structlog al inicio de `service.py` |
| P0 | `ingestion.py` SyntaxError (`__future__`) | `from __future__` movido al inicio del archivo; `py_compile` OK |

Tests: `tests/unit/test_auth_security.py` → **8 passed**

## P1 resueltos (código)

| ID | Fix |
|----|-----|
| Scheduler vs RLS | `set_config('app.tenant_id','__system__')` antes de `claim_due_jobs` |
| FORCE RLS dem_assets | Migración `0009_force_rls_system` — FORCE RLS + policy `__system__` en tablas multi-tenant |
| file_uri permisivo | Solo `s3://{minio_bucket_raw}/(dem\|derived)/...`; paths locales solo en development/test |
| MinIO bucket | Rechaza bucket distinto al configurado |
| GDAL Python | Dockerfile instala `python3-gdal` + `pip install gdal==$(gdal-config --version)` y verifica `from osgeo import gdal` |
| Rate limit | `RATE_LIMIT_FAIL_OPEN=false` por defecto (fail-closed) |
| /metrics | Requiere auth salvo `METRICS_PUBLIC=true` |
| AUTH_DISABLED | Rechazado en `production`/`prod` |

## Pendiente consciente (P2 / no cerrado en R4)

- Retención automática end-to-end
- Slope CRS-aware completo (preview numpy approx OK; gdaldem scale en Docker)
- Cache Terrarium multi-sample
- JWT en sessionStorage (frontend)
- Carrera idempotencia workers (SKIP LOCKED ya existe; falta prueba de carga)
- curvature_coeff en LOS geométrico (solo aplica a viewshed GDAL)

## Evidencia de pruebas R4

```
test_auth_security.py          8 passed
topography + clip + store      10+ passed
e2e_topography.py              10/10
JWT forged token with weak secret → RuntimeError (rejected)
API key hash match/mismatch    OK
```

## Cómo arrancar limpio en tu entorno

```bash
cd geoint-platform
cp .env.example .env
# OBLIGATORIO:
echo "JWT_SECRET=$(openssl rand -hex 32)" >> .env
# AUTH_DISABLED=false
# RATE_LIMIT_FAIL_OPEN=false
# METRICS_PUBLIC=false

python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# Si osgeo falta en host (en Docker ya va):
#   sudo apt install gdal-bin libgdal-dev python3-gdal
#   pip install gdal==$(gdal-config --version)

docker compose up -d
alembic upgrade head   # incluye 0009
pytest tests/unit/test_auth_security.py -v
PYTHONPATH=. python scripts/e2e_topography.py
uvicorn app.main:app --reload
```

**Conclusión:** Los dos fallos de autenticación confirmados, el import de Topografía, el worker que no compilaba, la frontera file_uri y el camino FORCE RLS + scheduler quedan **cerrados en código y tests**. R4 sigue sin ser “prod checklist completa” (retención, OIDC real, carga), pero **ya no es trivial fabricar admin JWT con secret por defecto**.
