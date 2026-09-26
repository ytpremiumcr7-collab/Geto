"""Dispatcher tipado: cada fuente recibe solo los kwargs que acepta su adapter."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.correlation.engine import CorrelationEngine
from app.db.models import Observation as ObservationModel
from app.db.models import SourceRun
from app.db.repositories import EntityRepository
from app.db.tenant import set_tenant
from app.domain.models import Observation
from app.domain.quality import calculate_quality
from app.geofencing.service import GeofenceService
from app.infrastructure.object_store import ObjectStore
from app.infrastructure.retry import retryable
from app.outbox.repository import OutboxRepository
from app.policies.source_access import assert_ingestion_allowed
from app.resilience.circuit_breaker import CircuitOpenError, get_breaker
from app.sources.registry import create_adapters

log = structlog.get_logger()


# Argumentos de fetch por fuente (sin kwargs ciegos).
def _fetch_kwargs(source_id: str, config: dict[str, Any]) -> dict[str, Any]:
    if source_id == "opensky":
        return {
            "lamin": config.get("lamin", settings.default_aoi_south),
            "lomin": config.get("lomin", settings.default_aoi_west),
            "lamax": config.get("lamax", settings.default_aoi_north),
            "lomax": config.get("lomax", settings.default_aoi_east),
        }
    if source_id == "celestrak":
        return {"group": config.get("group", settings.celestrak_group)}
    if source_id == "aviation_weather":
        return {"station_ids": config.get("station_ids", "KMCI")}
    if source_id == "copernicus":
        bbox = config.get("bbox")
        kwargs: dict[str, Any] = {"limit": config.get("limit", 20)}
        if bbox:
            kwargs["bbox"] = bbox
        if config.get("datetime_range"):
            kwargs["datetime_range"] = config["datetime_range"]
        return kwargs
    if source_id == "readsb_local":
        return {"path": config.get("path")}
    if source_id == "ais_file":
        return {"path": config.get("path")}
    if source_id == "nexrad":
        return {"site": config.get("site"), "max_keys": int(config.get("max_keys", 20))}
    if source_id == "goes":
        return {"product": config.get("product"), "max_keys": int(config.get("max_keys", 15))}
    if source_id == "jpl_horizons":
        return {
            "command": config.get("command", "399"),
            "start": config.get("start"),
            "stop": config.get("stop"),
            "step": config.get("step", "1 d"),
        }
    if source_id == "minio_dropzone":
        return {
            "prefix": config.get("prefix"),
            "max_objects": int(config.get("max_objects", 50)),
        }
    # usgs_earthquake, nasa_firms: sin kwargs
    return {}


class SourceDispatcher:
    def __init__(self, object_store: ObjectStore | None = None):
        self.adapters = create_adapters()
        self.object_store = object_store or ObjectStore()

    async def execute(
        self,
        session: AsyncSession,
        *,
        source_id: str,
        job_type: str,
        config: dict[str, Any],
        tenant_id: str = "default",
        job_id: str | None = None,
        message_id: str | None = None,
    ) -> int:
        adapter = self.adapters.get(source_id)
        if adapter is None:
            raise ValueError(f"Unknown source_id: {source_id}")

        await set_tenant(session, tenant_id)
        assert_ingestion_allowed(source_id)
        breaker = get_breaker(source_id)
        breaker.before_call()

        kwargs = _fetch_kwargs(source_id, config)
        try:

            @retryable()
            async def _fetch():
                return await adapter.fetch(**kwargs)

            raw = await _fetch()
            breaker.record_success()
        except CircuitOpenError:
            raise
        except Exception:
            breaker.record_failure()
            raise

        raw_key = self.object_store.make_key(
            source_id,
            tenant_id=tenant_id,
            job_id=job_id,
            message_id=message_id,
        )
        raw_uri = await self.object_store.put_json(raw_key, raw)

        received_at = datetime.now(UTC)
        run = SourceRun(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            source_id=source_id,
            started_at=received_at,
            status="running",
            records_seen=0,
            records_normalized=0,
        )
        session.add(run)
        await session.flush()
        entity_repo = EntityRepository(session)
        correlator = CorrelationEngine()
        inserted = 0
        seen = 0
        ch_rows: list[dict] = []
        geofence_service = GeofenceService()
        outbox_early = OutboxRepository()

        async for obs in adapter.normalize(raw, received_at):
            seen += 1
            obs.confidence = calculate_quality(obs)
            await entity_repo.upsert(
                entity_id=obs.entity_id,
                entity_type=obs.entity_type,
                observed_at=obs.observed_at,
                properties=obs.attributes,
                tenant_id=tenant_id,
            )
            if await self._insert_observation(session, obs, raw_uri, tenant_id=tenant_id):
                inserted += 1
                ch_rows.append(
                    {
                        "entity_id": obs.entity_id,
                        "entity_type": obs.entity_type,
                        "source_id": obs.source_id,
                        "observed_at": obs.observed_at.isoformat(),
                        "received_at": obs.received_at.isoformat(),
                        "position": {
                            "lon": obs.position.lon if obs.position else None,
                            "lat": obs.position.lat if obs.position else None,
                            "altitude_m": obs.position.altitude_m if obs.position else None,
                        },
                        "speed_mps": obs.speed_mps,
                        "heading_deg": obs.heading_deg,
                        "confidence": obs.confidence,
                    }
                )
                if obs.position:
                    await geofence_service.evaluate_observation(
                        session,
                        tenant_id=tenant_id,
                        entity_id=obs.entity_id,
                        lon=obs.position.lon,
                        lat=obs.position.lat,
                        altitude=obs.position.altitude_m,
                        observed_at=obs.observed_at,
                    )
                for ev in correlator.detect(obs):
                    await outbox_early.enqueue(
                        session,
                        subject=f"geoint.event.{tenant_id}",
                        payload={
                            "event_type": ev.event_type,
                            "entity_id": ev.entity_id,
                            "severity": ev.severity,
                            "observed_at": ev.observed_at.isoformat(),
                            "data": ev.payload,
                            "tenant_id": tenant_id,
                        },
                        tenant_id=tenant_id,
                    )

        run.records_seen = seen
        run.records_normalized = inserted
        run.finished_at = datetime.now(UTC)
        run.status = "ok"
        outbox = OutboxRepository()
        await outbox.enqueue(
            session,
            subject=f"geoint.ingestion.{source_id}.completed",
            payload={
                "source_id": source_id,
                "inserted": inserted,
                "job_type": job_type,
            },
            tenant_id=tenant_id,
        )
        # Durable analytics intent in same TX as observations (outbox)
        if getattr(settings, "clickhouse_enabled", False) and ch_rows:
            await outbox.enqueue(
                session,
                subject="geoint.analytics.observations",
                payload={"tenant_id": tenant_id, "source_id": source_id, "rows": ch_rows},
                tenant_id=tenant_id,
            )
        await session.commit()
        log.info(
            "dispatch_ok",
            source=source_id,
            inserted=inserted,
            job_type=job_type,
        )
        return inserted

    async def _insert_observation(
        self,
        session: AsyncSession,
        observation: Observation,
        raw_payload_uri: str | None,
        tenant_id: str = "default",
    ) -> bool:
        geometry = None
        altitude = None
        if observation.position:
            altitude = observation.position.altitude_m
            geometry = from_shape(
                Point(
                    observation.position.lon,
                    observation.position.lat,
                    altitude or 0,
                ),
                srid=4326,
            )

        stmt = (
            insert(ObservationModel)
            .values(
                tenant_id=tenant_id,
                entity_id=observation.entity_id,
                entity_type=observation.entity_type,
                source_id=observation.source_id,
                source_record_id=observation.source_record_id,
                observed_at=observation.observed_at,
                received_at=observation.received_at,
                geometry=geometry,
                altitude_m=altitude,
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
            .returning(ObservationModel.id)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None
