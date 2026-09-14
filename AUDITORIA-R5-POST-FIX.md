# Auditoría técnica de cierre — GEOINT Fullstack R5

Fecha de auditoría: 2026-09-12
Artefacto analizado: `geoint-fullstack-COMPLETE-R5.zip`

## Alcance y método

Se descomprimió el ZIP en un entorno de trabajo limpio antes de modificarlo. Se hizo inventario físico, inspección del backend Python, frontend TypeScript/React, configuración, Docker Compose, Dockerfile, Alembic, autenticación/RLS, almacenamiento, workers, topografía, fuentes, pruebas y documentación. Las afirmaciones históricas de README/INSTALL/EVIDENCE no se trataron como evidencia suficiente cuando podían contrastarse con código o ejecución.

## Inventario físico inicial

- Archivos presentes en el ZIP antes de la corrección: **211**.
- Tamaño descomprimido aproximado: **2.5 MB**.
- Python (`.py`): **152**.
- Frontend fuente: TypeScript/TSX/CSS/HTML/JSON según árbol de `geoint-web`.
- Docker Compose: `docker-compose.yml` y `docker-compose.prod.yml`.
- Migraciones Alembic: revisiones `0001` → `0009`.
- No había `.git` dentro del artefacto.

## Cambios efectuados en esta ronda

1. `geoint-platform/requirements.lock.txt`: se eliminó la entrada host-local `-e /tmp/geoint_r5/geoint-platform`. El lock queda con **121 paquetes fijados por versión**, sin rutas editables del entorno de construcción.
2. `geoint-platform/scripts/bootstrap_dev.sh`: usa `python -m pip` y deja de forzar una actualización implícita de pip/setuptools/wheel antes de aplicar el lock.
3. `geoint-platform/Dockerfile`: copia el lock y lo instala antes del editable del proyecto, evitando que la imagen ignore completamente el snapshot de dependencias.
4. `INSTALL.md`: se corrigieron las cifras/claims para no presentar la evidencia histórica como una ejecución limpia recién reproducida y se aclaró que el lock fija versiones, no constituye una reproducción hermética con hashes/arquitectura.

## Verificaciones ejecutables realizadas

### Sintaxis/imports estáticos

- `python3 -m compileall` sobre `app`, `config`, `scripts` y `tests`: **OK**.
- Validación AST de imports locales `app.*`: **0 referencias locales inexistentes**.
- Estadística AST del backend: **86 clases, 184 funciones sync, 180 funciones async**.

### Tests ejecutables en el sandbox actual

El sandbox no tiene Internet/DNS para PyPI y no tiene Docker instalado. Por ello no se puede afirmar una instalación limpia completa ni `docker compose up` desde este entorno.

Sí se ejecutaron pruebas independientes del stack externo:

- `tests/unit/test_topography_engine.py`, `test_topography_clip.py`, `test_topography_routes_import.py`: **9 passed, 2 skipped**.
- `tests/unit/test_marinecadastre_validate.py`: **2 passed**.
- `tests/unit/test_quality.py`: **2 passed**.
- `tests/unit/test_auth_security.py`: **8 passed**, usando exclusivamente un stub temporal de MinIO para satisfacer un import; no se simuló la lógica JWT/API-key.
- El E2E de topografía ejecutó **9 passed, 1 failed** con dependencias externas aisladas; el fallo restante corresponde al chequeo live de Terrarium y no demuestra un fallo del motor DEM local.

### Lo que no se pudo certificar aquí

- `python -m pip install -r requirements.lock.txt` en un venv limpio: **bloqueado por falta de resolución DNS/Internet en el sandbox**.
- `pip install -e ".[dev]"`: no se pudo completar porque depende de la instalación anterior.
- `npm ci`: no se pudo ejecutar en este sandbox por ausencia de contenido utilizable en la caché npm y falta de acceso de red.
- `npm run build`: no se puede declarar como reproducido en este sandbox sin `node_modules` instalados.
- `docker compose up -d`: **Docker no está instalado en el sandbox**.
- `alembic upgrade head` contra PostgreSQL real: no ejecutable aquí.
- E2E completo con PostgreSQL + Redis + NATS + MinIO reales: no ejecutable aquí.

## Arquitectura real: PostgreSQL

PostgreSQL/PostGIS es **estado persistente y catálogo**, no un servicio ornamental.

- `app/db/session.py` crea el engine SQLAlchemy asíncrono contra `settings.database_url`.
- `app/db/models.py` persiste `entities`, `observations` y `source_runs`.
- `app/jobs/models.py`, `app/geofencing/models.py`, `app/outbox/models.py` y `app/db/models_dlq.py` añaden jobs, geofences, outbox y DLQ.
- `app/topography/repository.py` guarda el catálogo de DEM (`dem_assets`) con tenant, provider, CRS, bbox, checksum, URI y metadatos.
- PostGIS se utiliza para geometrías e índices espaciales.
- Alembic `0004`, `0006`, `0008`, `0009` implementa/fortalece RLS; `0009` fuerza RLS sobre las tablas multi-tenant principales y define la política de worker `__system__`.
- Las rutas autenticadas llaman `set_tenant()` antes de consultar datos tenant-scoped.

**Conclusión:** sin PostgreSQL el backend pierde su persistencia, catálogo, consultas espaciales, RLS, jobs/outbox y parte de la topografía.

## Arquitectura real: MinIO

MinIO es **object storage compatible con S3** para datos grandes y payloads, mientras PostgreSQL conserva su metadata/catálogo.

- `app/infrastructure/object_store.py` encapsula `put_json`, `put_bytes` y `get_bytes` mediante el cliente MinIO.
- El `file_uri` de los DEM usa `s3://...` y `TopographyService` descarga temporalmente el raster desde MinIO para operar sobre él.
- `app/sources/minio_dropzone/adapter.py` implementa un dropzone: lista objetos `.json/.geojson`, normaliza y mueve entradas a `processed/` o `failed/`.
- `raw_payload_uri` de `Observation` apunta al objeto raw correspondiente cuando existe.
- El Compose mantiene un volumen persistente `miniodata`.

**Conclusión:** MinIO evita meter GeoTIFF/COG/JSON raw pesados dentro de PostgreSQL; PostgreSQL guarda la referencia y metadata para consultar/aislar el contenido.

## Hallazgos de cierre

### P1 — Lock Python corregido en esta ronda

**Archivo:** `geoint-platform/requirements.lock.txt`.

La versión original contenía `-e /tmp/geoint_r5/geoint-platform`, que solo funcionaba en el host de construcción. Ya fue eliminado.

**Estado:** corregido en la copia de entrega.

### P1 — Reproducción completa aún no demostrada en este entorno

La cadena limpia requiere red para PyPI/npm y Docker para el stack de servicios. Este sandbox carece de ambos. No se debe convertir esta limitación en un “PASS” ficticio.

**Estado:** condicionado al host de verificación.

### P2 — El lock fija versiones, pero no hashes

Las 121 entradas son version-pinned, pero `requirements.lock.txt` no contiene hashes por artefacto. Tampoco hay una matriz de wheels por plataforma/arquitectura.

**Impacto:** buena reproducibilidad de versiones, pero no reproducción hermética/supply-chain completa.

### P2 — Dockerfile ahora respeta el lock, pero el build instala GDAL después

El Dockerfile instala el lock y después intenta instalar GDAL compatible con `gdal-config`. Eso puede modificar el conjunto final respecto del snapshot exacto.

### P2 — CORS amplio en development

`app/main.py:60-67` habilita `allow_origins=["*"]` y `allow_credentials=True` en development/test. No aplica al perfil production, pero no es una política CORS endurecida.

### P2 — WebSocket todavía acepta `?token=`

`app/api/routes/websocket.py:29-57` prioriza header/mensaje, pero conserva token por query string, expresamente marcado como deprecado. Los tokens en URLs pueden terminar en logs/proxies.

### P2 — API keys plaintext legacy siguen admitidas

`app/auth/dependencies.py:48-57` conserva `settings.api_keys` como compatibilidad legacy y solo emite warning fuera de development. La ruta recomendada es `api_key_hashes`.

### P2 — Retención de objetos raw en MinIO no está implementada como purge real

`app/retention/purge.py:38-46` solo registra la política de retención de MinIO y recomienda lifecycle; no lista/elimina objetos por antigüedad desde la aplicación.

### P2 — Test de viewshed está incondicionalmente skipped

`tests/unit/test_topography_engine.py:114-119` tiene `skipif(True)` y cuerpo `pass`. Es deuda de QA consciente, no funcionalidad probada.

### P2 — `health/ready` no comprueba Redis

`app/api/routes/health.py:18-62` evalúa PostgreSQL, NATS y MinIO, pero Redis es dependencia del rate limiter y no forma parte del resultado de readiness.

### P2 — Rutas de datos principales sí son tenant-scoped; no todas las piezas auxiliares tienen la misma cobertura RLS

Las tablas principales de observaciones, entidades, geofences, jobs, DLQ, OSM y DEM tienen políticas RLS. `source_runs` y `outbox_messages` sí contienen `tenant_id`, pero no tienen una migración RLS equivalente en el árbol actual. Debe decidirse explícitamente si son accesibles solo por workers/repositorios de confianza o si necesitan aislamiento SQL adicional.

### P2 — Credenciales root de MinIO en `docker-compose.prod.yml`

El perfil de producción toma credenciales externas, pero el proceso API usa `MINIO_ROOT_USER/MINIO_ROOT_PASSWORD` como credenciales S3. Para mínimo privilegio conviene una cuenta de servicio limitada al bucket/prefijos necesarios.

## Matriz de componentes

| Componente | Código | Config | Tests | Runtime aquí |
|---|---|---|---|---|
| FastAPI | ✅ | ✅ | ✅ parcial | ❌ no stack completo |
| PostgreSQL/PostGIS | ✅ | ✅ | ✅ estático | ❌ Docker ausente |
| Redis | ✅ | ✅ | ⚠️ | ❌ Docker ausente |
| NATS/JetStream | ✅ | ✅ | ⚠️ | ❌ Docker ausente |
| MinIO | ✅ | ✅ | ✅ mock/unit | ❌ real no disponible |
| Topography/DEM | ✅ | ✅ | ✅ 9 pass / 2 skip | ✅ local/sintético |
| Auth JWT/API-Key | ✅ | ✅ | ✅ 8 pass con stub de import | ⚠️ stack completo no |
| React/Vite | ✅ | ✅ | — | ❌ npm install no disponible aquí |
| Alembic | ✅ | ✅ | — | ❌ DB real no disponible |
| Docker prod | ✅ | ✅ | — | ❌ Docker no disponible |

## Veredicto final

**R5 queda mejorado y corregido en empaquetado, pero no puede etiquetarse honestamente como “reproducibilidad total demostrada” desde este sandbox.**

Lo importante: el problema de la ruta editable absoluta quedó eliminado, el árbol fuente compila, los imports locales cierran, las pruebas independientes críticas de topografía/auth ejecutan y el propósito de PostgreSQL/MinIO está realmente integrado en el código.

La aceptación final de “COMPLETE” requiere una última ejecución en una máquina con red + Docker:

1. `bash scripts/bootstrap_dev.sh`
2. `docker compose up -d`
3. `alembic upgrade head`
4. `pytest`
5. `PYTHONPATH=. python scripts/e2e_topography.py`
6. `cd ../geoint-web && npm ci && npm run build`
7. Validación de `/health/ready` contra PostgreSQL + NATS + MinIO y, preferentemente, Redis.

No se hicieron cambios funcionales fuera de los cuatro puntos de empaquetado/reproducibilidad enumerados arriba.
