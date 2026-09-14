import json

import nats
from nats.js import JetStreamContext

from app.core.config import settings


class EventBus:
    def __init__(self):
        self.nc = None
        self.js: JetStreamContext | None = None

    async def connect(self):
        self.nc = await nats.connect(settings.nats_url)
        self.js = self.nc.jetstream()

        try:
            await self.js.stream_info(settings.nats_stream)
        except Exception:
            await self.js.add_stream(
                name=settings.nats_stream,
                subjects=[
                    "geoint.observation.>",
                    "geoint.event.>",
                    "geoint.ingestion.>",
                ],
                max_age=settings.nats_max_age_seconds,
            )

    async def publish(
        self,
        subject: str,
        payload: dict,
    ):
        if not self.js:
            raise RuntimeError("NATS is not connected")

        await self.js.publish(
            subject,
            json.dumps(
                payload,
                default=str,
            ).encode(),
        )

    async def close(self):
        if self.nc:
            await self.nc.drain()
