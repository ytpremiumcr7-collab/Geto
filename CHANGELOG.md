# Changelog

All notable product changes to GEOINT Platform (Geto).

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
