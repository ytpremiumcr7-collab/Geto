"""LEGACY / compatibility only.

Use SourceDispatcher (app.ingestion.dispatcher) for production ingestion
via SourceJobs + NATS. Do not extend this module.
"""

from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.telemetry import (
    INGESTION_DURATION,
    INGESTION_TOTAL,
    OBSERVATIONS_TOTAL,
)
from app.db.repositories import EntityRepository, ObservationRepository
from app.infrastructure.nats_bus import EventBus
from app.infrastructure.object_store import ObjectStore
from app.sources.base import SourceAdapter

log = structlog.get_logger()


class IngestionPipeline:
    def __init__(
        self,
        session: AsyncSession,
        bus: EventBus,
        object_store: ObjectStore,
    ):
        self.session = session
        self.bus = bus
        self.object_store = object_store

    async def process(
        self,
        adapter: SourceAdapter,
        **kwargs,
    ) -> int:
        source_id = adapter.metadata.source_id

        started = __import__("time").perf_counter()

        try:
            raw = await adapter.fetch(**kwargs)

            raw_key = self.object_store.make_key(source_id)

            raw_uri = self.object_store.put_json(
                raw_key,
                raw,
            )

            observations = 0

            observation_repo = ObservationRepository(self.session)

            entity_repo = EntityRepository(self.session)

            async for observation in adapter.normalize(
                raw,
                datetime.now(UTC),
            ):
                try:
                    await entity_repo.upsert(
                        entity_id=observation.entity_id,
                        entity_type=observation.entity_type,
                        observed_at=observation.observed_at,
                        properties=observation.attributes,
                    )

                    model = await observation_repo.insert(
                        observation,
                        raw_payload_uri=raw_uri,
                    )
                    if model is None:
                        await self.session.commit()
                        continue

                    await self.session.commit()
                    await self.bus.publish(
                        f"geoint.observation.{source_id}",
                        observation.model_dump(mode="json"),
                    )
                    observations += 1
                    OBSERVATIONS_TOTAL.labels(
                        source_id,
                        observation.entity_type,
                    ).inc()
                except Exception:
                    await self.session.rollback()
                    raise

            INGESTION_TOTAL.labels(
                source_id,
                "success",
            ).inc()

            return observations

        except Exception:
            INGESTION_TOTAL.labels(
                source_id,
                "error",
            ).inc()

            log.exception(
                "ingestion_failed",
                source=source_id,
            )

            raise

        finally:
            INGESTION_DURATION.labels(source_id).observe(
                __import__("time").perf_counter() - started
            )
