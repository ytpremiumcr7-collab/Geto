"""Geofencing enter/exit — una query espacial + estados por entidad (sin N+1)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.geofencing.repository import GeofenceRepository
from app.outbox.repository import OutboxRepository


class GeofenceService:
    def __init__(self, repository: GeofenceRepository | None = None):
        self.repository = repository or GeofenceRepository()

    async def evaluate_observation(
        self,
        session: AsyncSession,
        *,
        tenant_id: str,
        entity_id: str,
        lon: float,
        lat: float,
        altitude: float | None,
        observed_at: datetime,
    ) -> list[dict[str, Any]]:
        containing = await self.repository.find_containing(
            session,
            tenant_id=tenant_id,
            lon=lon,
            lat=lat,
            altitude=altitude,
        )
        inside_ids = {f.id for f in containing}

        # Una sola carga de estados de la entidad
        prior_states = await self.repository.list_states_for_entity(
            session, tenant_id=tenant_id, entity_id=entity_id
        )
        by_fence = {s.geofence_id: s for s in prior_states}

        events: list[dict[str, Any]] = []
        outbox = OutboxRepository()

        for fence in containing:
            prev = by_fence.get(fence.id)
            was_inside = prev.inside if prev else False
            await self.repository.upsert_state(
                session,
                tenant_id=tenant_id,
                geofence_id=fence.id,
                entity_id=entity_id,
                inside=True,
                when=observed_at,
                existing=prev,
            )
            if not was_inside:
                event = {
                    "event_type": "geofence.enter",
                    "tenant_id": tenant_id,
                    "entity_id": entity_id,
                    "geofence_id": str(fence.id),
                    "geofence_name": fence.name,
                    "occurred_at": observed_at.isoformat(),
                    "data": {"lat": lat, "lon": lon, "altitude": altitude},
                }
                events.append(event)
                await outbox.enqueue(
                    session,
                    subject=f"geoint.event.{tenant_id}",
                    payload=event,
                    tenant_id=tenant_id,
                )

        for state in prior_states:
            if state.inside and state.geofence_id not in inside_ids:
                await self.repository.upsert_state(
                    session,
                    tenant_id=tenant_id,
                    geofence_id=state.geofence_id,
                    entity_id=entity_id,
                    inside=False,
                    when=observed_at,
                    existing=state,
                )
                event = {
                    "event_type": "geofence.exit",
                    "tenant_id": tenant_id,
                    "entity_id": entity_id,
                    "geofence_id": str(state.geofence_id),
                    "occurred_at": observed_at.isoformat(),
                    "data": {"lat": lat, "lon": lon, "altitude": altitude},
                }
                events.append(event)
                await outbox.enqueue(
                    session,
                    subject=f"geoint.event.{tenant_id}",
                    payload=event,
                    tenant_id=tenant_id,
                )

        return events
