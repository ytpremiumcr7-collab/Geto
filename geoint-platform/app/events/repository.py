from __future__ import annotations

from collections.abc import Collection
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.models import EventRecord


class EventRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def append(
        self,
        *,
        tenant_id: str,
        source_id: str,
        event_type: str,
        occurred_at: datetime,
        payload: dict[str, Any],
        entity_id: str | None = None,
    ) -> EventRecord:
        row = EventRecord(
            tenant_id=tenant_id,
            source_id=source_id,
            event_type=event_type,
            entity_id=entity_id,
            occurred_at=occurred_at,
            payload=payload,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def list(
        self,
        *,
        source_ids: Collection[str],
        source_id: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[EventRecord]:
        allowed = tuple(dict.fromkeys(str(item) for item in source_ids if str(item)))
        if not allowed:
            return []
        stmt = select(EventRecord).where(EventRecord.source_id.in_(allowed))
        if source_id:
            stmt = stmt.where(EventRecord.source_id == source_id)
        if since is not None:
            stmt = stmt.where(EventRecord.occurred_at >= since)
        stmt = stmt.order_by(EventRecord.occurred_at.desc()).limit(min(limit, 500))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
