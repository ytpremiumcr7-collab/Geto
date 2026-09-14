from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_principal, get_tenant_db, require_roles
from app.auth.models import Principal
from app.db.session import get_db  # noqa: F401 — legacy
from app.workspaces.service import WorkspaceService

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])
svc = WorkspaceService()


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    aoi_geojson: dict | None = None
    map_center_lon: float | None = None
    map_center_lat: float | None = None
    map_zoom: float | None = None
    is_default: bool = False
    settings: dict = Field(default_factory=dict)


class WorkspaceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    aoi_geojson: dict | None = None
    map_center_lon: float | None = None
    map_center_lat: float | None = None
    map_zoom: float | None = None
    is_default: bool | None = None
    settings: dict | None = None


class LayerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    layer_type: str = Field(min_length=1, max_length=64)
    config: dict = Field(default_factory=dict)
    visible: bool = True
    sort_order: int = 0
    style: dict = Field(default_factory=dict)


@router.get("")
async def list_workspaces(
    db: AsyncSession = Depends(get_tenant_db),
    principal: Principal = Depends(get_current_principal),
):
    items = await svc.list_workspaces(db, principal.tenant_id)
    return {"workspaces": items, "tenant_id": principal.tenant_id}


@router.post("")
async def create_workspace(
    body: WorkspaceCreate,
    db: AsyncSession = Depends(get_tenant_db),
    principal: Principal = Depends(require_roles("admin", "operator")),
):
    item = await svc.create(
        db,
        tenant_id=principal.tenant_id,
        name=body.name,
        description=body.description,
        owner_user_id=principal.user_id,
        aoi_geojson=body.aoi_geojson,
        map_center_lon=body.map_center_lon,
        map_center_lat=body.map_center_lat,
        map_zoom=body.map_zoom,
        is_default=body.is_default,
        settings=body.settings,
    )
    return item


@router.patch("/{workspace_id}")
async def update_workspace(
    workspace_id: UUID,
    body: WorkspaceUpdate,
    db: AsyncSession = Depends(get_tenant_db),
    principal: Principal = Depends(require_roles("admin", "operator")),
):
    item = await svc.update(
        db, principal.tenant_id, workspace_id, **body.model_dump(exclude_unset=True)
    )
    if not item:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return item


@router.delete("/{workspace_id}")
async def delete_workspace(
    workspace_id: UUID,
    db: AsyncSession = Depends(get_tenant_db),
    principal: Principal = Depends(require_roles("admin")),
):
    ok = await svc.delete(db, principal.tenant_id, workspace_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return {"ok": True}


@router.get("/{workspace_id}/layers")
async def list_layers(
    workspace_id: UUID,
    db: AsyncSession = Depends(get_tenant_db),
    principal: Principal = Depends(get_current_principal),
):
    items = await svc.list_layers(db, principal.tenant_id, workspace_id)
    return {"layers": items}


@router.post("/{workspace_id}/layers")
async def add_layer(
    workspace_id: UUID,
    body: LayerCreate,
    db: AsyncSession = Depends(get_tenant_db),
    principal: Principal = Depends(require_roles("admin", "operator")),
):
    item = await svc.add_layer(
        db,
        tenant_id=principal.tenant_id,
        workspace_id=workspace_id,
        name=body.name,
        layer_type=body.layer_type,
        config=body.config,
        visible=body.visible,
        sort_order=body.sort_order,
        style=body.style,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return item
