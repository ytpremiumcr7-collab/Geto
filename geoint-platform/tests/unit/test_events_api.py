from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.api.routes import events as events_routes
from app.auth.models import Principal


class _LeakyEventRepository:
    def __init__(self, _db):
        pass

    async def list(self, **_kwargs):
        now = datetime.now(UTC)
        return [
            SimpleNamespace(
                id="restricted",
                tenant_id="tenant-a",
                source_id="opensky",
                event_type="position",
                entity_id="icao24:abc",
                occurred_at=now,
                payload={"source_id": "opensky"},
            ),
            SimpleNamespace(
                id="allowed",
                tenant_id="tenant-a",
                source_id="usgs_earthquake",
                event_type="correlation",
                entity_id="quake:1",
                occurred_at=now,
                payload={"source_id": "usgs_earthquake"},
            ),
        ]


@pytest.mark.asyncio
async def test_events_api_is_real_and_source_scoped(monkeypatch):
    monkeypatch.setattr(events_routes, "EventRepository", _LeakyEventRepository)
    principal = Principal("operator-1", "tenant-a", frozenset({"operator"}))

    body = await events_routes.list_events(
        source_id=None,
        since=None,
        limit=100,
        db=object(),
        principal=principal,
    )

    assert [item["id"] for item in body["events"]] == ["allowed"]
    assert body["events"][0]["source_id"] == "usgs_earthquake"
