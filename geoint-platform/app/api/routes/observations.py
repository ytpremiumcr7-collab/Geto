from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_principal
from app.auth.models import Principal
from app.policies.source_access import assert_can_read_source
from app.db.repositories import ObservationRepository
from app.db.session import get_db
from app.db.tenant import set_tenant

router = APIRouter(
    prefix="/api/v1/observations",
    tags=["observations"],
)


@router.get("")
async def list_observations(
    entity_id: str | None = None,
    source_id: str | None = None,
    since: datetime | None = Query(None, description="ISO8601 inclusive start"),
    until: datetime | None = Query(None, description="ISO8601 inclusive end"),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    if source_id:
        assert_can_read_source(principal, source_id)
    await set_tenant(db, principal.tenant_id)
    repository = ObservationRepository(db)
    rows = await repository.list(
        entity_id=entity_id,
        source_id=source_id,
        since=since,
        until=until,
        limit=limit,
    )
    from geoalchemy2.shape import to_shape

    observations = []
    for row in rows:
        lon = lat = None
        if getattr(row, "geometry", None) is not None:
            try:
                shape = to_shape(row.geometry)
                lon, lat = float(shape.x), float(shape.y)
            except Exception:
                pass
        observations.append(
            {
                "id": str(row.id),
                "entity_id": row.entity_id,
                "entity_type": row.entity_type,
                "source_id": row.source_id,
                "source_record_id": row.source_record_id,
                "observed_at": row.observed_at.isoformat(),
                "received_at": row.received_at.isoformat(),
                "lon": lon,
                "lat": lat,
                "altitude_m": row.altitude_m,
                "speed_mps": row.speed_mps,
                "heading_deg": row.heading_deg,
                "accuracy_m": row.accuracy_m,
                "confidence": row.confidence,
                "attributes": row.attributes,
                "provenance": row.provenance,
                "raw_payload_uri": row.raw_payload_uri,
            }
        )
    return {
        "tenant_id": principal.tenant_id,
        "count": len(observations),
        "observations": observations,
    }
