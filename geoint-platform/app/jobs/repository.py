"""Repositorio de SourceJob con claim distribuido (SKIP LOCKED + lease)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
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
        now = datetime.now(UTC)
        lease_until = now + timedelta(seconds=lease_seconds)

        stmt = (
            select(SourceJob)
            .where(
                SourceJob.enabled.is_(True),
                SourceJob.next_run_at <= now,
                SourceJob.status.in_(("pending", "retry")),
            )
            .where((SourceJob.locked_until.is_(None)) | (SourceJob.locked_until < now))
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

        now = datetime.now(UTC)
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

        now = datetime.now(UTC)
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
    """Atomic claim before side effects: processing → completed | failed."""

    async def try_claim(
        self,
        session: AsyncSession,
        *,
        tenant_id: str,
        message_id: str,
        subject: str,
        source_id: str | None,
        worker_id: str,
        lease_seconds: int = 180,
    ) -> str:
        """Try to claim message for processing.

        Returns:
          claimed — this worker owns the work; run side effects
          completed — already finished successfully; ACK
          busy — another worker holds a live lease; NAK for redelivery
        """
        now = datetime.now(UTC)
        lease_until = now + timedelta(seconds=max(30, lease_seconds))
        msg_uuid = uuid4()

        # Insert new processing row, or reclaim if failed/expired lease
        stmt = (
            insert(ProcessedMessage)
            .values(
                id=msg_uuid,
                tenant_id=tenant_id,
                message_id=message_id,
                subject=subject,
                source_id=source_id,
                status="processing",
                lease_until=lease_until,
                worker_id=worker_id,
            )
            .on_conflict_do_update(
                constraint="uq_processed_messages_tenant_message_id",
                set_={
                    "status": "processing",
                    "lease_until": lease_until,
                    "worker_id": worker_id,
                    "subject": subject,
                    "source_id": source_id,
                    "updated_at": now,
                },
                where=(
                    (ProcessedMessage.status != "completed")
                    & (
                        (ProcessedMessage.lease_until.is_(None))
                        | (ProcessedMessage.lease_until < now)
                        | (ProcessedMessage.status == "failed")
                    )
                ),
            )
            .returning(ProcessedMessage.id, ProcessedMessage.status, ProcessedMessage.worker_id)
        )
        result = await session.execute(stmt)
        row = result.first()

        if row is not None and row.worker_id == worker_id and row.status == "processing":
            outcome = "claimed"
        else:
            # Inspect the conflicting row before commit. RLS set_config is
            # transaction-local, so querying after commit would drop worker context.
            cur = await session.execute(
                select(ProcessedMessage).where(
                    ProcessedMessage.tenant_id == tenant_id,
                    ProcessedMessage.message_id == message_id,
                )
            )
            existing = cur.scalar_one_or_none()
            if existing is None:
                outcome = "busy"
            elif existing.status == "completed":
                outcome = "completed"
            elif existing.worker_id == worker_id and existing.status == "processing":
                outcome = "claimed"
            else:
                outcome = "busy"

        await session.commit()
        return outcome

    async def mark_completed(
        self,
        session: AsyncSession,
        *,
        tenant_id: str,
        message_id: str,
        worker_id: str,
    ) -> None:
        now = datetime.now(UTC)
        await session.execute(
            text(
                """
                UPDATE processed_messages
                SET status = 'completed', lease_until = NULL, updated_at = :now
                WHERE tenant_id = :tid AND message_id = :mid AND worker_id = :wid
                """
            ),
            {"now": now, "tid": tenant_id, "mid": message_id, "wid": worker_id},
        )
        await session.commit()

    async def mark_failed(
        self,
        session: AsyncSession,
        *,
        tenant_id: str,
        message_id: str,
        worker_id: str,
    ) -> None:
        """Release lease so another delivery can reclaim."""
        now = datetime.now(UTC)
        await session.execute(
            text(
                """
                UPDATE processed_messages
                SET status = 'failed', lease_until = NULL, updated_at = :now
                WHERE tenant_id = :tid
                  AND message_id = :mid
                  AND worker_id = :wid
                  AND status = 'processing'
                """
            ),
            {"now": now, "tid": tenant_id, "mid": message_id, "wid": worker_id},
        )
        await session.commit()

    # Back-compat helpers
    async def is_processed(
        self,
        session: AsyncSession,
        *,
        tenant_id: str,
        message_id: str,
    ) -> bool:
        stmt = select(ProcessedMessage.id).where(
            ProcessedMessage.tenant_id == tenant_id,
            ProcessedMessage.message_id == message_id,
            ProcessedMessage.status == "completed",
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def mark_processed(
        self,
        session: AsyncSession,
        *,
        tenant_id: str,
        message_id: str,
        subject: str,
        source_id: str | None = None,
    ) -> bool:
        """Legacy path: insert completed. Prefer try_claim + mark_completed."""
        stmt = (
            insert(ProcessedMessage)
            .values(
                tenant_id=tenant_id,
                message_id=message_id,
                subject=subject,
                source_id=source_id,
                status="completed",
            )
            .on_conflict_do_nothing(constraint="uq_processed_messages_tenant_message_id")
            .returning(ProcessedMessage.id)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.scalar_one_or_none() is not None
