"""Enqueue and claim alert deliveries for the notifier worker."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select
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

    async def claim_batch(
        self,
        session: AsyncSession,
        *,
        worker_id: str,
        limit: int = 20,
        lease_seconds: int = 120,
    ) -> list[AlertDelivery]:
        """Claim ready deliveries or reclaim an expired sending lease."""
        now = datetime.now(UTC)
        lease_until = now + timedelta(seconds=max(30, lease_seconds))
        ready = and_(
            AlertDelivery.status.in_(("pending", "failed")),
            or_(
                AlertDelivery.next_attempt_at.is_(None),
                AlertDelivery.next_attempt_at <= now,
            ),
        )
        expired = and_(
            AlertDelivery.status == "sending",
            AlertDelivery.lease_until.is_not(None),
            AlertDelivery.lease_until < now,
        )
        result = await session.execute(
            select(AlertDelivery)
            .where(
                AlertDelivery.attempts < AlertDelivery.max_attempts,
                or_(ready, expired),
            )
            .order_by(AlertDelivery.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        rows = list(result.scalars().all())
        for delivery in rows:
            delivery.status = "sending"
            delivery.claimed_by = worker_id
            delivery.lease_until = lease_until
            delivery.updated_at = now
        if rows:
            await session.flush()
        return rows

    async def process_one(
        self,
        session: AsyncSession,
        *,
        delivery_id: UUID,
        worker_id: str,
    ) -> dict[str, Any]:
        delivery = await session.get(AlertDelivery, delivery_id)
        if delivery is None:
            raise LookupError(f"alert delivery not found: {delivery_id}")
        if delivery.status != "sending" or delivery.claimed_by != worker_id:
            raise RuntimeError("alert delivery lease is not owned by this worker")

        alert = await session.get(GeofenceAlert, delivery.alert_id)
        channel = await session.get(AlertChannel, delivery.channel_id)
        now = datetime.now(UTC)
        delivery.attempts += 1

        if not alert:
            delivery.status = "skipped"
            delivery.last_error = "alert not found"
            delivery.claimed_by = None
            delivery.lease_until = None
            delivery.updated_at = now
            return _delivery_dict(delivery)

        # Do not notify resolved/silenced noise: skip if alert already resolved
        if alert.status in ("resolved",):
            delivery.status = "skipped"
            delivery.last_error = f"alert status={alert.status}"
            delivery.claimed_by = None
            delivery.lease_until = None
            delivery.updated_at = now
            return _delivery_dict(delivery)

        if not channel or not channel.enabled:
            delivery.status = "skipped"
            delivery.last_error = "channel missing or disabled"
            delivery.claimed_by = None
            delivery.lease_until = None
            delivery.updated_at = now
            return _delivery_dict(delivery)

        alert_payload = _alert_dict(alert)
        alert_payload["tenant_id"] = delivery.tenant_id
        notifier = get_notifier(delivery.channel_type)
        result = await notifier.send(
            alert=alert_payload,
            channel_config=channel.config or {},
            idempotency_key=str(delivery.id),
        )

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
        delivery.claimed_by = None
        delivery.lease_until = None
        delivery.updated_at = now
        return _delivery_dict(delivery)
