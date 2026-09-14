from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import get_current_principal
from app.auth.models import Principal
from app.policies.source_access import (
    assert_can_admin_source,
    assert_can_read_source,
)
from app.services.source_service import SourceService

router = APIRouter(
    prefix="/api/v1/sources",
    tags=["sources"],
)

service = SourceService()


@router.get("")
async def list_sources(
    principal: Principal = Depends(get_current_principal),
):
    """Lista filtrada por política. OpenSky solo available=true para goodmode."""
    return {
        "tenant_id": principal.tenant_id,
        "roles": sorted(principal.roles),
        "sources": service.list_for(principal),
    }


@router.get("/nasa_firms/wms")
async def firms_wms_info(
    principal: Principal = Depends(get_current_principal),
):
    """Plantilla WMS FIRMS si FIRMS_MAP_KEY está en env."""
    from app.core.config import settings

    if not settings.firms_map_key:
        return {"available": False, "detail": "FIRMS_MAP_KEY not configured"}
    key = settings.firms_map_key
    base = f"https://firms.modaps.eosdis.nasa.gov/mapserver/wms/fires/{key}"
    layer = getattr(settings, "firms_wms_layer", "fires_viirs_24")
    tile_url = (
        f"{base}/?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap"
        f"&LAYERS={layer}&STYLES=&FORMAT=image/png&TRANSPARENT=true"
        f"&SRS=EPSG:3857&WIDTH=256&HEIGHT=256&BBOX={{bbox-epsg-3857}}"
    )
    return {
        "available": True,
        "layer": layer,
        "tile_url": tile_url,
        "attribution": "NASA FIRMS",
    }


@router.get("/{source_id}/health")
async def source_health(
    source_id: str,
    principal: Principal = Depends(get_current_principal),
):
    """Health: admin puede chequear OpenSky; lectura de datos es otro permiso."""
    adapter = service.get(source_id)
    if not adapter:
        raise HTTPException(status_code=404, detail="Unknown source")

    # Health permitido con admin del source O con read
    try:
        assert_can_admin_source(principal, source_id)
    except HTTPException:
        assert_can_read_source(principal, source_id)

    return {
        "source_id": source_id,
        "healthy": await adapter.health(),
    }


@router.get("/{source_id}/access")
async def source_access(
    source_id: str,
    principal: Principal = Depends(get_current_principal),
):
    """Introspección de política (sin filtrar): útil para UI/admin."""
    from app.policies.source_access import can_admin_source, can_read_source

    policy = service.policy(source_id)
    if not policy and not service.get(source_id):
        raise HTTPException(status_code=404, detail="Unknown source")
    return {
        "source_id": source_id,
        "can_read": can_read_source(principal, source_id),
        "can_admin": can_admin_source(principal, source_id),
        "policy": {
            "access_policy": policy.access_policy.value if policy else None,
            "commercial_status": policy.commercial_status if policy else None,
            "retention": policy.retention if policy else None,
            "read_permission": policy.read_permission if policy else None,
            "admin_permission": policy.admin_permission if policy else None,
        },
    }
