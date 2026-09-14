"""Current principal: identity, roles, fine-grained permissions for the client."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_principal
from app.auth.models import Principal
from app.policies.source_access import SOURCE_POLICIES

router = APIRouter(prefix="/api/v1/me", tags=["me"])


@router.get("")
async def me(principal: Principal = Depends(get_current_principal)):
    perms = sorted(principal.permissions())
    # Sources the principal can read (product-facing)
    readable = []
    for source_id, policy in SOURCE_POLICIES.items():
        readable.append(
            {
                "source_id": source_id,
                "access_policy": policy.access_policy.value
                if hasattr(policy.access_policy, "value")
                else str(policy.access_policy),
                "read_permission": policy.read_permission,
                "admin_permission": policy.admin_permission,
                "can_read": bool(
                    policy.read_permission and policy.read_permission in principal.permissions()
                ),
                "can_admin": bool(
                    policy.admin_permission and policy.admin_permission in principal.permissions()
                ),
            }
        )
    return {
        "user_id": principal.user_id,
        "tenant_id": principal.tenant_id,
        "roles": sorted(principal.roles),
        "permissions": perms,
        "sources": readable,
    }


@router.get("/permissions")
async def my_permissions(principal: Principal = Depends(get_current_principal)):
    return {
        "user_id": principal.user_id,
        "tenant_id": principal.tenant_id,
        "roles": sorted(principal.roles),
        "permissions": sorted(principal.permissions()),
    }
