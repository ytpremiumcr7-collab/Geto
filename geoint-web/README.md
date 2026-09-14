# geoint-web

Operator UI: map, sources, geofences, alerts, analytics, permissions, admin.

## Stack

React 18 · Vite · MapLibre · TypeScript

## Run

```bash
npm ci
npm run dev      # http://localhost:5173 — proxies /api and /ws to :8000
npm run build    # production bundle
npm run typecheck
```

## Routes

| Path | Purpose |
|------|---------|
| `/login` | Dev token / IdP path |
| `/onboarding` | First-run guidance |
| `/map` | Live map & panels |
| `/alerts` | Geofence alerts & deliveries |
| `/analytics` | ClickHouse templates |
| `/permissions` | Roles & source access |
| `/admin` | Jobs & DLQ |

Auth state comes from `GET /api/v1/me` (`AuthContext`).
