"""Product analytics API (ClickHouse templates)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.analytics.clickhouse import QUERY_TEMPLATES, ClickHouseClient
from app.auth.dependencies import get_current_principal, require_roles
from app.auth.models import Principal
from app.core.config import settings

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/templates")
async def list_templates(principal: Principal = Depends(get_current_principal)):
    client = ClickHouseClient()
    return {
        "enabled": bool(settings.clickhouse_enabled),
        "templates": client.list_templates(),
        "tenant_id": principal.tenant_id,
    }


@router.get("/query/{template_id}")
async def run_template(
    template_id: str,
    principal: Principal = Depends(require_roles("admin", "operator", "goodmode")),
):
    if template_id not in QUERY_TEMPLATES:
        raise HTTPException(status_code=404, detail=f"Unknown template: {template_id}")
    client = ClickHouseClient()
    result = await client.query(template_id, tenant_id=principal.tenant_id)
    result["tenant_id"] = principal.tenant_id
    return result


@router.get("/status")
async def analytics_status(principal: Principal = Depends(get_current_principal)):
    client = ClickHouseClient()
    ok = await client.ping()
    return {
        "enabled": bool(settings.clickhouse_enabled),
        "reachable": ok,
        "url_configured": bool(settings.clickhouse_url),
        "tenant_id": principal.tenant_id,
    }
