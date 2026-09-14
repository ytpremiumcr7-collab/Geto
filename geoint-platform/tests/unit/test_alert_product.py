"""Geofence alert product: rule matching (asyncio.run, no plugin required)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4


def test_emit_skips_silenced_rule():
    from app.alerts.service import AlertService

    fence_id = uuid4()
    rule = SimpleNamespace(
        id=uuid4(),
        tenant_id="t1",
        geofence_id=fence_id,
        enabled=True,
        silence_until=datetime.now(UTC) + timedelta(hours=1),
        on_enter=True,
        on_exit=True,
        severity="high",
        name="r1",
        channel_ids=[],
        entity_type_filter=None,
    )

    class FakeResult:
        def scalars(self):
            return self

        def all(self):
            return [rule]

    class FakeSession:
        def __init__(self):
            self.added = []

        async def execute(self, *a, **k):
            return FakeResult()

        def add(self, obj):
            self.added.append(obj)

        async def flush(self):
            pass

    session = FakeSession()
    event = {
        "event_type": "geofence.enter",
        "geofence_id": str(fence_id),
        "entity_id": "acft-1",
        "occurred_at": datetime.now(UTC).isoformat(),
        "data": {},
    }
    created = asyncio.run(
        AlertService().emit_from_geofence_event(session, tenant_id="t1", event=event)
    )
    assert created == []
    assert session.added == []


def test_emit_creates_on_enter():
    from app.alerts.models import GeofenceAlert
    from app.alerts.service import AlertService

    fence_id = uuid4()
    rule = SimpleNamespace(
        id=uuid4(),
        tenant_id="t1",
        geofence_id=fence_id,
        enabled=True,
        silence_until=None,
        on_enter=True,
        on_exit=False,
        severity="medium",
        name="r1",
        channel_ids=["c1"],
        entity_type_filter=None,
    )

    class FakeResult:
        def scalars(self):
            return self

        def all(self):
            return [rule]

    class FakeSession:
        def __init__(self):
            self.added = []

        async def execute(self, *a, **k):
            return FakeResult()

        def add(self, obj):
            self.added.append(obj)

        async def flush(self):
            pass

    session = FakeSession()
    event = {
        "event_type": "geofence.enter",
        "geofence_id": str(fence_id),
        "entity_id": "ship-9",
        "occurred_at": datetime.now(UTC).isoformat(),
        "data": {"lat": 1.0, "lon": 2.0},
    }
    created = asyncio.run(
        AlertService().emit_from_geofence_event(session, tenant_id="t1", event=event)
    )
    assert len(created) == 1
    assert created[0]["event_type"] == "enter"
    assert created[0]["entity_id"] == "ship-9"
    assert len(session.added) == 1
    assert isinstance(session.added[0], GeofenceAlert)
