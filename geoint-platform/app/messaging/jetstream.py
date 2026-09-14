"""Publicación JetStream con Nats-Msg-Id para deduplicación de publicación."""

from __future__ import annotations

import json
from datetime import UTC
from typing import Any
from uuid import UUID

import nats
from nats.js import JetStreamContext
from nats.js.api import RetentionPolicy, StorageType, StreamConfig

from app.core.config import settings
from app.messaging.subjects import DLQ_PREFIX, JOBS_PREFIX


class JetStreamClient:
    def __init__(self, url: str | None = None):
        self.url = url or settings.nats_url
        self.nc = None
        self.js: JetStreamContext | None = None

    async def connect(self) -> None:
        self.nc = await nats.connect(self.url, name="geoint-js")
        self.js = self.nc.jetstream()
        await self.ensure_streams()

    async def ensure_streams(self) -> None:
        assert self.js is not None
        for cfg in (
            StreamConfig(
                name=settings.nats_stream,
                subjects=[
                    f"{JOBS_PREFIX}.>",
                    "geoint.observation.>",
                    "geoint.event.>",
                ],
                retention=RetentionPolicy.LIMITS,
                storage=StorageType.FILE,
                max_age=settings.nats_max_age_seconds,
            ),
            StreamConfig(
                name=f"{settings.nats_stream}_DLQ",
                subjects=[f"{DLQ_PREFIX}.>"],
                retention=RetentionPolicy.LIMITS,
                storage=StorageType.FILE,
                max_age=30 * 24 * 3600,
            ),
        ):
            try:
                await self.js.stream_info(cfg.name)
                await self.js.update_stream(cfg)
            except Exception:
                await self.js.add_stream(cfg)

    async def publish_job(
        self,
        *,
        job_id: UUID,
        source_id: str,
        job_type: str,
        config: dict[str, Any],
        tenant_id: str = "default",
    ) -> None:
        assert self.js is not None
        payload = {
            "job_id": str(job_id),
            "source_id": source_id,
            "job_type": job_type,
            "config": config or {},
            "tenant_id": tenant_id,
        }
        subject = f"{JOBS_PREFIX}.{source_id}"
        await self.js.publish(
            subject,
            json.dumps(payload, default=str).encode(),
            headers={"Nats-Msg-Id": str(job_id)},
        )

    async def publish_dlq(
        self,
        *,
        source_id: str,
        original_subject: str,
        payload: dict[str, Any],
        error: str,
        delivery_count: int,
    ) -> None:
        assert self.js is not None
        from datetime import datetime

        message = {
            "failed_at": datetime.now(UTC).isoformat(),
            "source_id": source_id,
            "original_subject": original_subject,
            "delivery_count": delivery_count,
            "error": error,
            "payload": payload,
        }
        await self.js.publish(
            f"{DLQ_PREFIX}.{source_id}",
            json.dumps(message, default=str).encode(),
        )

    async def close(self) -> None:
        if self.nc:
            await self.nc.drain()
