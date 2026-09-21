"""Puente NATS → WebSocket: cada instancia API se suscribe a geoint.event.>

Así el evento publicado por worker/outbox llega a sockets en cualquier réplica.
"""

from __future__ import annotations

import asyncio
import json

import nats
import structlog
from nats.aio.client import Client as NATSClient

from app.core.config import settings
from app.realtime.manager import manager

log = structlog.get_logger()


class RealtimeNatsBridge:
    def __init__(self) -> None:
        self.nc: NATSClient | None = None
        self._running = False

    async def start(self) -> None:
        nc = await nats.connect(settings.nats_url, name="geoint-realtime-api")
        self.nc = nc
        self._running = True

        # Stream de eventos ya asegurado por JetStreamClient; suscripción push simple
        sub = await nc.subscribe("geoint.event.>")
        log.info("realtime_bridge_subscribed", subject="geoint.event.>")

        while self._running:
            try:
                msg = await sub.next_msg(timeout=1)
            except nats.errors.TimeoutError:
                continue
            except Exception:
                log.exception("realtime_bridge_recv_failed")
                await asyncio.sleep(1)
                continue

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
                log.exception("realtime_bridge_handle_failed")

    @staticmethod
    def _tenant_from_subject(subject: str) -> str | None:
        # geoint.event.{tenant_id}
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
