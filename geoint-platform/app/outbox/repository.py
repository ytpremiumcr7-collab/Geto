from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
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
        limit: int = 100,
    ) -> list[OutboxMessage]:
        stmt = (
            select(OutboxMessage)
            .where(OutboxMessage.published_at.is_(None))
            .order_by(OutboxMessage.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def mark_published(
        self,
        session: AsyncSession,
        message: OutboxMessage,
    ) -> None:
        message.published_at = datetime.now(UTC)

    async def mark_failed(
        self,
        message: OutboxMessage,
        error: str,
    ) -> None:
        message.attempts += 1
        message.last_error = (error or "")[:4000]
