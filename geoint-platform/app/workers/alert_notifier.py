"""Alert notifier worker — claims pending deliveries and runs webhook/SMTP/log/NATS.

Ops: exposes HTTP health on ALERT_NOTIFIER_HEALTH_PORT (default 8081):
  GET /health/live   — process up
  GET /health/ready  — recent successful tick + DB reachable
Writes heartbeat file for Docker HEALTHCHECK without curl in image.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import socket
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import structlog

from app.alerts.delivery import DeliveryService
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.security_bootstrap import validate_settings
from app.db.tenant import system_worker_session, tenant_session

log = structlog.get_logger()

HEARTBEAT_PATH = Path(
    os.getenv("ALERT_NOTIFIER_HEARTBEAT_PATH", "/tmp/geoint_alert_notifier_heartbeat")
)


class AlertNotifierWorker:
    def __init__(self) -> None:
        self.poll = float(
            os.getenv("ALERT_NOTIFIER_POLL_SECONDS")
            or settings.alert_notifier_poll_seconds
        )
        self.batch = int(
            os.getenv("ALERT_NOTIFIER_BATCH_SIZE")
            or settings.alert_notifier_batch_size
        )
        self.health_port = int(os.getenv("ALERT_NOTIFIER_HEALTH_PORT", "8081"))
        self.lease_seconds = int(
            os.getenv("ALERT_NOTIFIER_LEASE_SECONDS")
            or settings.alert_notifier_lease_seconds
        )
        self.worker_id = os.getenv("ALERT_NOTIFIER_WORKER_ID") or (
            f"{socket.gethostname()}-{os.getpid()}-{uuid4().hex[:8]}"
        )
        self.ready_max_age_s = float(os.getenv("ALERT_NOTIFIER_READY_MAX_AGE_S", "30"))
        self._running = True
        self.delivery = DeliveryService()
        self._last_tick_ok_at: float | None = None
        self._last_tick_error: str | None = None
        self._ticks = 0
        self._deliveries_ok = 0
        self._deliveries_fail = 0

    def stop(self) -> None:
        self._running = False

    def _write_heartbeat(self, ready: bool) -> None:
        try:
            payload = {
                "ts": datetime.now(UTC).isoformat(),
                "ready": ready,
                "ticks": self._ticks,
                "deliveries_ok": self._deliveries_ok,
                "deliveries_fail": self._deliveries_fail,
                "last_error": self._last_tick_error,
            }
            HEARTBEAT_PATH.write_text(json.dumps(payload), encoding="utf-8")
        except Exception:
            log.warning("alert_notifier_heartbeat_write_failed")

    def _ready(self) -> bool:
        if self._last_tick_ok_at is None:
            return False
        return (time.monotonic() - self._last_tick_ok_at) <= self.ready_max_age_s

    async def _handle_health(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            req = await asyncio.wait_for(reader.read(1024), timeout=2.0)
            line = req.decode("utf-8", errors="ignore").split("\r\n")[0]
            path = line.split(" ")[1] if " " in line else "/"
            if path.startswith("/health/ready"):
                ok = self._ready()
                body = {
                    "status": "ready" if ok else "not_ready",
                    "last_tick_ok_at": self._last_tick_ok_at,
                    "ticks": self._ticks,
                    "deliveries_ok": self._deliveries_ok,
                    "deliveries_fail": self._deliveries_fail,
                    "last_error": self._last_tick_error,
                }
                status = 200 if ok else 503
            else:
                body = {"status": "live", "worker": "alert_notifier"}
                status = 200
            raw = json.dumps(body).encode()
            writer.write(
                f"HTTP/1.1 {status} OK\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(raw)}\r\n"
                f"Connection: close\r\n\r\n".encode()
                + raw
            )
            await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def _run_health_server(self) -> None:
        server = await asyncio.start_server(self._handle_health, "0.0.0.0", self.health_port)
        log.info("alert_notifier_health_listen", port=self.health_port)
        async with server:
            await server.serve_forever()

    async def run(self) -> None:
        log.info("alert_notifier_started", poll=self.poll, batch=self.batch)
        health_task = asyncio.create_task(self._run_health_server())
        try:
            while self._running:
                try:
                    await self._tick()
                    self._last_tick_ok_at = time.monotonic()
                    self._last_tick_error = None
                    self._ticks += 1
                    self._write_heartbeat(True)
                except Exception as e:
                    self._last_tick_error = str(e)[:500]
                    self._write_heartbeat(False)
                    log.exception("alert_notifier_tick_failed")
                await asyncio.sleep(self.poll)
        finally:
            health_task.cancel()
            try:
                await health_task
            except asyncio.CancelledError:
                pass
            log.info("alert_notifier_stopped")

    async def _tick(self) -> None:
        async with system_worker_session() as session:
            claimed = await self.delivery.claim_batch(
                session,
                worker_id=self.worker_id,
                limit=self.batch,
                lease_seconds=self.lease_seconds,
            )
            await session.commit()

        for claim in claimed:
            try:
                async with tenant_session(claim.tenant_id) as session:
                    result = await self.delivery.process_one(
                        session,
                        delivery_id=claim.id,
                        worker_id=self.worker_id,
                    )
                    await session.commit()
                status = result.get("status")
                if status == "delivered":
                    self._deliveries_ok += 1
                elif status == "failed":
                    self._deliveries_fail += 1
                log.info(
                    "alert_delivery_processed",
                    delivery_id=result.get("id"),
                    status=status,
                    channel_type=result.get("channel_type"),
                    attempts=result.get("attempts"),
                )
            except Exception:
                # The persisted sending lease is intentionally left intact.
                # A later worker can reclaim it after lease expiry.
                self._deliveries_fail += 1
                log.exception(
                    "alert_delivery_one_failed",
                    delivery_id=str(claim.id),
                    worker_id=self.worker_id,
                )


async def _amain() -> None:
    configure_logging()
    validate_settings(settings, role="worker")
    worker = AlertNotifierWorker()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, worker.stop)
        except NotImplementedError:
            pass

    await worker.run()


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    import os

    os.environ.setdefault("GEOINT_SYSTEM_WORKER", "1")
    main()
