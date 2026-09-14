"""Alert notifier worker — claims pending deliveries and runs webhook/SMTP/log/NATS."""

from __future__ import annotations

import asyncio
import os
import signal

import structlog
from sqlalchemy import text

from app.alerts.delivery import DeliveryService
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.security_bootstrap import validate_settings
from app.db.session import SessionLocal

log = structlog.get_logger()


class AlertNotifierWorker:
    def __init__(self) -> None:
        self.poll = float(
            os.getenv("ALERT_NOTIFIER_POLL_SECONDS")
            or getattr(settings, "alert_notifier_poll_seconds", 2.0)
        )
        self.batch = int(
            os.getenv("ALERT_NOTIFIER_BATCH_SIZE")
            or getattr(settings, "alert_notifier_batch_size", 20)
        )
        self._running = True
        self.delivery = DeliveryService()

    def stop(self) -> None:
        self._running = False

    async def run(self) -> None:
        log.info("alert_notifier_started", poll=self.poll, batch=self.batch)
        while self._running:
            try:
                await self._tick()
            except Exception:
                log.exception("alert_notifier_tick_failed")
            await asyncio.sleep(self.poll)
        log.info("alert_notifier_stopped")

    async def _tick(self) -> None:
        async with SessionLocal() as session:
            # System tenant for cross-tenant claim (RLS system policy)
            await session.execute(text("SELECT set_config('app.tenant_id', '__system__', true)"))
            claimed = await self.delivery.claim_batch(session, limit=self.batch)
            if not claimed:
                await session.commit()
                return
            for d in claimed:
                # Switch to alert tenant for channel/alert reads under RLS
                await session.execute(
                    text("SELECT set_config('app.tenant_id', :tid, true)"),
                    {"tid": d.tenant_id},
                )
                try:
                    result = await self.delivery.process_one(session, d)
                    log.info(
                        "alert_delivery_processed",
                        delivery_id=result.get("id"),
                        status=result.get("status"),
                        channel_type=result.get("channel_type"),
                        attempts=result.get("attempts"),
                    )
                except Exception as e:
                    log.exception("alert_delivery_failed", delivery_id=str(d.id))
                    d.status = "pending"
                    d.last_error = str(e)[:2000]
                    d.attempts = (d.attempts or 0) + 1
            await session.execute(text("SELECT set_config('app.tenant_id', '__system__', true)"))
            await session.commit()


async def main() -> None:
    configure_logging(settings.log_level)
    validate_settings(settings, role="alert-notifier")
    worker = AlertNotifierWorker()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, worker.stop)
        except NotImplementedError:
            pass
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
