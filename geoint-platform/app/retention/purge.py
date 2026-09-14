"""Purge de observations antiguas y raw en MinIO según settings."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import delete, text

from app.core.config import settings
from app.core.logging import configure_logging
from app.db.models import Observation
from app.db.session import SessionLocal
from app.infrastructure.object_store import ObjectStore

log = structlog.get_logger()


async def purge_observations() -> int:
    days = settings.observations_retention_days
    if days <= 0:
        return 0
    cutoff = datetime.now(UTC) - timedelta(days=days)
    async with SessionLocal() as session:
        # Bypass RLS for maintenance: set tenant wildcard not possible;
        # use table owner connection — purge all tenants older than cutoff.
        await session.execute(text("SET LOCAL row_security = off"))
        result = await session.execute(delete(Observation).where(Observation.observed_at < cutoff))
        await session.commit()
        count = result.rowcount or 0
        log.info("purge_observations", deleted=count, cutoff=cutoff.isoformat())
        return count


async def purge_minio_raw_prefix_hint() -> None:
    """MinIO lifecycle es preferible en prod; aquí solo log de política."""
    days = settings.raw_payload_retention_days
    log.info(
        "raw_retention_policy",
        days=days,
        note="Configure MinIO bucket lifecycle for geoint-raw prefix",
    )
    _ = ObjectStore  # dependency present for future list/delete by date prefix


async def run_once() -> None:
    await purge_observations()
    await purge_minio_raw_prefix_hint()


async def main() -> None:
    configure_logging(settings.log_level)
    interval = max(3600, int(getattr(settings, "purge_interval_seconds", 86400) or 86400))
    while True:
        try:
            await run_once()
        except Exception:
            log.exception("purge_failed")
        await asyncio.sleep(interval)


if __name__ == "__main__":
    asyncio.run(main())
