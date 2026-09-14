"""Scheduler de SourceJobs: claim + publish a JetStream."""

from __future__ import annotations

import asyncio
import os
import signal
import socket
from uuid import uuid4

import structlog

from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.jobs.repository import JobRepository
from app.messaging.jetstream import JetStreamClient

log = structlog.get_logger()


class JobScheduler:
    def __init__(
        self,
        poll_interval: float | None = None,
        lease_seconds: int | None = None,
    ):
        self.poll_interval = poll_interval or float(
            os.getenv("JOB_POLL_INTERVAL_SECONDS", "2")
        )
        self.lease_seconds = lease_seconds or int(
            os.getenv("JOB_LEASE_SECONDS", "120")
        )
        self.worker_id = os.getenv("WORKER_ID") or (
            f"{socket.gethostname()}-{os.getpid()}-{uuid4().hex[:8]}"
        )
        self.repo = JobRepository()
        self.js = JetStreamClient()
        self._running = False

    async def run(self) -> None:
        await self.js.connect()
        self._running = True
        log.info("scheduler_started", worker_id=self.worker_id)

        try:
            while self._running:
                try:
                    await self.tick()
                except Exception:
                    log.exception("scheduler_tick_failed")
                await asyncio.sleep(self.poll_interval)
        finally:
            await self.js.close()

    async def tick(self) -> None:
        async with SessionLocal() as session:
            # RLS: workers use reserved tenant marker so FORCE RLS policies allow claim
            from sqlalchemy import text
            await session.execute(
                text("SELECT set_config('app.tenant_id', :tid, true)"),
                {"tid": "__system__"},
            )
            jobs = await self.repo.claim_due_jobs(
                session,
                worker_id=self.worker_id,
                lease_seconds=self.lease_seconds,
            )

        for job in jobs:
            try:
                await self.js.publish_job(
                    job_id=job.id,
                    source_id=job.source_id,
                    job_type=job.job_type,
                    config=job.config or {},
                    tenant_id=getattr(job, "tenant_id", None) or "default",
                )
                log.info(
                    "job_published",
                    job_id=str(job.id),
                    source=job.source_id,
                )
            except Exception as exc:
                log.exception(
                    "job_publish_failed",
                    job_id=str(job.id),
                    source=job.source_id,
                )
                async with SessionLocal() as session:
                    await self.repo.mark_failure(session, job.id, str(exc))

    def stop(self) -> None:
        self._running = False


async def main() -> None:
    configure_logging(settings.log_level)
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
