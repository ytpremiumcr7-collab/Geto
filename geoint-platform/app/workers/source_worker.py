"""Worker JetStream: durable consumer + AckWait + MaxDeliver + idempotencia + DLQ."""

from __future__ import annotations

import asyncio
import json
import os
from uuid import UUID

import nats
import structlog
from nats.aio.client import Client as NATSClient
from nats.aio.msg import Msg
from nats.js import JetStreamContext
from nats.js.api import AckPolicy, ConsumerConfig, DeliverPolicy

from app.core.config import settings
from app.core.logging import configure_logging
from app.db.models_dlq import DlqMessage
from app.db.tenant import system_worker_session, tenant_session
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
        self.nc: NATSClient | None = None
        self.js: JetStreamContext | None = None
        self.dispatcher = SourceDispatcher()
        self.jobs = JobRepository()
        self.idempotency = IdempotencyRepository()
        self.dlq = JetStreamClient()
        self._running = True

    async def start(self) -> None:
        nc = await nats.connect(self.nats_url, name="geoint-source-worker")
        js = nc.jetstream()
        self.nc = nc
        self.js = js
        await self.dlq.connect()

        # Asegurar stream de jobs (idempotente)
        try:
            await js.stream_info(settings.nats_stream)
        except Exception:
            from nats.js.api import RetentionPolicy, StorageType, StreamConfig

            await js.add_stream(
                StreamConfig(
                    name=settings.nats_stream,
                    subjects=[
                        f"{JOBS_PREFIX}.>",
                        "geoint.observation.>",
                        "geoint.event.>",
                        "geoint.alert.>",
                        "geoint.ingestion.>",
                    ],
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

        sub = await js.pull_subscribe(
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

        try:
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
        finally:
            await self.dlq.close()
            if self.nc is not None:
                await self.nc.drain()
            self.nc = None
            self.js = None
            log.info("worker_stopped")

    async def _heartbeat_execution(
        self,
        msg: Msg,
        *,
        tenant_id: str,
        job_id: UUID,
        execution_id: UUID,
        message_id: str,
        worker_id: str,
    ) -> None:
        """Renew broker and database leases while a source execution is alive."""
        interval = max(5.0, min(float(self.ack_wait) / 3.0, 30.0))
        lease_seconds = max(self.ack_wait * 3, 180)
        while True:
            await asyncio.sleep(interval)
            try:
                await msg.in_progress()
                async with tenant_session(tenant_id) as session:
                    await self.jobs.renew_execution_lease(
                        session,
                        job_id,
                        execution_id=execution_id,
                        worker_id=worker_id,
                        lease_seconds=lease_seconds,
                    )
                async with system_worker_session() as session:
                    await self.idempotency.renew_claim(
                        session,
                        tenant_id=tenant_id,
                        message_id=message_id,
                        worker_id=worker_id,
                        lease_seconds=lease_seconds,
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning(
                    "execution_heartbeat_failed",
                    job_id=str(job_id),
                    execution_id=str(execution_id),
                    error=str(exc)[:300],
                )

    async def handle(self, msg: Msg) -> None:
        delivery = int(msg.metadata.num_delivered) if msg.metadata else 1
        subject = msg.subject
        message_id: str | None = None

        try:
            headers = msg.headers or {}
            message_id = headers.get("Nats-Msg-Id") or headers.get("nats-msg-id")
            payload = json.loads(msg.data.decode())
            job_id = UUID(payload["job_id"])
            source_id = payload["source_id"]
            job_type = payload.get("job_type", "poll")
            config = payload.get("config") or {}
            tenant_id = payload.get("tenant_id") or "default"
            execution_id = UUID(str(payload.get("execution_id") or message_id or job_id))
            if not message_id:
                message_id = str(execution_id)

            worker_id = f"{self.durable}:{os.getpid()}"
            claim_lease = max(self.ack_wait * 3, 180)
            async with system_worker_session() as session:
                claim = await self.idempotency.try_claim(
                    session,
                    tenant_id=tenant_id,
                    message_id=message_id,
                    subject=subject,
                    source_id=source_id,
                    worker_id=worker_id,
                    lease_seconds=claim_lease,
                )

            if claim == "completed":
                # Crash recovery may republish an execution after its side effects
                # and idempotency record committed but before SourceJob was reset.
                async with tenant_session(tenant_id) as session:
                    await self.jobs.mark_success(
                        session,
                        job_id,
                        execution_id=execution_id,
                    )
                log.info(
                    "already_processed",
                    message_id=message_id,
                    execution_id=str(execution_id),
                )
                await msg.ack()
                return

            if claim == "busy":
                # Another delivery owns a live processing lease. Do not burn
                # MaxDeliver with immediate NAKs; extend broker time and return.
                log.info("claim_busy", message_id=message_id)
                await msg.in_progress()
                return

            async with tenant_session(tenant_id) as session:
                await self.jobs.renew_execution_lease(
                    session,
                    job_id,
                    execution_id=execution_id,
                    worker_id=worker_id,
                    lease_seconds=claim_lease,
                )

            heartbeat = asyncio.create_task(
                self._heartbeat_execution(
                    msg,
                    tenant_id=tenant_id,
                    job_id=job_id,
                    execution_id=execution_id,
                    message_id=message_id,
                    worker_id=worker_id,
                )
            )
            try:
                async with tenant_session(tenant_id) as session:
                    await self.dispatcher.execute(
                        session,
                        source_id=source_id,
                        job_type=job_type,
                        config=config,
                        tenant_id=tenant_id,
                        job_id=str(job_id),
                        message_id=message_id,
                    )

                # Mark the execution durable before advancing the recurring
                # schedule. If the process dies between these commits, a
                # republished identical execution completes only the job state.
                async with system_worker_session() as session:
                    await self.idempotency.mark_completed(
                        session,
                        tenant_id=tenant_id,
                        message_id=message_id,
                        worker_id=worker_id,
                    )
                async with tenant_session(tenant_id) as session:
                    await self.jobs.mark_success(
                        session,
                        job_id,
                        execution_id=execution_id,
                    )
                await msg.ack()
                log.info(
                    "job_ok",
                    job_id=str(job_id),
                    execution_id=str(execution_id),
                    source=source_id,
                    delivery=delivery,
                )
            except Exception:
                async with system_worker_session() as session:
                    await self.idempotency.mark_failed(
                        session,
                        tenant_id=tenant_id,
                        message_id=message_id,
                        worker_id=worker_id,
                    )
                raise
            finally:
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)

        except Exception as exc:
            log.exception("job_failed", delivery=delivery, subject=subject)

            if delivery >= self.max_deliver:
                try:
                    body = json.loads(msg.data.decode()) if msg.data else {}
                    source_id = body.get("source_id", "unknown")
                    dlq_tenant_id = body.get("tenant_id") or "default"
                    job_id_raw = body.get("job_id")
                    execution_raw = body.get("execution_id") or message_id or job_id_raw

                    await self.dlq.publish_dlq(
                        source_id=source_id,
                        original_subject=subject,
                        payload=body,
                        error=str(exc),
                        delivery_count=delivery,
                    )
                    async with tenant_session(dlq_tenant_id) as session:
                        session.add(
                            DlqMessage(
                                tenant_id=dlq_tenant_id,
                                source_id=source_id,
                                original_subject=subject,
                                payload=body,
                                error=str(exc),
                                delivery_count=delivery,
                                status="open",
                            )
                        )
                        await session.commit()

                    if job_id_raw and execution_raw:
                        async with tenant_session(dlq_tenant_id) as session:
                            await self.jobs.mark_failure(
                                session,
                                UUID(str(job_id_raw)),
                                str(exc),
                                execution_id=UUID(str(execution_raw)),
                                terminal=True,
                            )
                except Exception:
                    log.exception("dlq_publish_failed")
                await msg.ack()
                return

            # JetStream owns delivery retries for this execution. SourceJob stays
            # attached to the same execution_id; the scheduler must not create a
            # parallel retry while the broker is redelivering it.
            await msg.nak()

    def stop(self) -> None:
        self._running = False


async def main() -> None:
    import os

    os.environ.setdefault("GEOINT_SYSTEM_WORKER", "1")
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
