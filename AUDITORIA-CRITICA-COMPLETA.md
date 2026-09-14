# AUDITORÍA CRÍTICA COMPLETA — GEOINT Fullstack (v2.1)

**Fecha:** 2026-08-20  
**Auditor:** Senior Full-Stack + Security + QA  
**Alcance:** Código fuente completo (geoint-platform + geoint-web), configuración, Docker, migraciones, tests, docs.  
**Método:** Inspección estática de código, configuración, patrones de seguridad, arquitectura, pruebas y residuals existentes.  
**Clasificación de hallazgos:**  
- **VERIFICADO** — confirmado en código  
- **PROBABLE** — inferido con alta confianza  
- **NO VERIFICADO** — requiere runtime  
- **ROTO / FALTANTE / MOCK / PLACEHOLDER** — según evidencia  

---

## 1. RESUMEN EJECUTIVO

| Área                    | Estado general     | Severidad dominante |
|-------------------------|--------------------|---------------------|
| Arquitectura            | Sólida y modular   | Baja                |
| Seguridad (Auth/RLS)    | Buena base, gaps   | Media-Alta          |
| Secretos / Config       | Riesgo en empaquetado | **Crítica**      |
| Multi-tenant / RLS      | Implementado       | Media               |
| Ingestión / Pipeline    | Maduro             | Baja                |
| Tests                   | Unitarios parciales| Media               |
| Frontend                | Funcional básico   | Media               |
| Producción readiness    | Casi listo         | Media               |
| Observabilidad          | Presente           | Baja                |

**Veredicto global:** Proyecto avanzado, bien estructurado y con deuda técnica controlada. **No está listo para producción** hasta resolver secretos en el artefacto, AUTH_DISABLED por defecto en .env de ejemplo de desarrollo, CORS abierto, rate-limit fail-open y cobertura de tests de integración/e2e automatizados. La base de seguridad (JWT + API-Key hashed + RLS + tenant isolation) es sólida y supera a la mayoría de prototipos GEOINT.

---

## 2. HALLAZGOS CRÍTICOS (P0)

### P0-1. Archivo `.env` incluido en el ZIP (VERIFICADO)
- **Evidencia:** El ZIP original contenía `geoint-platform/.env` con valores de desarrollo (`AUTH_DISABLED=true`, `JWT_SECRET=dev-only-not-for-prod`, passwords `change-me`).
- **Riesgo:** Fuga de configuración, posible uso accidental en entornos reales, violación de higiene de secretos.
- **Causa:** `.gitignore` excluye `.env` pero el empaquetado lo incluyó.
- **Mitigación aplicada en esta entrega:** `.env` **eliminado** del ZIP de auditoría. Solo queda `.env.example`.
- **Acción requerida:** Nunca incluir `.env` en artefactos. Usar solo `.env.example` + secrets externos / Docker secrets / vault.

### P0-2. AUTH_DISABLED=true en el `.env` de desarrollo empaquetado (VERIFICADO)
- Aunque se eliminó el `.env`, el historial y el estado previo mostraban `AUTH_DISABLED=true`.
- En `app/auth/dependencies.py` cuando `auth_disabled=True` se devuelve un Principal `admin/operator` sin autenticación real.
- **Riesgo:** Si alguien levanta con el `.env` original, toda la API queda abierta.
- **Estado actual:** `.env.example` tiene `AUTH_DISABLED=false` (correcto).

### P0-3. CORS `allow_origins=["*"]` + credentials en development (VERIFICADO)
```python
if settings.app_env in ("development", "dev", "test"):
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, ...)
```
- **Riesgo:** En cualquier despliegue donde `APP_ENV` no sea estrictamente `production`, CORS abierto + credentials es peligroso.
- **Recomendación:** Lista blanca explícita incluso en dev; nunca `*` con `allow_credentials=True`.

### P0-4. Rate-limit fail-open (VERIFICADO + INTENCIONAL)
- `check_rate_limit` retorna `True` si Redis no está disponible o falla.
- **Riesgo:** En incidentes de Redis, la API queda sin límite (DoS / abuso de token endpoint).
- Documentado en RESIDUALS como intencional para “lean”. Para producción de alta seguridad debe ser **fail-closed** o con circuit breaker + alerta.

### P0-5. Bootstrap token sin secret en development (VERIFICADO)
- `/api/v1/auth/token` permite emitir JWT si `APP_ENV=development` sin `bootstrap_secret`.
- Útil para demos, peligroso si el entorno se etiquetó mal como development.

---

## 3. HALLAZGOS DE SEGURIDAD (P1)

| ID | Hallazgo | Evidencia | Severidad | Estado |
|----|----------|-----------|-----------|--------|
| S1 | JWT HS256 por defecto + secret débil en example | `JWT_SECRET=change-me-...` | Alta | Mitigable con openssl rand |
| S2 | API keys plaintext legacy (`API_KEYS`) | `dependencies.py` fallback | Media | Preferir solo `API_KEY_HASHES` + compare_digest (ya implementado) |
| S3 | WebSocket query `?token=` deprecado pero aún soportado | `websocket.py` | Media | Logs de proxy pueden filtrar token |
| S4 | Métricas Prometheus sin auth (`/metrics`) | `main.py` | Media | En prod proteger o deshabilitar |
| S5 | Passwords por defecto en `docker-compose.yml` | `change-me` | Alta (dev) | Solo dev; prod usa `docker-compose.prod.yml` |
| S6 | MinIO sin TLS en dev (`MINIO_SECURE=false`) | config | Baja (dev) | OK |
| S7 | No hay Content-Security-Policy ni headers de seguridad HTTP | frontend + API | Media | Faltante |
| S8 | Tenant isolation depende de que **todos** los paths llamen `set_tenant` | `tenant.py` + routes | Alta | Parcialmente auditado en AUDIT-FIXES; riesgo residual de olvido |
| S9 | RLS policies usan `current_setting('app.tenant_id', true)` | migración 0004 | Buena | Verificar que el rol de la app no sea superuser |
| S10 | Frontend almacena token (localStorage probable) | `auth.ts` / Login | Media | XSS → robo de token |

**Positivo VERIFICADO:**
- Uso de `hashlib.compare_digest` para API keys.
- Soporte OIDC/RS256 + JWKS preparado.
- RLS con políticas `USING` + `WITH CHECK`.
- Principal con roles y tenant_id procedentes solo del token/key (no del body del cliente).
- Rate limit middleware global (excluye health).

---

## 4. ARQUITECTURA Y CALIDAD DE CÓDIGO

### Fortalezas (VERIFICADO)
- Separación clara: `sources/*` adapters, `ingestion/`, `domain/`, `db/`, `auth/`, `geofencing/`, `correlation/`, `workers/`.
- Outbox pattern + NATS JetStream.
- Circuit breaker / retry (tenacity) en adapters.
- Quality score + correlation engine en pipeline.
- Migraciones Alembic numeradas 0001–0007 con RLS, geofences, unique constraints multi-tenant.
- Multi-fuente real: OpenSky, CelesTrak, USGS, FIRMS, AviationWeather, Copernicus STAC, AIS, readsb, GOES, Horizons, MinIO dropzone, NEXRAD.
- Frontend MapLibre + capas GIBS/FIRMS WMS + tracks + geofences + live events.

### Deuda / Riesgos
- `pipeline.py` marcado LEGACY (documentado).
- Algunos workers/ingestion paths DEPRECATED.
- ClickHouse / Timescale opcionales (flags).
- ObjectStore usa `asyncio.to_thread` (aceptable, no nativo async).
- Falta validación exhaustiva de geometrías GeoJSON en todos los entrypoints (PROBABLE).
- No hay contrato OpenAPI formal versionado fuera de FastAPI auto-docs.

---

## 5. TESTS Y QA

| Tipo | Cantidad | Cobertura aparente |
|------|----------|--------------------|
| Unit (adapters, quality, source_access, orbit…) | ~13 archivos, ~484 LOC | Fuentes individuales + quality + access |
| Integration | 2 archivos (health, sources) | Mínima |
| E2E automatizado | No | Solo checklist manual (`docs/E2E-CHECKLIST.md`) |
| Security tests | No | Faltante |
| Load / chaos | No | Faltante |

**Veredicto QA:** Los unit tests de adapters son un buen comienzo. **Falta** cobertura de:
- Auth (JWT inválido, roles, API-key hash mismatch)
- RLS (cross-tenant isolation)
- Geofencing enter/exit
- Outbox exactly-once
- WebSocket auth flows
- Rate-limit behaviour

Sin tests de integración/e2e automatizados el riesgo de regresión en multi-tenant es alto.

---

## 6. PRODUCCIÓN Y OPERACIÓN

**Presente (VERIFICADO):**
- `docker-compose.prod.yml` (sin puertos innecesarios, AUTH_DISABLED=false)
- `PRODUCTION.md` + checklist
- Prometheus `/metrics`
- OTEL flag
- Graceful shutdown en workers
- Retención configurable + script purge
- Makefile targets

**Faltante / Mejorable:**
- Healthchecks más profundos (ready depende de DB + NATS + MinIO)
- Secrets management (Vault / Docker secrets / K8s)
- Horizontal scaling de WebSocket (documentado como residual: multi-instancia vía NATS)
- Backup/restore procedures
- Network policies / service mesh
- Image scanning / SBOM

---

## 7. FRONTEND (geoint-web)

- React 18 + Vite + MapLibre + TypeScript.
- Auth: login page + token issuer (dev banner).
- Componentes: MapView, EventsFeed, SourcesPanel, GeofencesPanel, TimeFilter, useLiveEvents.
- **Riesgos:**
  - Token en URL deprecado (backend lo soporta aún).
  - Sin CSP, sin sanitización visible de todos los popups (se menciona fix de setHTML → textContent en AUDIT-FIXES).
  - Dependencias mínimas (bueno); falta error boundaries / retry UI.
- **No verificado runtime:** build `tsc -b && vite build` y funcionamiento real de capas GIBS/FIRMS.

---

## 8. COMPLIANCE CON BUENAS PRÁCTICAS DE SEGURIDAD

| Práctica                        | Estado |
|---------------------------------|--------|
| Secretos fuera del código       | Parcial (example OK, ZIP original falló) |
| AuthN + AuthZ                   | Sí (JWT + API key + roles) |
| Multi-tenant isolation          | Sí (RLS + set_tenant) |
| Rate limiting                   | Sí (fail-open) |
| Input validation                | Parcial (Pydantic) |
| Output encoding / XSS           | Parcial (frontend) |
| Logging estructurado            | Sí (structlog) |
| Dependencias pinned             | Revisar pyproject + lock |
| Least privilege DB role         | NO VERIFICADO (riesgo si usa superuser) |
| HTTPS only                      | Responsabilidad del reverse proxy |

---

## 9. LISTA PRIORIZADA DE ACCIONES (siguiente ronda)

### Inmediato (antes de cualquier despliegue real)
1. Eliminar cualquier `.env` de artefactos (hecho en esta entrega).
2. Forzar `APP_ENV=production` + `AUTH_DISABLED=false` + JWT_SECRET fuerte.
3. CORS con orígenes explícitos.
4. Rate-limit fail-closed o con alerta + fallback local.
5. Proteger `/metrics` y deshabilitar bootstrap token en prod.
6. Verificar que el usuario de Postgres **no** sea superuser y que RLS esté FORCED.

### Corto plazo
7. Tests de integración: auth, RLS cross-tenant, geofence, WS.
8. Eliminar soporte de token en query string de WebSocket.
9. Headers de seguridad (HSTS, CSP, X-Content-Type-Options…).
10. Lockfile de Python (poetry.lock / uv.lock / requirements.txt pinneado).

### Medio plazo
11. OIDC real (quitar bootstrap HS256).
12. WebSocket multi-instancia validado.
13. Purge automático + monitoring de DLQ.
14. SBOM + scan de vulnerabilidades en CI.

---

## 10. EVIDENCIA DE ESTA AUDITORÍA

- ZIP original inspeccionado: 266 entradas, ~166 KB.
- Estructura: `geoint-platform` (FastAPI + workers + 7 migraciones + 13 unit tests) + `geoint-web` (Vite/React/MapLibre).
- Documentación interna existente (`AUDIT-FIXES.md`, `RESIDUALS.md`, `PRODUCTION.md`, `E2E-CHECKLIST.md`) revisada y contrastada.
- Código de auth, rate-limit, tenant, main, docker-compose, config, JWT, dependencies leído línea a línea.
- Búsqueda de patrones de secretos / shell / eval / pickle: sin hallazgos de ejecución arbitraria; solo placeholders `change-me`.

**No se ejecutó** en esta ronda:
- `docker compose up` completo
- `pytest`
- `npm run build`
- Tests de penetración runtime

Por tanto: hallazgos de **código y configuración = VERIFICADO**. Comportamiento runtime = **NO VERIFICADO**.

---

## 11. CONCLUSIÓN

El proyecto es **sólido, modular y con conciencia real de seguridad multi-tenant**. Las piezas críticas (auth, RLS, outbox, adapters, geofencing, frontend mapa) están presentes y en su mayoría implementadas de forma correcta.  

Los mayores riesgos actuales son **operacionales y de empaquetado** (secretos, defaults de desarrollo, fail-open, falta de tests de aislamiento), no fallos conceptuales de arquitectura.

**Recomendación:** Tratar como **staging-ready** tras aplicar las acciones P0 + tests de RLS/auth. No promover a producción pública sin fail-closed rate limit, OIDC o secret rotativo, CORS restrictivo y verificación de que el rol DB no bypasea RLS.

---

*Fin de la auditoría crítica. El ZIP de esta entrega contiene el proyecto completo **sin** `.env` + este informe.*
