"""Worker JetStream: durable consumer + AckWait + MaxDeliver + idempotencia + DLQ."""

from __future__ import annotations

import asyncio
import json
import os
from uuid import UUID

import nats
import structlog
from nats.aio.msg import Msg
from nats.js.api import AckPolicy, ConsumerConfig, DeliverPolicy

from app.core.config import settings
from app.core.logging import configure_logging
from app.db.models_dlq import DlqMessage
from app.db.session import SessionLocal
from app.ingestion.dispatcher import SourceDispatcher
from app.jobs.repository import IdempotencyRepository, JobRepository
from app.messaging.jetstream import JetStreamClient
from app.messaging.subjects import JOBS_PREFIX

log = structlog.get_logger()


class SourceWorker:
    def __init__(self) -> None:
        self.nats_url = settings.nats_url
        self.durable = os.getenv("NATS_DURABLE", "geoint-source-workers")
        self.queue = os.getenv("NATS_QUEUE_GROUP", "geoint-workers")
        self.ack_wait = int(os.getenv("NATS_ACK_WAIT_SECONDS", "60"))
        self.max_deliver = int(os.getenv("NATS_MAX_DELIVER", "5"))
        self.nc = None
        self.js = None
        self.dispatcher = SourceDispatcher()
        self.jobs = JobRepository()
        self.idempotency = IdempotencyRepository()
        self.dlq = JetStreamClient()
        self._running = True

    async def start(self) -> None:
        self.nc = await nats.connect(self.nats_url, name="geoint-source-worker")
        self.js = self.nc.jetstream()
        await self.dlq.connect()

        # Asegurar stream de jobs (idempotente)
        try:
            await self.js.stream_info(settings.nats_stream)
        except Exception:
            from nats.js.api import RetentionPolicy, StorageType, StreamConfig

            await self.js.add_stream(
                StreamConfig(
                    name=settings.nats_stream,
                    subjects=[f"{JOBS_PREFIX}.>", "geoint.observation.>", "geoint.event.>"],
                    retention=RetentionPolicy.LIMITS,
                    storage=StorageType.FILE,
                    max_age=settings.nats_max_age_seconds,
                )
            )

        # Consumer durable + queue + límites de entrega
        config = ConsumerConfig(
            durable_name=self.durable,
            deliver_policy=DeliverPolicy.ALL,
            ack_policy=AckPolicy.EXPLICIT,
            ack_wait=self.ack_wait,
            max_deliver=self.max_deliver,
            filter_subject=f"{JOBS_PREFIX}.>",
        )

        sub = await self.js.pull_subscribe(
            subject=f"{JOBS_PREFIX}.>",
            durable=self.durable,
            config=config,
        )

        log.info(
            "worker_started",
            durable=self.durable,
            queue=self.queue,
            ack_wait=self.ack_wait,
            max_deliver=self.max_deliver,
        )

        while self._running:
            try:
                messages = await sub.fetch(batch=5, timeout=5)
            except nats.errors.TimeoutError:
                continue
            except Exception:
                log.exception("fetch_failed")
                await asyncio.sleep(1)
                continue

            for msg in messages:
                await self.handle(msg)

    async def handle(self, msg: Msg) -> None:
        delivery = int(msg.metadata.num_delivered) if msg.metadata else 1
        subject = msg.subject
        message_id = None

        try:
            headers = msg.headers or {}
            message_id = headers.get("Nats-Msg-Id") or headers.get("nats-msg-id")
            payload = json.loads(msg.data.decode())
            job_id = UUID(payload["job_id"])
            source_id = payload["source_id"]
            job_type = payload.get("job_type", "poll")
            config = payload.get("config") or {}
            tenant_id = payload.get("tenant_id") or "default"

            if not message_id:
                message_id = str(job_id)

            # Atomic claim BEFORE side effects (processing lease)
            worker_id = f"{self.durable}:{os.getpid()}"
            async with SessionLocal() as session:
                claim = await self.idempotency.try_claim(
                    session,
                    message_id=message_id,
                    subject=subject,
                    source_id=source_id,
                    worker_id=worker_id,
                    lease_seconds=max(self.ack_wait * 2, 120),
                )
            if claim == "completed":
                log.info("already_processed", message_id=message_id)
                await msg.ack()
                return
            if claim == "busy":
                log.info("claim_busy", message_id=message_id)
                await msg.nak()
                return

            # We own the lease — execute side effects
            try:
                async with SessionLocal() as session:
                    await self.dispatcher.execute(
                        session,
                        source_id=source_id,
                        job_type=job_type,
                        config=config,
                        tenant_id=tenant_id,
                        job_id=str(job_id),
                        message_id=message_id,
                    )
                    await self.jobs.mark_success(session, job_id)
                async with SessionLocal() as session:
                    await self.idempotency.mark_completed(
                        session, message_id=message_id, worker_id=worker_id
                    )
                await msg.ack()
                log.info("job_ok", job_id=str(job_id), source=source_id, delivery=delivery)
            except Exception:
                async with SessionLocal() as session:
                    await self.idempotency.mark_failed(
                        session, message_id=message_id, worker_id=worker_id
                    )
                raise

        except Exception as exc:
            log.exception("job_failed", delivery=delivery, subject=subject)

            # MaxDeliver alcanzado → DLQ + ACK (no redelivery infinita)
            if delivery >= self.max_deliver:
                try:
                    body = json.loads(msg.data.decode()) if msg.data else {}
                    source_id = body.get("source_id", "unknown")
                    await self.dlq.publish_dlq(
                        source_id=source_id,
                        original_subject=subject,
                        payload=body,
                        error=str(exc),
                        delivery_count=delivery,
                    )
                    async with SessionLocal() as session:
                        session.add(
                            DlqMessage(
                                tenant_id=body.get("tenant_id") or "default",
                                source_id=source_id,
                                original_subject=subject,
                                payload=body,
                                error=str(exc),
                                delivery_count=delivery,
                                status="open",
                            )
                        )
                        await session.commit()
                    job_id_raw = body.get("job_id")
                    if job_id_raw:
                        async with SessionLocal() as session:
                            await self.jobs.mark_failure(session, UUID(job_id_raw), str(exc))
                except Exception:
                    log.exception("dlq_publish_failed")
                await msg.ack()
                return

            # Reintento
            try:
                body = json.loads(msg.data.decode()) if msg.data else {}
                if body.get("job_id"):
                    async with SessionLocal() as session:
                        await self.jobs.mark_failure(session, UUID(body["job_id"]), str(exc))
            except Exception:
                pass
            await msg.nak()

    def stop(self) -> None:
        self._running = False


async def main() -> None:
    import signal

    configure_logging(settings.log_level)
    from app.core.security_bootstrap import validate_settings

    validate_settings(settings, role="worker")
    worker = SourceWorker()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, worker.stop)
        except NotImplementedError:
            pass
    await worker.start()


if __name__ == "__main__":
    asyncio.run(main())
