from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_principal, get_tenant_db
from app.auth.models import Principal
from app.events.repository import EventRepository
from app.policies.source_access import (
    assert_can_read_source,
    can_read_source,
    readable_source_ids,
)

router = APIRouter(
    prefix="/api/v1/events",
    tags=["events"],
)


@router.get("")
async def list_events(
    source_id: str | None = None,
    since: datetime | None = Query(None, description="ISO8601 inclusive start"),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_tenant_db),
    principal: Principal = Depends(get_current_principal),
):
    allowed = readable_source_ids(principal)
    if source_id:
        assert_can_read_source(principal, source_id)
        query_scope = frozenset({source_id})
    else:
        query_scope = allowed

    rows = await EventRepository(db).list(
        source_ids=query_scope,
        source_id=source_id,
        since=since,
        limit=limit,
    )
    rows = [row for row in rows if can_read_source(principal, row.source_id)]
    return {
        "tenant_id": principal.tenant_id,
        "events": [
            {
                "id": str(row.id),
                "source_id": row.source_id,
                "event_type": row.event_type,
                "entity_id": row.entity_id,
                "occurred_at": row.occurred_at.isoformat(),
                "payload": row.payload,
            }
            for row in rows
        ],
    }
