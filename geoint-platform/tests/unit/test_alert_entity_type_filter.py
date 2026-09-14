"""entity_type_filter must gate GeofenceAlert creation."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.alerts.models import GeofenceAlertRule
from app.alerts.service import AlertService


@pytest.mark.asyncio
async def test_entity_type_filter_skips_non_matching(monkeypatch):
    rule = GeofenceAlertRule(
        id=uuid.uuid4(),
        tenant_id="t1",
        geofence_id=uuid.uuid4(),
        name="aircraft-only",
        on_enter=True,
        on_exit=False,
        channel_ids=[],
        entity_type_filter=["aircraft"],
        severity="high",
        enabled=True,
        silence_until=None,
    )

    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [rule]
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.flush = AsyncMock()

    # Avoid delivery side effects
    class DummyDelivery:
        async def enqueue_for_alert(self, *a, **k):
            return []

    monkeypatch.setattr("app.alerts.delivery.DeliveryService", lambda: DummyDelivery())

    svc = AlertService()
    event = {
        "geofence_id": str(rule.geofence_id),
        "entity_id": "SHIP-1",
        "event_type": "geofence.enter",
        "occurred_at": datetime.now(UTC).isoformat(),
        "data": {"entity_type": "vessel", "lat": 1, "lon": 2},
    }
    created = await svc.emit_from_geofence_event(session, tenant_id="t1", event=event)
    assert created == []
    session.add.assert_not_called()
