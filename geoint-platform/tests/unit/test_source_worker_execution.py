from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.workers import source_worker as worker_mod


class FakeSession:
    def __init__(self):
        self.added = []
        self.commits = 0

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.commits += 1


@asynccontextmanager
async def fake_system_session():
    yield FakeSession()


@asynccontextmanager
async def fake_tenant_session(_tenant_id: str):
    yield FakeSession()


class FakeMsg:
    def __init__(self, payload: dict, *, delivery: int = 1):
        self.subject = f"geoint.jobs.{payload['source_id']}"
        self.data = json.dumps(payload).encode()
        self.headers = {"Nats-Msg-Id": payload["execution_id"]}
        self.metadata = SimpleNamespace(num_delivered=delivery)
        self.acks = 0
        self.naks = 0
        self.progress = 0

    async def ack(self):
        self.acks += 1

    async def nak(self):
        self.naks += 1

    async def in_progress(self):
        self.progress += 1


class FakeIdempotency:
    def __init__(self, outcome: str):
        self.outcome = outcome
        self.completed = []
        self.failed = []
        self.renewed = []

    async def try_claim(self, _session, **kwargs):
        self.claim_kwargs = kwargs
        return self.outcome

    async def mark_completed(self, _session, **kwargs):
        self.completed.append(kwargs)

    async def mark_failed(self, _session, **kwargs):
        self.failed.append(kwargs)

    async def renew_claim(self, _session, **kwargs):
        self.renewed.append(kwargs)


class FakeJobs:
    def __init__(self):
        self.renewed = []
        self.success = []
        self.failure = []

    async def renew_execution_lease(self, _session, job_id, **kwargs):
        self.renewed.append((job_id, kwargs))
        return True

    async def mark_success(self, _session, job_id, **kwargs):
        self.success.append((job_id, kwargs))
        return True

    async def mark_failure(self, _session, job_id, error, **kwargs):
        self.failure.append((job_id, error, kwargs))
        return True


class FakeDispatcher:
    def __init__(self, error: Exception | None = None):
        self.calls = []
        self.error = error

    async def execute(self, _session, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return 1


class FakeDlq:
    def __init__(self):
        self.items = []

    async def publish_dlq(self, **kwargs):
        self.items.append(kwargs)


def _payload():
    return {
        "job_id": str(uuid4()),
        "execution_id": str(uuid4()),
        "source_id": "usgs_earthquake",
        "job_type": "poll",
        "config": {},
        "tenant_id": "tenant-a",
    }


def _worker(monkeypatch, *, claim="claimed", dispatcher_error=None):
    monkeypatch.setattr(worker_mod, "system_worker_session", fake_system_session)
    monkeypatch.setattr(worker_mod, "tenant_session", fake_tenant_session)
    worker = worker_mod.SourceWorker()
    worker.idempotency = FakeIdempotency(claim)
    worker.jobs = FakeJobs()
    worker.dispatcher = FakeDispatcher(dispatcher_error)
    worker.dlq = FakeDlq()
    return worker


@pytest.mark.asyncio
async def test_source_worker_completes_one_execution_and_advances_schedule(monkeypatch):
    payload = _payload()
    msg = FakeMsg(payload)
    worker = _worker(monkeypatch)

    await worker.handle(msg)

    assert msg.acks == 1
    assert msg.naks == 0
    assert worker.dispatcher.calls[0]["message_id"] == payload["execution_id"]
    assert worker.idempotency.completed[0]["message_id"] == payload["execution_id"]
    assert worker.jobs.success[0][1]["execution_id"] == worker_mod.UUID(payload["execution_id"])


@pytest.mark.asyncio
async def test_source_worker_completed_redelivery_only_repairs_job_state(monkeypatch):
    payload = _payload()
    msg = FakeMsg(payload)
    worker = _worker(monkeypatch, claim="completed")

    await worker.handle(msg)

    assert msg.acks == 1
    assert worker.dispatcher.calls == []
    assert worker.jobs.success[0][1]["execution_id"] == worker_mod.UUID(payload["execution_id"])


@pytest.mark.asyncio
async def test_source_worker_busy_execution_does_not_burn_delivery(monkeypatch):
    payload = _payload()
    msg = FakeMsg(payload)
    worker = _worker(monkeypatch, claim="busy")

    await worker.handle(msg)

    assert msg.progress == 1
    assert msg.acks == 0
    assert msg.naks == 0
    assert worker.dispatcher.calls == []


@pytest.mark.asyncio
async def test_source_worker_retry_keeps_same_execution_on_transient_failure(monkeypatch):
    payload = _payload()
    msg = FakeMsg(payload, delivery=1)
    worker = _worker(monkeypatch, dispatcher_error=RuntimeError("temporary"))

    await worker.handle(msg)

    assert msg.naks == 1
    assert msg.acks == 0
    assert worker.idempotency.failed[0]["message_id"] == payload["execution_id"]
    assert worker.jobs.failure == []


@pytest.mark.asyncio
async def test_source_worker_dead_letters_terminal_execution(monkeypatch):
    payload = _payload()
    msg = FakeMsg(payload, delivery=5)
    worker = _worker(monkeypatch, dispatcher_error=RuntimeError("terminal"))
    worker.max_deliver = 5

    await worker.handle(msg)

    assert msg.acks == 1
    assert msg.naks == 0
    assert worker.dlq.items
    _, _, kwargs = worker.jobs.failure[0]
    assert kwargs["terminal"] is True
    assert kwargs["execution_id"] == worker_mod.UUID(payload["execution_id"])
