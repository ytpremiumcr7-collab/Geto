from fastapi import APIRouter, Depends, HTTPException
from geoalchemy2.shape import to_shape
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_principal, get_tenant_db
from app.auth.models import Principal
from app.db.repositories import EntityRepository, ObservationRepository
from app.db.session import get_db  # noqa: F401 — legacy

router = APIRouter(
    prefix="/api/v1/entities",
    tags=["entities"],
)


@router.get("/{entity_id}")
async def get_entity(
    entity_id: str,
    db: AsyncSession = Depends(get_tenant_db),
    principal: Principal = Depends(get_current_principal),
):
    repository = EntityRepository(db)
    entity = await repository.get(entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return {
        "tenant_id": principal.tenant_id,
        "entity_id": entity.entity_id,
        "entity_type": entity.entity_type,
        "first_seen": entity.first_seen.isoformat() if entity.first_seen else None,
        "last_seen": entity.last_seen.isoformat() if entity.last_seen else None,
        "properties": entity.properties,
    }


@router.get("/{entity_id}/track")
async def get_track(
    entity_id: str,
    limit: int = 100,
    db: AsyncSession = Depends(get_tenant_db),
    principal: Principal = Depends(get_current_principal),
):
    repository = ObservationRepository(db)
    rows = await repository.list(entity_id=entity_id, limit=limit)
    track = []
    for row in reversed(rows):
        lon = lat = None
        if getattr(row, "geometry", None) is not None:
            try:
                shape = to_shape(row.geometry)
                lon, lat = float(shape.x), float(shape.y)
            except Exception:
                pass
        track.append(
            {
                "observed_at": row.observed_at.isoformat(),
                "lon": lon,
                "lat": lat,
                "speed_mps": row.speed_mps,
                "heading_deg": row.heading_deg,
                "altitude_m": row.altitude_m,
                "attributes": row.attributes,
            }
        )
    return {
        "tenant_id": principal.tenant_id,
        "entity_id": entity_id,
        "track": track,
    }
