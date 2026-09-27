from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.geofencing import service as geofence_service


class _GeoRepo:
    def __init__(self):
        self.fence = SimpleNamespace(id=uuid4(), name="secure-zone")

    async def find_containing(self, *args, **kwargs):
        return [self.fence]

    async def list_states_for_entity(self, *args, **kwargs):
        return []

    async def upsert_state(self, *args, **kwargs):
        return None


class _Outbox:
    async def enqueue(self, *args, **kwargs):
        return None


class _Events:
    appended = []

    def __init__(self, _session):
        pass

    async def append(self, **kwargs):
        self.__class__.appended.append(kwargs)


class _Alerts:
    async def emit_from_geofence_event(self, *args, **kwargs):
        return []


@pytest.mark.asyncio
async def test_geofence_event_is_persisted_with_source_provenance(monkeypatch):
    _Events.appended = []
    monkeypatch.setattr(geofence_service, "OutboxRepository", _Outbox)
    monkeypatch.setattr(geofence_service, "EventRepository", _Events, raising=False)

    from app.alerts import service as alerts_service

    monkeypatch.setattr(alerts_service, "AlertService", _Alerts)

    svc = geofence_service.GeofenceService(repository=_GeoRepo())
    events = await svc.evaluate_observation(
        object(),
        tenant_id="tenant-a",
        entity_id="icao24:abc",
        lon=-99.1,
        lat=19.4,
        altitude=1000.0,
        observed_at=datetime.now(UTC),
        entity_type="aircraft",
        source_id="usgs_earthquake",
    )

    assert len(events) == 1
    assert events[0]["source_id"] == "usgs_earthquake"
    assert len(_Events.appended) == 1
    assert _Events.appended[0]["source_id"] == "usgs_earthquake"
    assert _Events.appended[0]["event_type"] == "geofence.enter"
