from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.models import AlertChannel, GeofenceAlert, GeofenceAlertRule


def _channel_dict(c: AlertChannel) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "name": c.name,
        "channel_type": c.channel_type,
        "config": c.config or {},
        "enabled": c.enabled,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _rule_dict(r: GeofenceAlertRule) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "geofence_id": str(r.geofence_id),
        "name": r.name,
        "on_enter": r.on_enter,
        "on_exit": r.on_exit,
        "channel_ids": r.channel_ids or [],
        "entity_type_filter": r.entity_type_filter,
        "severity": r.severity,
        "enabled": r.enabled,
        "silence_until": r.silence_until.isoformat() if r.silence_until else None,
    }


def _alert_dict(a: GeofenceAlert) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "rule_id": str(a.rule_id) if a.rule_id else None,
        "geofence_id": str(a.geofence_id),
        "entity_id": a.entity_id,
        "event_type": a.event_type,
        "severity": a.severity,
        "status": a.status,
        "payload": a.payload or {},
        "occurred_at": a.occurred_at.isoformat() if a.occurred_at else None,
        "acked_at": a.acked_at.isoformat() if a.acked_at else None,
        "acked_by": a.acked_by,
        "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


class AlertService:
    async def list_channels(self, session: AsyncSession, tenant_id: str) -> list[dict[str, Any]]:
        result = await session.execute(
            select(AlertChannel)
            .where(AlertChannel.tenant_id == tenant_id)
            .order_by(AlertChannel.name)
        )
        return [_channel_dict(c) for c in result.scalars().all()]

    async def create_channel(
        self,
        session: AsyncSession,
        *,
        tenant_id: str,
        name: str,
        channel_type: str,
        config: dict | None = None,
    ) -> dict[str, Any]:
        c = AlertChannel(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            name=name,
            channel_type=channel_type,
            config=config or {},
        )
        session.add(c)
        await session.commit()
        await session.refresh(c)
        return _channel_dict(c)

    async def list_rules(
        self, session: AsyncSession, tenant_id: str, geofence_id: uuid.UUID | None = None
    ) -> list[dict[str, Any]]:
        stmt = select(GeofenceAlertRule).where(GeofenceAlertRule.tenant_id == tenant_id)
        if geofence_id:
            stmt = stmt.where(GeofenceAlertRule.geofence_id == geofence_id)
        result = await session.execute(stmt.order_by(GeofenceAlertRule.name))
        return [_rule_dict(r) for r in result.scalars().all()]

    async def create_rule(
        self,
        session: AsyncSession,
        *,
        tenant_id: str,
        geofence_id: uuid.UUID,
        name: str,
        on_enter: bool = True,
        on_exit: bool = True,
        channel_ids: list | None = None,
        entity_type_filter: list | None = None,
        severity: str = "medium",
    ) -> dict[str, Any]:
        r = GeofenceAlertRule(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            geofence_id=geofence_id,
            name=name,
            on_enter=on_enter,
            on_exit=on_exit,
            channel_ids=channel_ids or [],
            entity_type_filter=entity_type_filter,
            severity=severity,
        )
        session.add(r)
        await session.commit()
        await session.refresh(r)
        return _rule_dict(r)

    async def silence_rule(
        self, session: AsyncSession, tenant_id: str, rule_id: uuid.UUID, until: datetime
    ) -> dict[str, Any] | None:
        r = await session.get(GeofenceAlertRule, rule_id)
        if not r or r.tenant_id != tenant_id:
            return None
        r.silence_until = until
        await session.commit()
        await session.refresh(r)
        return _rule_dict(r)

    async def list_alerts(
        self,
        session: AsyncSession,
        tenant_id: str,
        *,
        status: str | None = "open",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        stmt = select(GeofenceAlert).where(GeofenceAlert.tenant_id == tenant_id)
        if status:
            stmt = stmt.where(GeofenceAlert.status == status)
        stmt = stmt.order_by(GeofenceAlert.occurred_at.desc()).limit(limit)
        result = await session.execute(stmt)
        return [_alert_dict(a) for a in result.scalars().all()]

    async def ack_alert(
        self, session: AsyncSession, tenant_id: str, alert_id: uuid.UUID, user_id: str
    ) -> dict[str, Any] | None:
        a = await session.get(GeofenceAlert, alert_id)
        if not a or a.tenant_id != tenant_id:
            return None
        a.status = "acked"
        a.acked_at = datetime.now(UTC)
        a.acked_by = user_id
        await session.commit()
        await session.refresh(a)
        return _alert_dict(a)

    async def resolve_alert(
        self, session: AsyncSession, tenant_id: str, alert_id: uuid.UUID
    ) -> dict[str, Any] | None:
        a = await session.get(GeofenceAlert, alert_id)
        if not a or a.tenant_id != tenant_id:
            return None
        a.status = "resolved"
        a.resolved_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(a)
        return _alert_dict(a)

    async def emit_from_geofence_event(
        self,
        session: AsyncSession,
        *,
        tenant_id: str,
        event: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Create GeofenceAlert rows for matching rules (enter/exit product path)."""
        geofence_id = uuid.UUID(str(event["geofence_id"]))
        event_type = "enter" if event.get("event_type") == "geofence.enter" else "exit"
        occurred_at = datetime.fromisoformat(event["occurred_at"].replace("Z", "+00:00"))
        if occurred_at.tzinfo is None:
            occurred_at = occurred_at.replace(tzinfo=UTC)

        result = await session.execute(
            select(GeofenceAlertRule).where(
                GeofenceAlertRule.tenant_id == tenant_id,
                GeofenceAlertRule.geofence_id == geofence_id,
                GeofenceAlertRule.enabled.is_(True),
            )
        )
        rules = list(result.scalars().all())
        created: list[dict[str, Any]] = []
        now = datetime.now(UTC)

        for rule in rules:
            if rule.silence_until and rule.silence_until > now:
                continue
            if event_type == "enter" and not rule.on_enter:
                continue
            if event_type == "exit" and not rule.on_exit:
                continue
            alert = GeofenceAlert(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                rule_id=rule.id,
                geofence_id=geofence_id,
                entity_id=event["entity_id"],
                event_type=event_type,
                severity=rule.severity,
                status="open",
                payload=event,
                occurred_at=occurred_at,
            )
            session.add(alert)
            await session.flush()  # need alert.id
            # Enqueue notifier deliveries for rule channels
            from app.alerts.delivery import DeliveryService

            await DeliveryService().enqueue_for_alert(
                session,
                tenant_id=tenant_id,
                alert=alert,
                channel_ids=list(rule.channel_ids or []),
            )
            created.append(_alert_dict(alert))
        if created:
            await session.flush()
        return created
