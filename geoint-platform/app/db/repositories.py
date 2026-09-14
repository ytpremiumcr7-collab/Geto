from datetime import datetime, timezone
from uuid import UUID

from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Entity, Observation
from app.domain.models import Observation as ObservationDTO


class ObservationRepository:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def insert(
        self,
        observation: ObservationDTO,
        raw_payload_uri: str | None = None,
    ) -> Observation | None:
        """Inserta con ON CONFLICT DO NOTHING. Devuelve None si era duplicado."""
        from sqlalchemy.dialects.postgresql import insert
        import uuid

        geometry = None
        altitude_m = None
        if observation.position:
            altitude_m = observation.position.altitude_m
            geometry = from_shape(
                Point(
                    observation.position.lon,
                    observation.position.lat,
                    altitude_m or 0,
                ),
                srid=4326,
            )

        row_id = uuid.uuid4()
        stmt = (
            insert(Observation)
            .values(
                id=row_id,
                tenant_id=getattr(observation, 'tenant_id', None) or "default",
                entity_id=observation.entity_id,
                entity_type=observation.entity_type,
                source_id=observation.source_id,
                source_record_id=observation.source_record_id,
                observed_at=observation.observed_at,
                received_at=observation.received_at,
                geometry=geometry,
                altitude_m=altitude_m,
                speed_mps=observation.speed_mps,
                heading_deg=observation.heading_deg,
                accuracy_m=observation.accuracy_m,
                confidence=observation.confidence,
                attributes=observation.attributes,
                provenance=observation.provenance,
                raw_payload_uri=raw_payload_uri,
            )
            .on_conflict_do_nothing(
                constraint="uq_observations_tenant_source_entity_time",
            )
            .returning(Observation.id)
        )
        result = await self.session.execute(stmt)
        inserted_id = result.scalar_one_or_none()
        if inserted_id is None:
            return None
        await self.session.flush()
        return await self.session.get(Observation, inserted_id)

    async def list(
        self,
        entity_id: str | None = None,
        source_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
    ):
        stmt = select(Observation).order_by(
            Observation.observed_at.desc()
        )

        if entity_id:
            stmt = stmt.where(
                Observation.entity_id == entity_id
            )

        if source_id:
            stmt = stmt.where(
                Observation.source_id == source_id
            )

        if since is not None:
            stmt = stmt.where(Observation.observed_at >= since)

        if until is not None:
            stmt = stmt.where(Observation.observed_at <= until)

        stmt = stmt.limit(min(limit, 1000))

        result = await self.session.execute(stmt)

        return list(result.scalars().all())


class EntityRepository:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert(
        self,
        entity_id: str,
        entity_type: str,
        observed_at: datetime,
        properties: dict | None = None,
        tenant_id: str = "default",
    ) -> Entity:

        stmt = select(Entity).where(
            Entity.entity_id == entity_id,
            Entity.tenant_id == tenant_id,
        )

        result = await self.session.execute(stmt)
        entity = result.scalar_one_or_none()

        if entity is None:
            entity = Entity(
                tenant_id=tenant_id,
                entity_id=entity_id,
                entity_type=entity_type,
                first_seen=observed_at,
                last_seen=observed_at,
                properties=properties or {},
            )
            self.session.add(entity)
        else:
            entity.last_seen = max(
                entity.last_seen or observed_at,
                observed_at,
            )

            if properties:
                entity.properties = {
                    **(entity.properties or {}),
                    **properties,
                }

        await self.session.flush()

        return entity

    async def get(self, entity_id: str):
        stmt = select(Entity).where(
            Entity.entity_id == entity_id
        )

        result = await self.session.execute(stmt)

        return result.scalar_one_or_none()

