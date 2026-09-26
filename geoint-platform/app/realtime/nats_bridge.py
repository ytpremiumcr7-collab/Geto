"""NATS → WebSocket fan-out for tenant-scoped product events and alerts."""

from __future__ import annotations

import asyncio
import json

import nats
import structlog
from nats.aio.client import Client as NATSClient
from nats.aio.msg import Msg

from app.core.config import settings
from app.realtime.manager import manager

log = structlog.get_logger()


class RealtimeNatsBridge:
    def __init__(self) -> None:
        self.nc: NATSClient | None = None
        self._running = False

    async def _handle_message(self, msg: Msg) -> None:
        try:
            payload = json.loads(msg.data.decode())
            tenant_id = str(
                payload.get("tenant_id") or self._tenant_from_subject(msg.subject) or "default"
            )
            await manager.publish(
                tenant_id,
                {
                    "type": payload.get("event_type") or "event",
                    **payload,
                },
            )
        except Exception:
            log.exception("realtime_bridge_handle_failed", subject=msg.subject)

    async def start(self) -> None:
        nc = await nats.connect(settings.nats_url, name="geoint-realtime-api")
        self.nc = nc
        self._running = True

        await nc.subscribe("geoint.event.>", cb=self._handle_message)
        await nc.subscribe("geoint.alert.>", cb=self._handle_message)
        log.info(
            "realtime_bridge_subscribed",
            subjects=["geoint.event.>", "geoint.alert.>"],
        )

        while self._running:
            await asyncio.sleep(1)

    @staticmethod
    def _tenant_from_subject(subject: str) -> str | None:
        # geoint.event.{tenant_id} / geoint.alert.{tenant_id}
        parts = subject.split(".")
        if len(parts) >= 3:
            return parts[2]
        return None

    def stop(self) -> None:
        self._running = False

    async def close(self) -> None:
        self.stop()
        if self.nc:
            await self.nc.drain()
