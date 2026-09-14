"""Source catalog, health, access introspection, FIRMS WMS proxy."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response

from app.auth.dependencies import get_current_principal
from app.auth.models import Principal
from app.core.config import settings
from app.policies.source_access import (
    assert_can_admin_source,
    assert_can_read_source,
)
from app.services.source_service import SourceService
from app.sources.firms.tile_ticket import issue_ticket, verify_ticket

router = APIRouter(
    prefix="/api/v1/sources",
    tags=["sources"],
)

service = SourceService()
log = structlog.get_logger()

# WMS params the client may pass through; anything else is dropped.
_WMS_ALLOWED_PARAMS = frozenset(
    {
        "SERVICE",
        "VERSION",
        "REQUEST",
        "LAYERS",
        "STYLES",
        "FORMAT",
        "TRANSPARENT",
        "SRS",
        "CRS",
        "WIDTH",
        "HEIGHT",
        "BBOX",
        "BGCOLOR",
        "EXCEPTIONS",
    }
)


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
    """WMS template that points at **our** proxy — NASA MAP_KEY never leaves the server.

    MapLibre uses tile_url with ``{bbox-epsg-3857}``; each tile hit carries a
    short-lived HMAC ticket (no Bearer required on raster requests).
    """
    assert_can_read_source(principal, "nasa_firms")

    if not settings.firms_map_key:
        return {
            "available": False,
            "detail": "FIRMS_MAP_KEY not configured on server",
            "tile_url": None,
        }

    layer = getattr(settings, "firms_wms_layer", "fires_viirs_24") or "fires_viirs_24"
    ticket, exp = issue_ticket(
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
    )
    # Relative URL so the SPA same-origin (or vite proxy) keeps path stable.
    tile_url = (
        f"/api/v1/sources/nasa_firms/wms/proxy"
        f"?ticket={ticket}"
        f"&SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap"
        f"&LAYERS={layer}&STYLES=&FORMAT=image/png&TRANSPARENT=true"
        f"&SRS=EPSG:3857&WIDTH=256&HEIGHT=256&BBOX={{bbox-epsg-3857}}"
    )
    return {
        "available": True,
        "layer": layer,
        "tile_url": tile_url,
        "ticket_expires_at": exp,
        "attribution": "NASA FIRMS",
        "note": "Tiles are proxied server-side; MAP_KEY is not exposed to the client.",
    }


@router.get("/nasa_firms/wms/proxy")
async def firms_wms_proxy(
    request: Request,
    ticket: str | None = Query(None, description="HMAC tile ticket from /nasa_firms/wms"),
):
    """Server-side WMS proxy to NASA FIRMS. Validates ticket; injects MAP_KEY only upstream."""
    claims = verify_ticket(ticket or "")
    if not claims:
        log.warning("firms_proxy_ticket_invalid", has_ticket=bool(ticket))
        raise HTTPException(status_code=401, detail="Invalid or expired FIRMS tile ticket")

    tenant_id, user_id = claims
    key = settings.firms_map_key
    if not key:
        raise HTTPException(status_code=503, detail="FIRMS_MAP_KEY not configured")

    layer = getattr(settings, "firms_wms_layer", "fires_viirs_24") or "fires_viirs_24"
    # Build upstream query from allowlisted params only
    upstream_q: list[tuple[str, str]] = []
    for k, v in request.query_params.multi_items():
        ku = k.upper()
        if ku == "TICKET":
            continue
        if ku not in _WMS_ALLOWED_PARAMS:
            continue
        upstream_q.append((ku, v))

    # Ensure required defaults if client omitted
    have = {k for k, _ in upstream_q}
    defaults = {
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetMap",
        "LAYERS": layer,
        "STYLES": "",
        "FORMAT": "image/png",
        "TRANSPARENT": "true",
        "SRS": "EPSG:3857",
        "WIDTH": "256",
        "HEIGHT": "256",
    }
    for dk, dv in defaults.items():
        if dk not in have:
            upstream_q.append((dk, dv))

    if "BBOX" not in {k for k, _ in upstream_q}:
        raise HTTPException(status_code=400, detail="BBOX is required")

    from urllib.parse import urlencode

    import httpx

    base = f"https://firms.modaps.eosdis.nasa.gov/mapserver/wms/fires/{key}/"
    url = f"{base}?{urlencode(upstream_q)}"

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            upstream = await client.get(url)
    except Exception as e:
        log.exception(
            "firms_proxy_upstream_error",
            tenant_id=tenant_id,
            user_id=user_id,
            error=str(e)[:300],
        )
        raise HTTPException(status_code=502, detail="FIRMS upstream unreachable") from e

    content_type = upstream.headers.get("content-type", "image/png")
    # Do not forward NASA error HTML as success without status
    if upstream.status_code >= 400:
        log.warning(
            "firms_proxy_upstream_status",
            status=upstream.status_code,
            tenant_id=tenant_id,
            body_prefix=upstream.text[:120] if content_type.startswith("text") else "",
        )
        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            media_type=content_type,
        )

    log.debug(
        "firms_proxy_ok",
        tenant_id=tenant_id,
        user_id=user_id,
        bytes=len(upstream.content),
        status=upstream.status_code,
    )
    return Response(
        content=upstream.content,
        status_code=200,
        media_type=content_type,
        headers={
            "Cache-Control": "private, max-age=60",
            "X-Geoint-Firms-Proxy": "1",
        },
    )


@router.get("/{source_id}/health")
async def source_health(
    source_id: str,
    principal: Principal = Depends(get_current_principal),
):
    """Health: admin puede chequear OpenSky; lectura de datos es otro permiso."""
    adapter = service.get(source_id)
    if not adapter:
        raise HTTPException(status_code=404, detail="Unknown source")

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
