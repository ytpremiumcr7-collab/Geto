from __future__ import annotations

"""DEPRECATED — usar job_scheduler + source_worker. Este path es solo dev sin NATS."""

"""Worker legacy de ingestión directa (sin SourceJob).

Preferir en producción:
  python -m app.workers.job_scheduler
  python -m app.workers.source_worker

Este módulo se mantiene para desarrollo rápido sin NATS jobs.
Cada fuente recibe solo los argumentos que su adapter acepta.
"""


import asyncio
from datetime import datetime, timezone

import structlog

from app.core.config import settings
from app.db.session import SessionLocal
from app.ingestion.pipeline import IngestionPipeline
from app.infrastructure.nats_bus import EventBus
from app.infrastructure.object_store import ObjectStore
from app.sources.registry import create_adapters

log = structlog.get_logger()


def _fetch_kwargs(source_id: str) -> dict:
    if source_id == "opensky":
        return {
            "lamin": settings.default_aoi_south,
            "lomin": settings.default_aoi_west,
            "lamax": settings.default_aoi_north,
            "lomax": settings.default_aoi_east,
        }
    if source_id == "celestrak":
        return {"group": settings.celestrak_group}
    if source_id == "aviation_weather":
        return {"station_ids": "KMCI"}
    if source_id == "copernicus":
        return {"limit": 20}
    return {}


async def run_source(source_id: str, interval: int) -> None:
    adapters = create_adapters()
    adapter = adapters[source_id]
    bus = EventBus()
    await bus.connect()
    object_store = ObjectStore()

    try:
        while True:
            started = datetime.now(timezone.utc)
            try:
                async with SessionLocal() as session:
                    pipeline = IngestionPipeline(
                        session=session,
                        bus=bus,
                        object_store=object_store,
                    )
                    await pipeline.process(adapter, **_fetch_kwargs(source_id))
            except Exception:
                log.exception("source_worker_failed", source=source_id)

            elapsed = (datetime.now(timezone.utc) - started).total_seconds()
            await asyncio.sleep(max(0, interval - elapsed))
    finally:
        await bus.close()


async def main() -> None:
    tasks = [
        run_source("opensky", settings.opensky_interval_seconds),
        run_source("celestrak", settings.celestrak_interval_seconds),
        run_source("usgs_earthquake", settings.usgs_interval_seconds),
        run_source("nasa_firms", settings.firms_interval_seconds),
        run_source("aviation_weather", settings.aviation_weather_interval_seconds),
        run_source("copernicus", settings.copernicus_interval_seconds),
    ]
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
