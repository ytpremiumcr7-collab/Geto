from __future__ import annotations

import asyncio
import json

from app.api.routes import health as health_mod


class _BoomCtx:
    async def __aenter__(self):
        raise RuntimeError("pg down")

    async def __aexit__(self, *args):
        return False


class _BoomEngine:
    def connect(self):
        return _BoomCtx()


class _BoomBus:
    async def connect(self):
        raise RuntimeError("nats down")

    async def close(self):
        return None


class _BoomStore:
    def ensure_bucket(self):
        raise RuntimeError("minio down")


def test_readiness_returns_503_when_required_dependencies_are_down(monkeypatch):
    monkeypatch.setattr(health_mod, "engine", _BoomEngine())
    monkeypatch.setattr(health_mod, "EventBus", _BoomBus)
    monkeypatch.setattr(health_mod, "ObjectStore", _BoomStore)

    response = asyncio.run(health_mod.readiness())

    assert response.status_code == 503
    body = json.loads(response.body)
    assert body["status"] == "degraded"
    assert body["postgres"] is False
    assert body["nats"] is False
    assert body["minio"] is False
