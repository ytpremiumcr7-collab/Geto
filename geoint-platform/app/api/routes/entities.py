from fastapi import APIRouter, Depends, HTTPException
from geoalchemy2.shape import to_shape
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_principal, get_tenant_db
from app.auth.models import Principal
from app.db.repositories import ObservationRepository
from app.db.session import get_db  # noqa: F401 — legacy
from app.policies.source_access import can_read_source, readable_source_ids

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
    repository = ObservationRepository(db)
    summary = await repository.visible_entity_summary(
        entity_id=entity_id,
        source_ids=readable_source_ids(principal),
    )
    if summary is None:
        # Do not reveal that an entity exists only in a restricted source.
        raise HTTPException(status_code=404, detail="Entity not found")
    return {
        "tenant_id": principal.tenant_id,
        "entity_id": summary["entity_id"],
        "entity_type": summary["entity_type"],
        "first_seen": summary["first_seen"].isoformat(),
        "last_seen": summary["last_seen"].isoformat(),
        # Entity.properties merges attributes across sources and therefore cannot
        # be exposed safely. Use attributes from the latest authorized observation.
        "properties": summary["properties"],
        "source_id": summary["source_id"],
    }


@router.get("/{entity_id}/track")
async def get_track(
    entity_id: str,
    limit: int = 100,
    db: AsyncSession = Depends(get_tenant_db),
    principal: Principal = Depends(get_current_principal),
):
    repository = ObservationRepository(db)
    rows = await repository.list(
        entity_id=entity_id,
        source_ids=readable_source_ids(principal),
        limit=limit,
    )
    rows = [row for row in rows if can_read_source(principal, row.source_id)]
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
                "source_id": row.source_id,
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
