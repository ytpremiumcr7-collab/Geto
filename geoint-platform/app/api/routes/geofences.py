from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from geoalchemy2.shape import from_shape
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_principal, get_tenant_db, require_roles
from app.auth.models import Principal
from app.db.session import get_db  # noqa: F401 — legacy
from app.geofencing.models import Geofence

router = APIRouter(prefix="/api/v1/geofences", tags=["geofences"])


class GeofenceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    geometry: dict  # GeoJSON Polygon or MultiPolygon
    min_altitude: float | None = None
    max_altitude: float | None = None
    metadata: dict = Field(default_factory=dict)


@router.get("")
async def list_geofences(
    db: AsyncSession = Depends(get_tenant_db),
    principal: Principal = Depends(get_current_principal),
):
    result = await db.execute(
        select(Geofence).where(Geofence.tenant_id == principal.tenant_id).order_by(Geofence.name)
    )
    from geoalchemy2.shape import to_shape
    from shapely.geometry import mapping

    geofences = []
    for g in result.scalars().all():
        geom_json = None
        if g.geometry is not None:
            try:
                geom_json = mapping(to_shape(g.geometry))
            except Exception:
                geom_json = None
        geofences.append(
            {
                "id": str(g.id),
                "name": g.name,
                "enabled": g.enabled,
                "description": g.description,
                "geometry": geom_json,
            }
        )
    return {"geofences": geofences, "tenant_id": principal.tenant_id}


@router.post("")
async def create_geofence(
    body: GeofenceCreate,
    db: AsyncSession = Depends(get_tenant_db),
    principal: Principal = Depends(require_roles("admin", "operator")),
):
    from app.geofencing.geometry_validate import (
        InvalidGeofenceGeometry,
        validate_and_normalize_geofence_geometry,
    )

    try:
        geom = validate_and_normalize_geofence_geometry(body.geometry)
    except InvalidGeofenceGeometry as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    fence = Geofence(
        id=uuid4(),
        tenant_id=principal.tenant_id,
        name=body.name,
        description=body.description,
        geometry=from_shape(geom, srid=4326),
        min_altitude=body.min_altitude,
        max_altitude=body.max_altitude,
        metadata_=body.metadata,
    )
    db.add(fence)
    await db.commit()
    return {"id": str(fence.id), "name": fence.name}
