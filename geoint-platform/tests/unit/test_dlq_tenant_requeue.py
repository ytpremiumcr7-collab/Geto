from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.api.routes import dlq as dlq_routes
from app.auth.models import Principal


class _FakeDb:
    def __init__(self, message):
        self.message = message
        self.committed = False

    async def get(self, _model, _pk):
        return self.message

    async def commit(self):
        self.committed = True


class _FakeJetStreamClient:
    last = None

    def __init__(self):
        self.published = []
        self.js = None
        _FakeJetStreamClient.last = self

    async def connect(self):
        return None

    async def close(self):
        return None

    async def publish_job(self, **kwargs):
        self.published.append(kwargs)


def test_dlq_requeue_preserves_original_tenant(monkeypatch):
    tenant = "tenant-a"
    job_id = uuid4()
    message = SimpleNamespace(
        id=uuid4(),
        tenant_id=tenant,
        source_id="usgs_earthquake",
        status="open",
        payload={
            "job_id": str(job_id),
            "job_type": "poll",
            "config": {},
            "tenant_id": tenant,
        },
        resolved_at=None,
    )
    db = _FakeDb(message)
    principal = Principal("admin-1", tenant, frozenset({"admin"}))
    monkeypatch.setattr(dlq_routes, "JetStreamClient", _FakeJetStreamClient)

    asyncio.run(dlq_routes.requeue_dlq(message.id, db=db, principal=principal))

    assert db.committed is True
    assert _FakeJetStreamClient.last is not None
    assert _FakeJetStreamClient.last.published[0]["tenant_id"] == tenant
