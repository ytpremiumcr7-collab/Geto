# Changelog

All notable product changes to GEOINT Platform (Geto).

## [2.9.1] — 2026-09-14

### Security / supply-chain
- `requirements.lock.txt` includes SHA256 hashes for every pinned artifact
- CI installs with `pip install --require-hashes -r requirements.lock.txt` then `pip install --no-deps -e .`
- `requirements.in` + `scripts/generate_hashed_lock.py` for reproducible regeneration

## [2.9.0] — 2026-09-14

### Fixed / hardened (remaining audit P1/P2)
- `get_tenant_db` dependency; DB routes no longer rely on manual `set_tenant`
- ClickHouse: outbox `geoint.analytics.observations` + dispatcher write path (durable retry)
- Plaintext `API_KEYS` forbidden in staging/prod; `TRUSTED_HOSTS` required in production
- Geofence geometry validation (validity, size, bounds, make_valid)
- `/metrics` requires admin|metrics role; WS query-token rejected in staging/prod
- MinIO bucket create gated by `MINIO_CREATE_BUCKET`; rate limit uses XFF + identity suffix
- Frontend: `clearAuth()` on `/me` failure (no stale semi-auth session)

## [2.8.0] — 2026-09-14

### Fixed (audit P1 harden)
- Worker idempotency: atomic claim (`processing` + lease) before side effects; completed/failed states
- MinIO `make_key`: `raw/{tenant}/{source}/…` + job/message/uuid (no cross-tenant collision)
- RLS on `source_runs`; `source_jobs` unique `(tenant_id, source_id, name)`
- Alert `entity_type_filter` enforced; geofence events carry `entity_type`
- Alert emit failures logged + outbox retry (no silent `pass`)
- Webhook SSRF validation (DNS + private IP block); NATS alert subject tenant-locked
- Rule create verifies geofence belongs to tenant
- JWT: no silent tenant default in staging/prod; OIDC algorithms strict
- CI: mypy/bandit/typecheck no longer `|| true`; staging CORS_ALLOW_HTTP documented

## [2.7.2] — 2026-09-14

### Changed
- Documentation cleanup: removed historical audit/evidence notes; consolidated ops docs under `geoint-platform/docs/`

## [2.7.1] — 2026-09-14

### Fixed / hardened
- `/health/ready` always returns `errors[]` + timings; dependency failures logged (no silent pass)
- WebSocket: structured logs on connect, auth failure, disconnect (code/reason), cleanup
- FIRMS: MAP_KEY never sent to client; HMAC tile ticket + server-side WMS proxy

## [2.7.0] — 2026-09-14

### Added
- Staging real pack: `.env.staging.example`, `docker-compose.staging.yml`
- `scripts/staging_up.sh`, `staging_verify.py` (JWKS + CH data + notifier health)
- Lab JWKS server `scripts/dev_jwks_server.py` for staging without external IdP
- ClickHouse seed SQL for staging observations
- `docs/STAGING.md`

## [2.6.1] — 2026-09-14

### Added
- DEM register requires documented `vertical_datum`; `resolution_m` is GSD
- LOS clamps `sample_distance_m` to DEM GSD; quality flags `sample_clamped_to_gsd`
- UI always renders `quality.certification` (disclaimer never stripped)

## [2.6.0] — 2026-09-14

### Added
- Alert notifier **HTTP health** `/health/live|ready` + Docker healthcheck + heartbeat file
- ClickHouse **init schema** + `scripts/clickhouse_bootstrap.py` + compose profile `analytics`
- OIDC preflight `scripts/oidc_check.py` + ops doc `OPS-OIDC-CLICKHOUSE-WORKER.md`
- DEM/LOS **decision-support quality**: uncertainty, confidence, refraction k=4/3, certification disclaimer

## [2.5.0] — 2026-09-14

### Added
- Product UI routes: onboarding, map, alerts, analytics, permissions, admin (AppShell)
- AuthContext + `/api/v1/me` wired for visible RBAC in UI
- CI `e2e_ci_product_flow.py`: me → sources → alert emit → delivery delivered
- Root README pre-production clone-and-run

### Fixed
- Frontend build uses Vite hard gate; tsconfig without allowImportingTsExtensions
- CI product e2e step on PostGIS service job

## [2.4.0] — 2026-09-14

### Added
- LOS/Viewshed **precision docs** (`docs/TOPOGRAPHY-LOS-VIEWSHED.md`) + API metadata (`algorithm`, `assumptions`)
- **ClickHouse product API**: `/api/v1/analytics/templates|query|status` (allowlisted templates)
- **RBAC fino al cliente**: `Principal.permissions()`, `/api/v1/me`, `/api/v1/me/permissions`
- Frontend: design **tokens**, skip-link a11y, `lang`, i18n es/en (`src/i18n`)
- CI **E2E smoke** with PostGIS service: alembic upgrade + ASGI health/me/analytics

## [2.3.1] — 2026-09-14

### Added — alert notifiers
- **Delivery worker** `python -m app.workers.alert_notifier` (claim → webhook/SMTP/log/NATS)
- Table `alert_deliveries` with retry/backoff and RLS
- Webhook HMAC (`X-Geoint-Signature: sha256=…`), SMTP via `SMTP_*` settings
- Rule channels enqueue deliveries when geofence alerts are created
- API `GET /api/v1/alerts/{id}/deliveries`; UI shows delivery status
- Compose service `geoint-alert-notifier`

## [2.3.0] — 2026-09-14

### Added (P1 — product surface)
- **Workspaces** with AOI GeoJSON, map center/zoom, default flag, and **saved layers**
- **Geofence alerts product**: channels (webhook/email/websocket/log), rules (enter/exit, severity, silence), alert lifecycle (open → ack → resolve)
- Pipeline hook: geofence enter/exit events create `geofence_alerts` when rules match
- **Admin API** `/api/v1/admin/jobs` — list source jobs, enable/disable, interval
- Admin UI page (sources jobs + DLQ + alerts summary)
- Workspace panel + alerts panel in web client
- E2E product flow test script: auth → source → observation → geofence → alert
- Unified **semver** via root `VERSION` (platform + web aligned to 2.3.0)

### Security (P0 carried from 2.2.x)
- Production fail-fast: OIDC/JWKS, CORS explicit, no change-me secrets
- `scripts/deploy.sh` real deploy with migrate + seed

## [2.2.0] — 2026-09-14

- Ruff-clean CI, production security bootstrap, deploy hardening

## [2.1.0] — prior

- Multi-source ingestion, RLS, topography MVP, geofencing enter/exit, DLQ
