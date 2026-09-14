"""Topography API — elevation, profile, slope, aspect, hillshade, LOS, viewshed."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_principal
from app.auth.models import Principal
from app.db.session import get_db
from app.db.tenant import set_tenant
from app.topography.models import (
    DemAssetCreate,
    DemProvider,
    ElevationResponse,
    LosRequest,
    LosResponse,
    ProfileRequest,
    ProfileResponse,
    RasterOpRequest,
    RasterOpResponse,
    ViewshedRequest,
    ViewshedResponse,
)
from app.topography.service import TopographyService

router = APIRouter(prefix="/api/v1/topography", tags=["topography"])


@router.get("/providers")
async def providers(principal: Principal = Depends(get_current_principal)):
    svc = TopographyService()
    return await svc.provider_info()


@router.get("/dem")
async def list_dem(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db),
):
    await set_tenant(session, principal.tenant_id)
    svc = TopographyService(session)
    assets = await svc.list_dems(principal.tenant_id)
    return {"dem_assets": assets, "tenant_id": principal.tenant_id}


@router.post("/dem/register")
async def register_dem(
    body: DemAssetCreate,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db),
):
    await set_tenant(session, principal.tenant_id)
    svc = TopographyService(session)
    try:
        asset = await svc.register_dem(principal.tenant_id, body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return asset


@router.get("/elevation", response_model=ElevationResponse)
async def elevation(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    dem_id: str | None = None,
    preferred_provider: DemProvider | None = None,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db),
):
    await set_tenant(session, principal.tenant_id)
    svc = TopographyService(session)
    return await svc.elevation(
        principal.tenant_id, lat, lon, dem_id, preferred_provider
    )


@router.post("/profile", response_model=ProfileResponse)
async def profile(
    body: ProfileRequest,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db),
):
    await set_tenant(session, principal.tenant_id)
    svc = TopographyService(session)
    return await svc.profile(
        principal.tenant_id,
        body.coordinates,
        body.sample_distance_m,
        body.dem_id,
    )


@router.post("/slope", response_model=RasterOpResponse)
async def slope(
    body: RasterOpRequest,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db),
):
    await set_tenant(session, principal.tenant_id)
    svc = TopographyService(session)
    try:
        return await svc.raster_op(
            principal.tenant_id, body.dem_id, "slope", body.bbox
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/aspect", response_model=RasterOpResponse)
async def aspect(
    body: RasterOpRequest,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db),
):
    await set_tenant(session, principal.tenant_id)
    svc = TopographyService(session)
    try:
        return await svc.raster_op(
            principal.tenant_id, body.dem_id, "aspect", body.bbox
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/hillshade", response_model=RasterOpResponse)
async def hillshade(
    body: RasterOpRequest,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db),
):
    await set_tenant(session, principal.tenant_id)
    svc = TopographyService(session)
    try:
        return await svc.raster_op(
            principal.tenant_id, body.dem_id, "hillshade", body.bbox
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/los", response_model=LosResponse)
async def line_of_sight(
    body: LosRequest,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db),
):
    await set_tenant(session, principal.tenant_id)
    svc = TopographyService(session)
    return await svc.line_of_sight(
        principal.tenant_id,
        body.observer_lon,
        body.observer_lat,
        body.target_lon,
        body.target_lat,
        body.observer_height_m,
        body.target_height_m,
        body.dem_id,
    )


@router.post("/viewshed", response_model=ViewshedResponse)
async def viewshed(
    body: ViewshedRequest,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db),
):
    await set_tenant(session, principal.tenant_id)
    svc = TopographyService(session)
    try:
        return await svc.viewshed(
            principal.tenant_id,
            body.dem_id,
            body.observer_lon,
            body.observer_lat,
            body.observer_height_m,
            body.target_height_m,
            body.max_distance_m,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/slope-preview")
async def slope_preview(
    dem_id: str = Query(...),
    west: float | None = None,
    south: float | None = None,
    east: float | None = None,
    north: float | None = None,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db),
):
    """PNG slope overlay for MapLibre image source. Bounds in response headers."""
    await set_tenant(session, principal.tenant_id)
    svc = TopographyService(session)
    bbox = None
    if None not in (west, south, east, north):
        bbox = [west, south, east, north]  # type: ignore
    try:
        result = await svc.slope_preview(principal.tenant_id, dem_id, bbox)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    w, s, e, n = result["bounds"]
    headers = {
        "X-Bounds-West": str(w),
        "X-Bounds-South": str(s),
        "X-Bounds-East": str(e),
        "X-Bounds-North": str(n),
        "X-Slope-Min": str(result["stats"]["slope_min"]),
        "X-Slope-Max": str(result["stats"]["slope_max"]),
        "X-Slope-Mean": str(result["stats"]["slope_mean"]),
        "Access-Control-Expose-Headers": "X-Bounds-West,X-Bounds-South,X-Bounds-East,X-Bounds-North,X-Slope-Min,X-Slope-Max,X-Slope-Mean",
    }
    return Response(content=result["png"], media_type="image/png", headers=headers)

