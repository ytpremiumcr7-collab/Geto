# RBAC

Source of truth: `app/policies/source_access.py` (`ROLE_PERMISSIONS`, per-source policies).

## Client

```
GET /api/v1/me
GET /api/v1/me/permissions
```

Returns roles, effective permissions, and per-source `can_read` / `can_admin`.

UI: `/permissions` and `AuthContext` — hide actions using `/me`, not only coarse roles.

## Notes

- OpenSky read is **goodmode** by default; admin configures but does not inherit that read.
- `require_roles("admin")` grants admin a pass on role checks; source permissions remain separate.
