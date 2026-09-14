"""Enqueue and claim alert deliveries for the notifier worker."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.models import AlertChannel, AlertDelivery, GeofenceAlert
from app.alerts.notifiers import get_notifier
from app.alerts.service import _alert_dict


def _delivery_dict(d: AlertDelivery) -> dict[str, Any]:
    return {
        "id": str(d.id),
        "alert_id": str(d.alert_id),
        "channel_id": str(d.channel_id),
        "channel_type": d.channel_type,
        "status": d.status,
        "attempts": d.attempts,
        "last_error": d.last_error,
        "delivered_at": d.delivered_at.isoformat() if d.delivered_at else None,
        "response_meta": d.response_meta or {},
    }


class DeliveryService:
    async def enqueue_for_alert(
        self,
        session: AsyncSession,
        *,
        tenant_id: str,
        alert: GeofenceAlert,
        channel_ids: list[str] | list[UUID],
    ) -> list[AlertDelivery]:
        """Create pending delivery rows for each channel on the rule."""
        created: list[AlertDelivery] = []
        now = datetime.now(UTC)
        for raw_id in channel_ids or []:
            try:
                cid = raw_id if isinstance(raw_id, UUID) else UUID(str(raw_id))
            except Exception:
                continue
            ch = await session.get(AlertChannel, cid)
            if not ch or ch.tenant_id != tenant_id or not ch.enabled:
                # still record skipped placeholder? skip silently
                continue
            d = AlertDelivery(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                alert_id=alert.id,
                channel_id=ch.id,
                channel_type=ch.channel_type,
                status="pending",
                attempts=0,
                max_attempts=5,
                next_attempt_at=now,
                response_meta={},
            )
            session.add(d)
            created.append(d)
        if created:
            await session.flush()
        return created

    async def list_for_alert(
        self, session: AsyncSession, tenant_id: str, alert_id: UUID
    ) -> list[dict[str, Any]]:
        result = await session.execute(
            select(AlertDelivery).where(
                AlertDelivery.tenant_id == tenant_id,
                AlertDelivery.alert_id == alert_id,
            )
        )
        return [_delivery_dict(d) for d in result.scalars().all()]

    async def claim_batch(self, session: AsyncSession, *, limit: int = 20) -> list[AlertDelivery]:
        """Claim pending/failed deliveries ready for retry (system tenant)."""
        now = datetime.now(UTC)
        result = await session.execute(
            select(AlertDelivery)
            .where(
                AlertDelivery.status.in_(("pending", "failed")),
                AlertDelivery.attempts < AlertDelivery.max_attempts,
                or_(
                    AlertDelivery.next_attempt_at.is_(None),
                    AlertDelivery.next_attempt_at <= now,
                ),
            )
            .order_by(AlertDelivery.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        rows = list(result.scalars().all())
        for d in rows:
            d.status = "sending"
            d.updated_at = now
        if rows:
            await session.flush()
        return rows

    async def process_one(self, session: AsyncSession, delivery: AlertDelivery) -> dict[str, Any]:
        alert = await session.get(GeofenceAlert, delivery.alert_id)
        channel = await session.get(AlertChannel, delivery.channel_id)
        now = datetime.now(UTC)
        delivery.attempts += 1

        if not alert:
            delivery.status = "skipped"
            delivery.last_error = "alert not found"
            delivery.updated_at = now
            return _delivery_dict(delivery)

        # Do not notify resolved/silenced noise: skip if alert already resolved
        if alert.status in ("resolved",):
            delivery.status = "skipped"
            delivery.last_error = f"alert status={alert.status}"
            delivery.updated_at = now
            return _delivery_dict(delivery)

        if not channel or not channel.enabled:
            delivery.status = "skipped"
            delivery.last_error = "channel missing or disabled"
            delivery.updated_at = now
            return _delivery_dict(delivery)

        alert_payload = _alert_dict(alert)
        alert_payload["tenant_id"] = delivery.tenant_id
        notifier = get_notifier(delivery.channel_type)
        result = await notifier.send(alert=alert_payload, channel_config=channel.config or {})

        if result.ok:
            delivery.status = "delivered"
            delivery.delivered_at = now
            delivery.last_error = None
            delivery.response_meta = result.meta
        else:
            delivery.last_error = (result.error or "unknown")[:2000]
            delivery.response_meta = result.meta
            if delivery.attempts >= delivery.max_attempts:
                delivery.status = "failed"
            else:
                delay = min(3600, 30 * (2 ** max(0, delivery.attempts - 1)))
                delivery.next_attempt_at = now + timedelta(seconds=delay)
                delivery.status = "pending"
        delivery.updated_at = now
        return _delivery_dict(delivery)
