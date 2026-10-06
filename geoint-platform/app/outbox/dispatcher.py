"""Publica outbox → NATS. At-least-once; consumidores deben ser idempotentes."""

from __future__ import annotations

import asyncio
import json
import os
import socket
from uuid import UUID

import structlog

from app.db.tenant import system_worker_session
from app.jobs.repository import JobRepository
from app.messaging.jetstream import JetStreamClient
from app.messaging.subjects import JOBS_PREFIX
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
        self.jobs = JobRepository()
        self.js = JetStreamClient()
        self.worker_id = os.getenv("OUTBOX_WORKER_ID") or f"{socket.gethostname()}-{os.getpid()}"
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
        from app.core.config import settings

        async with system_worker_session() as session:
            messages = await self.repo.claim(
                session,
                worker_id=self.worker_id,
                limit=self.batch_size,
                lease_seconds=settings.outbox_lease_seconds,
            )

        # Network I/O intentionally happens after claim() committed and released
        # row locks. Completion/failure bookkeeping uses separate short TXs.
        for message in messages:
            try:
                if message.subject == "geoint.analytics.observations":
                    from app.analytics.clickhouse import ClickHouseSink

                    payload = message.payload or {}
                    rows = payload.get("rows") or []
                    tenant_id = payload.get("tenant_id") or message.tenant_id
                    if rows:
                        await ClickHouseSink().write_observations(rows, tenant_id=tenant_id)
                    log.info(
                        "clickhouse_outbox_written",
                        message_id=str(message.id),
                        rows=len(rows),
                    )
                else:
                    assert self.js.js is not None
                    payload = message.payload or {}
                    dedupe_key = str(message.id)
                    if message.subject.startswith("geoint.jobs."):
                        execution_id = payload.get("execution_id")
                        if not execution_id:
                            raise ValueError(
                                f"job dispatch outbox {message.id} has no execution_id"
                            )
                        dedupe_key = str(execution_id)
                    await self.js.js.publish(
                        message.subject,
                        json.dumps(payload, default=str).encode(),
                        headers={"Nats-Msg-Id": dedupe_key},
                    )

                async with system_worker_session() as session:
                    await self.repo.mark_published(
                        session,
                        message_id=message.id,
                        worker_id=self.worker_id,
                    )
            except Exception as exc:
                async with system_worker_session() as session:
                    outcome = await self.repo.persist_failure(
                        session,
                        message_id=message.id,
                        worker_id=self.worker_id,
                        error=str(exc),
                        max_attempts=settings.outbox_max_attempts,
                        base_backoff_seconds=settings.outbox_base_backoff_seconds,
                        commit=False,
                    )
                    if outcome == "dead_lettered" and message.subject.startswith(f"{JOBS_PREFIX}."):
                        payload = message.payload or {}
                        job_id_raw = payload.get("job_id")
                        execution_id_raw = payload.get("execution_id")
                        if job_id_raw and execution_id_raw:
                            try:
                                await self.jobs.mark_failure(
                                    session,
                                    UUID(str(job_id_raw)),
                                    str(exc),
                                    execution_id=UUID(str(execution_id_raw)),
                                    commit=False,
                                )
                            except (TypeError, ValueError):
                                log.error(
                                    "job_dispatch_dead_letter_invalid_identity",
                                    message_id=str(message.id),
                                    job_id=str(job_id_raw),
                                    execution_id=str(execution_id_raw),
                                )
                    await session.commit()
                log.warning(
                    "outbox_publish_failed",
                    message_id=str(message.id),
                    error=str(exc),
                )

    def stop(self) -> None:
        self._running = False


async def main() -> None:
    from app.core.config import settings
    from app.core.logging import configure_logging
    from app.core.security_bootstrap import validate_settings

    configure_logging(settings.log_level)
    os.environ.setdefault("GEOINT_SYSTEM_WORKER", "1")
    validate_settings(settings, role="outbox")
    dispatcher = OutboxDispatcher()
    await dispatcher.run()


if __name__ == "__main__":
    asyncio.run(main())
