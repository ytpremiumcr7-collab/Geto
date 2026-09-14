"""Publica outbox → NATS. At-least-once; consumidores deben ser idempotentes."""

from __future__ import annotations

import asyncio
import json

import structlog

from app.db.session import SessionLocal
from app.messaging.jetstream import JetStreamClient
from app.outbox.repository import OutboxRepository

log = structlog.get_logger()


class OutboxDispatcher:
    def __init__(
        self,
        batch_size: int = 50,
        interval: float = 1.0,
    ):
        self.batch_size = batch_size
        self.interval = interval
        self.repo = OutboxRepository()
        self.js = JetStreamClient()
        self._running = False

    async def run(self) -> None:
        await self.js.connect()
        self._running = True
        log.info("outbox_dispatcher_started")
        try:
            while self._running:
                try:
                    await self.process_batch()
                except Exception:
                    log.exception("outbox_batch_failed")
                await asyncio.sleep(self.interval)
        finally:
            await self.js.close()

    async def process_batch(self) -> None:
        async with SessionLocal() as session:
            messages = await self.repo.claim(session, self.batch_size)
            for message in messages:
                try:
                    assert self.js.js is not None
                    await self.js.js.publish(
                        message.subject,
                        json.dumps(message.payload, default=str).encode(),
                    )
                    await self.repo.mark_published(session, message)
                except Exception as exc:
                    await self.repo.mark_failed(message, str(exc))
                    log.warning(
                        "outbox_publish_failed",
                        message_id=str(message.id),
                        error=str(exc),
                    )
            await session.commit()

    def stop(self) -> None:
        self._running = False


async def main() -> None:
    from app.core.config import settings
    from app.core.logging import configure_logging
    from app.core.security_bootstrap import validate_settings

    configure_logging(settings.log_level)
    validate_settings(settings, role="outbox")
    dispatcher = OutboxDispatcher()
    await dispatcher.run()


if __name__ == "__main__":
    asyncio.run(main())
