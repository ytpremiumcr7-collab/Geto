from __future__ import annotations

import asyncio

from app.realtime.manager import ConnectionManager


class _FakeWebSocket:
    def __init__(self):
        self.accepts = 0
        self.sent = []

    async def accept(self):
        self.accepts += 1

    async def send_json(self, payload):
        self.sent.append(payload)


def test_connection_manager_does_not_repeat_protocol_accept():
    manager = ConnectionManager()
    ws = _FakeWebSocket()

    asyncio.run(manager.connect("tenant-a", ws, allowed_source_ids={"usgs_earthquake"}))

    assert ws.accepts == 0


def test_realtime_delivery_respects_source_scope():
    manager = ConnectionManager()
    ws = _FakeWebSocket()

    async def scenario():
        await manager.connect("tenant-a", ws, allowed_source_ids={"usgs_earthquake"})
        await manager.publish(
            "tenant-a",
            {"event_type": "position", "source_id": "opensky", "entity_id": "secret"},
        )
        await manager.publish(
            "tenant-a",
            {"event_type": "earthquake", "source_id": "usgs_earthquake", "entity_id": "ok"},
        )

    asyncio.run(scenario())

    assert [item["entity_id"] for item in ws.sent] == ["ok"]


def test_realtime_drops_payload_without_source_provenance():
    manager = ConnectionManager()
    ws = _FakeWebSocket()

    async def scenario():
        await manager.connect("tenant-a", ws, allowed_source_ids={"usgs_earthquake"})
        await manager.publish(
            "tenant-a",
            {"event_type": "legacy-event", "entity_id": "unknown-source"},
        )

    asyncio.run(scenario())

    assert ws.sent == []
