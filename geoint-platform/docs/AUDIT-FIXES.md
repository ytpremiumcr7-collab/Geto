# Correcciones auditoría (P0 + P1 críticos)

## P0 resueltos
1. **SourceDispatcher**: `_insert_observation(..., tenant_id=)` + constraint `uq_observations_tenant_source_entity_time`
2. **Tenant e2e**: `SourceJob.tenant_id` → `publish_job` → worker payload → `dispatcher.execute(tenant_id=)` → entity/observation insert + `set_tenant`
3. **API RLS**: `set_tenant` en observations y entities antes de queries
4. **compose dev**: servicios `geoint-scheduler`, `geoint-worker`, `geoint-outbox`
5. **Entity upsert**: recibe y filtra por `tenant_id`

## P1 parciales
- ClickHouse: escribe `ch_rows` reales (no lista vacía)
- Makefile: un solo target `worker` → source_worker
- Track API: incluye `lon`/`lat`
- Map popup: `textContent` / `setDOMContent` (sin XSS por setHTML)
- `pipeline.py` marcado LEGACY

## Pendiente (siguiente ronda)
- OIDC / RS256, rate limit Redis, WS auth sin query string
- Correlation/quality en pipeline, source_runs, ObjectStore async
- OSM RLS, geofence scaling


## Ronda 2

- Rate limit Redis en `/api/v1/auth/token` (20/min por IP, fail-open)
- WebSocket: auth por primer mensaje `{type:auth,token}` o header Bearer; query token deprecado
- Frontend WS sin token en URL
- ObjectStore.put_json async (`asyncio.to_thread`)
- Quality (`calculate_quality`) + CorrelationEngine → outbox en dispatcher
- SourceRun start/finish en cada dispatch
- Retry/backoff tenacity en `adapter.fetch`
- Migración `0006_osm_rls` RLS en osm_features

## Ronda 3 (cierre deuda)

- API keys: `API_KEY_HASHES` SHA-256 + `hashlib.compare_digest`; legacy `API_KEYS` plaintext solo fallback
- OIDC/RS256: `JWT_JWKS_URL` + PyJWKClient; encode local solo HS256
- Rate limit middleware global por IP (excluye `/health/*`)
- Geofencing: `ST_Covers`, estados en 1 query por entidad, `upsert_state(existing=)`
- Script `scripts/hash_api_key.py`
