# RBAC fino expuesto al cliente

## Backend

- `ROLE_PERMISSIONS` en `app/policies/source_access.py` es la fuente de verdad.
- `Principal.permissions()` = unión de permisos de los roles del token.
- OpenSky: solo `goodmode` tiene `geoint.source.opensky.read` (admin no por defecto).

## API

```
GET /api/v1/me
GET /api/v1/me/permissions
```

Incluye `sources[]` con `can_read` / `can_admin` por fuente.

## UI

El cliente debe usar `/api/v1/me` para ocultar fuentes y acciones, **sin** confiar solo en roles genéricos.
