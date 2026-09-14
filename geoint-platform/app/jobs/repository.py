"""Repositorio de SourceJob con claim distribuido (SKIP LOCKED + lease)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.models import ProcessedMessage, SourceJob


class JobRepository:
    async def claim_due_jobs(
        self,
        session: AsyncSession,
        *,
        worker_id: str,
        limit: int = 25,
        lease_seconds: int = 120,
    ) -> list[SourceJob]:
        now = datetime.now(timezone.utc)
        lease_until = now + timedelta(seconds=lease_seconds)

        stmt = (
            select(SourceJob)
            .where(
                SourceJob.enabled.is_(True),
                SourceJob.next_run_at <= now,
                SourceJob.status.in_(("pending", "retry")),
            )
            .where(
                (SourceJob.locked_until.is_(None)) | (SourceJob.locked_until < now)
            )
            .order_by(SourceJob.next_run_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )

        result = await session.execute(stmt)
        jobs = list(result.scalars().all())

        for job in jobs:
            job.status = "queued"
            job.locked_until = lease_until
            job.locked_by = worker_id
            job.last_run_at = now
            job.attempts += 1

        await session.commit()
        return jobs

    async def mark_success(self, session: AsyncSession, job_id: UUID) -> None:
        job = await session.get(SourceJob, job_id)
        if not job:
            return

        now = datetime.now(timezone.utc)
        job.status = "pending"
        job.next_run_at = now + timedelta(seconds=job.interval_seconds)
        job.locked_until = None
        job.locked_by = None
        job.attempts = 0
        job.last_error = None
        job.last_success_at = now
        await session.commit()

    async def mark_failure(
        self,
        session: AsyncSession,
        job_id: UUID,
        error: str,
    ) -> None:
        job = await session.get(SourceJob, job_id)
        if not job:
            return

        now = datetime.now(timezone.utc)
        if job.attempts >= job.max_attempts:
            job.status = "failed"
        else:
            job.status = "retry"
            backoff = min(300, 2 ** max(job.attempts - 1, 0))
            job.next_run_at = now + timedelta(seconds=backoff)

        job.locked_until = None
        job.locked_by = None
        job.last_error = (error or "")[:4000]
        await session.commit()


class IdempotencyRepository:
    async def is_processed(self, session: AsyncSession, message_id: str) -> bool:
        stmt = select(ProcessedMessage.id).where(
            ProcessedMessage.message_id == message_id
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def mark_processed(
        self,
        session: AsyncSession,
        *,
        message_id: str,
        subject: str,
        source_id: str | None = None,
    ) -> bool:
        """Inserta. Devuelve True si era nuevo, False si ya existía (race)."""
        from sqlalchemy.dialects.postgresql import insert

        stmt = (
            insert(ProcessedMessage)
            .values(
                message_id=message_id,
                subject=subject,
                source_id=source_id,
            )
            .on_conflict_do_nothing(constraint="uq_processed_messages_message_id")
            .returning(ProcessedMessage.id)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.scalar_one_or_none() is not None
