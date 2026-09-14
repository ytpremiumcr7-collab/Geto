from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.geofencing.models import Geofence, GeofenceState


class GeofenceRepository:
    async def find_containing(
        self,
        session: AsyncSession,
        *,
        tenant_id: str,
        lon: float,
        lat: float,
        altitude: float | None = None,
    ) -> list[Geofence]:
        """ST_Covers: incluye borde (mejor semántica operacional que Contains estricto)."""
        point = func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)
        conditions = [
            Geofence.tenant_id == tenant_id,
            Geofence.enabled.is_(True),
            func.ST_Covers(Geofence.geometry, point),
        ]
        if altitude is not None:
            conditions.append(
                and_(
                    (Geofence.min_altitude.is_(None)) | (Geofence.min_altitude <= altitude),
                    (Geofence.max_altitude.is_(None)) | (Geofence.max_altitude >= altitude),
                )
            )
        result = await session.execute(select(Geofence).where(and_(*conditions)))
        return list(result.scalars().all())

    async def list_states_for_entity(
        self,
        session: AsyncSession,
        *,
        tenant_id: str,
        entity_id: str,
        inside_only: bool = False,
    ) -> list[GeofenceState]:
        conditions = [
            GeofenceState.tenant_id == tenant_id,
            GeofenceState.entity_id == entity_id,
        ]
        if inside_only:
            conditions.append(GeofenceState.inside.is_(True))
        result = await session.execute(select(GeofenceState).where(and_(*conditions)))
        return list(result.scalars().all())

    async def get_state(
        self,
        session: AsyncSession,
        *,
        tenant_id: str,
        geofence_id: UUID,
        entity_id: str,
    ) -> GeofenceState | None:
        stmt = select(GeofenceState).where(
            GeofenceState.tenant_id == tenant_id,
            GeofenceState.geofence_id == geofence_id,
            GeofenceState.entity_id == entity_id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_state(
        self,
        session: AsyncSession,
        *,
        tenant_id: str,
        geofence_id: UUID,
        entity_id: str,
        inside: bool,
        when: datetime,
        existing: GeofenceState | None = None,
    ) -> GeofenceState:
        state = existing or await self.get_state(
            session,
            tenant_id=tenant_id,
            geofence_id=geofence_id,
            entity_id=entity_id,
        )
        if state is None:
            state = GeofenceState(
                tenant_id=tenant_id,
                geofence_id=geofence_id,
                entity_id=entity_id,
                inside=inside,
                since=when,
            )
            session.add(state)
        else:
            if state.inside != inside:
                state.inside = inside
                state.since = when
            state.updated_at = when
        await session.flush()
        return state
