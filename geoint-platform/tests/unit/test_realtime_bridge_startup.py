from __future__ import annotations

import pytest

from app.realtime import nats_bridge as bridge_mod


class _FakeNats:
    def __init__(self):
        self.subjects = []

    async def subscribe(self, subject, cb=None):
        self.subjects.append(subject)

    async def drain(self):
        return None


@pytest.mark.asyncio
async def test_realtime_bridge_connects_before_background_loop(monkeypatch):
    fake = _FakeNats()

    async def connect(*_args, **_kwargs):
        return fake

    monkeypatch.setattr(bridge_mod.nats, "connect", connect)

    bridge = bridge_mod.RealtimeNatsBridge()
    await bridge.connect()

    assert bridge.nc is fake
    assert bridge.connected is True
    assert fake.subjects == ["geoint.event.>", "geoint.alert.>"]


@pytest.mark.asyncio
async def test_realtime_bridge_connection_failure_propagates(monkeypatch):
    async def fail(*_args, **_kwargs):
        raise RuntimeError("nats unavailable")

    monkeypatch.setattr(bridge_mod.nats, "connect", fail)

    bridge = bridge_mod.RealtimeNatsBridge()
    with pytest.raises(RuntimeError, match="nats unavailable"):
        await bridge.connect()

    assert bridge.connected is False
