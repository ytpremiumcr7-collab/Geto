from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.outbox.models import OutboxMessage


class OutboxRepository:
    async def enqueue(
        self,
        session: AsyncSession,
        *,
        subject: str,
        payload: dict[str, Any],
        tenant_id: str = "default",
    ) -> OutboxMessage:
        msg = OutboxMessage(
            tenant_id=tenant_id,
            subject=subject,
            payload=payload,
        )
        session.add(msg)
        await session.flush()
        return msg

    async def claim(
        self,
        session: AsyncSession,
        *,
        worker_id: str,
        limit: int = 100,
        lease_seconds: int = 120,
    ) -> list[OutboxMessage]:
        """Lease dispatchable messages and COMMIT before any network I/O."""
        now = datetime.now(UTC)
        lease_until = now + timedelta(seconds=max(30, lease_seconds))
        stmt = (
            select(OutboxMessage)
            .where(
                OutboxMessage.published_at.is_(None),
                OutboxMessage.dead_lettered_at.is_(None),
                or_(
                    OutboxMessage.next_attempt_at.is_(None),
                    OutboxMessage.next_attempt_at <= now,
                ),
                or_(
                    OutboxMessage.lease_until.is_(None),
                    OutboxMessage.lease_until < now,
                ),
            )
            .order_by(OutboxMessage.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await session.execute(stmt)
        rows = list(result.scalars().all())
        for message in rows:
            message.claimed_by = worker_id
            message.lease_until = lease_until
        # Critical invariant: row locks end here, before NATS/ClickHouse calls.
        await session.commit()
        return rows

    async def mark_published(
        self,
        session: AsyncSession,
        *,
        message_id: UUID,
        worker_id: str,
    ) -> bool:
        message = await session.get(OutboxMessage, message_id)
        if (
            message is None
            or message.claimed_by != worker_id
            or message.published_at is not None
            or message.dead_lettered_at is not None
        ):
            return None
        message.published_at = datetime.now(UTC)
        message.claimed_by = None
        message.lease_until = None
        message.next_attempt_at = None
        message.last_error = None
        outcome = "dead_lettered" if message.dead_lettered_at is not None else "retry"
        if commit:
            await session.commit()
        else:
            await session.flush()
        return outcome

    @staticmethod
    def mark_failed(
        message: OutboxMessage,
        error: str,
        *,
        max_attempts: int,
        base_backoff_seconds: int,
    ) -> None:
        """Mutate retry/dead-letter state; caller persists it in a short TX."""
        now = datetime.now(UTC)
        message.attempts += 1
        message.last_error = (error or "")[:4000]
        message.claimed_by = None
        message.lease_until = None

        if message.attempts >= max(1, max_attempts):
            message.dead_lettered_at = now
            message.next_attempt_at = None
            return

        delay = min(
            3600,
            max(1, base_backoff_seconds) * (2 ** max(0, message.attempts - 1)),
        )
        message.next_attempt_at = now + timedelta(seconds=delay)
        message.dead_lettered_at = None

    async def persist_failure(
        self,
        session: AsyncSession,
        *,
        message_id: UUID,
        worker_id: str,
        error: str,
        max_attempts: int,
        base_backoff_seconds: int,
        commit: bool = True,
    ) -> str | None:
        message = await session.get(OutboxMessage, message_id)
        if (
            message is None
            or message.claimed_by != worker_id
            or message.published_at is not None
            or message.dead_lettered_at is not None
        ):
            return False
        self.mark_failed(
            message,
            error,
            max_attempts=max_attempts,
            base_backoff_seconds=base_backoff_seconds,
        )
        await session.commit()
        return True
