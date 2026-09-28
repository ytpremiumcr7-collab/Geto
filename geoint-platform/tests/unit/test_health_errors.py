"""Health ready must expose errors[] when a dependency fails — not silent pass."""

from __future__ import annotations

import json

import pytest


@pytest.mark.asyncio
async def test_readiness_structure_on_total_failure(monkeypatch):
    from app.api.routes import health as health_mod

    class BoomEngine:
        def connect(self):
            raise RuntimeError("pg down")

    class BoomCtx:
        async def __aenter__(self):
            raise RuntimeError("pg down")

        async def __aexit__(self, *a):
            return False

    class BoomEngine2:
        def connect(self):
            return BoomCtx()

    monkeypatch.setattr(health_mod, "engine", BoomEngine2())

    class BoomBus:
        async def connect(self):
            raise RuntimeError("nats down")

        async def close(self):
            pass

    monkeypatch.setattr(health_mod, "EventBus", BoomBus)

    class BoomStore:
        def ensure_bucket(self):
            raise RuntimeError("s3 down")

    monkeypatch.setattr(health_mod, "ObjectStore", BoomStore)

    response = await health_mod.readiness()
    assert response.status_code == 503
    body = json.loads(response.body)
    assert body["status"] == "degraded"
    assert body["postgres"] is False
    assert body["nats"] is False
    assert body["s3"] is False
    assert isinstance(body["errors"], list)
    assert len(body["errors"]) >= 3
    comps = {e["component"] for e in body["errors"]}
    assert "postgres" in comps
    assert "nats" in comps
    assert "s3" in comps
    for e in body["errors"]:
        assert "error_type" in e and "message" in e
