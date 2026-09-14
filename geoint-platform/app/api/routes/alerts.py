from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.delivery import DeliveryService
from app.alerts.service import AlertService
from app.auth.dependencies import get_current_principal, require_roles
from app.auth.models import Principal
from app.db.session import get_db
from app.db.tenant import set_tenant

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])
svc = AlertService()


class ChannelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    channel_type: str = Field(pattern="^(webhook|email|websocket|log)$")
    config: dict = Field(default_factory=dict)


class RuleCreate(BaseModel):
    geofence_id: UUID
    name: str = Field(min_length=1, max_length=255)
    on_enter: bool = True
    on_exit: bool = True
    channel_ids: list[str] = Field(default_factory=list)
    entity_type_filter: list[str] | None = None
    severity: str = Field(default="medium", pattern="^(low|medium|high|critical)$")


class SilenceBody(BaseModel):
    minutes: int = Field(default=60, ge=1, le=10080)


@router.get("/channels")
async def list_channels(
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    await set_tenant(db, principal.tenant_id)
    return {"channels": await svc.list_channels(db, principal.tenant_id)}


@router.post("/channels")
async def create_channel(
    body: ChannelCreate,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_roles("admin", "operator")),
):
    await set_tenant(db, principal.tenant_id)
    if body.channel_type == "webhook":
        from app.alerts.ssrf import UnsafeWebhookURL, validate_webhook_url

        try:
            cfg = dict(body.config or {})
            cfg["url"] = validate_webhook_url(
                str(cfg.get("url") or ""),
                require_https=bool(cfg.get("require_https")),
            )
            body = body.model_copy(update={"config": cfg})
        except UnsafeWebhookURL as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    return await svc.create_channel(
        db,
        tenant_id=principal.tenant_id,
        name=body.name,
        channel_type=body.channel_type,
        config=body.config,
    )


@router.get("/rules")
async def list_rules(
    geofence_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    await set_tenant(db, principal.tenant_id)
    return {"rules": await svc.list_rules(db, principal.tenant_id, geofence_id)}


@router.post("/rules")
async def create_rule(
    body: RuleCreate,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_roles("admin", "operator")),
):
    await set_tenant(db, principal.tenant_id)
    # Geofence must belong to the same tenant (integrity, not only RLS)
    from sqlalchemy import select
    from app.geofencing.models import Geofence

    fence = (
        await db.execute(
            select(Geofence).where(
                Geofence.id == body.geofence_id,
                Geofence.tenant_id == principal.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if fence is None:
        raise HTTPException(status_code=404, detail="Geofence not found for tenant")
    return await svc.create_rule(
        db,
        tenant_id=principal.tenant_id,
        geofence_id=body.geofence_id,
        name=body.name,
        on_enter=body.on_enter,
        on_exit=body.on_exit,
        channel_ids=body.channel_ids,
        entity_type_filter=body.entity_type_filter,
        severity=body.severity,
    )


@router.post("/rules/{rule_id}/silence")
async def silence_rule(
    rule_id: UUID,
    body: SilenceBody,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_roles("admin", "operator")),
):
    await set_tenant(db, principal.tenant_id)
    until = datetime.now(UTC) + timedelta(minutes=body.minutes)
    item = await svc.silence_rule(db, principal.tenant_id, rule_id, until)
    if not item:
        raise HTTPException(status_code=404, detail="Rule not found")
    return item


@router.get("")
async def list_alerts(
    status: str | None = Query("open"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    await set_tenant(db, principal.tenant_id)
    return {
        "alerts": await svc.list_alerts(db, principal.tenant_id, status=status, limit=limit),
        "tenant_id": principal.tenant_id,
    }


@router.post("/{alert_id}/ack")
async def ack_alert(
    alert_id: UUID,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    await set_tenant(db, principal.tenant_id)
    item = await svc.ack_alert(db, principal.tenant_id, alert_id, principal.user_id)
    if not item:
        raise HTTPException(status_code=404, detail="Alert not found")
    return item


@router.post("/{alert_id}/resolve")
async def resolve_alert(
    alert_id: UUID,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_roles("admin", "operator")),
):
    await set_tenant(db, principal.tenant_id)
    item = await svc.resolve_alert(db, principal.tenant_id, alert_id)
    if not item:
        raise HTTPException(status_code=404, detail="Alert not found")
    return item


@router.get("/{alert_id}/deliveries")
async def list_deliveries(
    alert_id: UUID,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    await set_tenant(db, principal.tenant_id)
    items = await DeliveryService().list_for_alert(db, principal.tenant_id, alert_id)
    return {"deliveries": items, "alert_id": str(alert_id)}
