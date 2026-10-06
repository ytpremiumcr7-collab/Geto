"""Scheduler de SourceJobs: DB claim + transactional dispatch outbox."""

from __future__ import annotations

import asyncio
import os
import signal
import socket
from uuid import uuid4

import structlog

from app.core.config import settings
from app.core.logging import configure_logging
from app.db.tenant import system_worker_session
from app.jobs.repository import JobRepository
from app.messaging.subjects import JOBS_PREFIX
from app.outbox.repository import OutboxRepository

log = structlog.get_logger()


class JobScheduler:
    def __init__(
        self,
        poll_interval: float | None = None,
        lease_seconds: int | None = None,
    ):
        self.poll_interval = poll_interval or float(os.getenv("JOB_POLL_INTERVAL_SECONDS", "2"))
        self.lease_seconds = lease_seconds or int(os.getenv("JOB_LEASE_SECONDS", "120"))
        self.worker_id = os.getenv("WORKER_ID") or (
            f"{socket.gethostname()}-{os.getpid()}-{uuid4().hex[:8]}"
        )
        self.repo = JobRepository()
        self.outbox = OutboxRepository()
        self._running = False

    async def run(self) -> None:
        self._running = True
        log.info("scheduler_started", worker_id=self.worker_id)
        while self._running:
            try:
                await self.tick()
            except Exception:
                log.exception("scheduler_tick_failed")
            await asyncio.sleep(self.poll_interval)

    async def tick(self) -> None:
        """Atomically claim schedules and create durable broker-dispatch intents."""
        async with system_worker_session() as session:
            jobs = await self.repo.claim_due_jobs(
                session,
                worker_id=self.worker_id,
                lease_seconds=self.lease_seconds,
            )

            for job in jobs:
                if job.execution_id is None:
                    raise RuntimeError(f"claimed job {job.id} has no execution_id")
                tenant_id = getattr(job, "tenant_id", None) or "default"
                await self.outbox.enqueue(
                    session,
                    subject=f"{JOBS_PREFIX}.{job.source_id}",
                    payload={
                        "job_id": str(job.id),
                        "execution_id": str(job.execution_id),
                        "source_id": job.source_id,
                        "job_type": job.job_type,
                        "config": job.config or {},
                        "tenant_id": tenant_id,
                    },
                    tenant_id=tenant_id,
                )
                log.info(
                    "job_dispatch_enqueued",
                    job_id=str(job.id),
                    execution_id=str(job.execution_id),
                    source=job.source_id,
                    tenant_id=tenant_id,
                )

            # SourceJob state and all job-dispatch outbox rows become durable
            # together. There is no scheduler DB->NATS crash window anymore.
            await session.commit()

    def stop(self) -> None:
        self._running = False


async def main() -> None:
    os.environ.setdefault("GEOINT_SYSTEM_WORKER", "1")
    configure_logging(settings.log_level)
    from app.core.security_bootstrap import validate_settings

    validate_settings(settings, role="scheduler")
    scheduler = JobScheduler()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, scheduler.stop)
        except NotImplementedError:
            pass
    await scheduler.run()


if __name__ == "__main__":
    asyncio.run(main())
