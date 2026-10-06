from __future__ import annotations

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.outbox import dispatcher as dispatcher_mod


class FakeSession:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


@asynccontextmanager
async def fake_system_session():
    yield FakeSession()


class FakeRepo:
    def __init__(self, messages):
        self.messages = messages
        self.claim_calls = []
        self.published = []
        self.failures = []

    async def claim(self, _session, **kwargs):
        self.claim_calls.append(kwargs)
        return self.messages

    async def mark_published(self, _session, **kwargs):
        self.published.append(kwargs)
        return True

    async def persist_failure(self, _session, **kwargs):
        self.failures.append(kwargs)
        return getattr(self, "failure_outcome", "retry")


class FakeJsContext:
    def __init__(self, error: Exception | None = None):
        self.calls = []
        self.error = error

    async def publish(self, subject, payload, headers=None):
        self.calls.append((subject, json.loads(payload.decode()), headers))
        if self.error:
            raise self.error


class FakeJobsRepo:
    def __init__(self):
        self.failures = []

    async def mark_failure(self, _session, job_id, error, **kwargs):
        self.failures.append((job_id, error, kwargs))
        return True


class FakeJetStream:
    def __init__(self, error: Exception | None = None):
        self.js = FakeJsContext(error)


def _message():
    return SimpleNamespace(
        id=uuid4(),
        tenant_id="tenant-a",
        subject="geoint.event.tenant-a",
        payload={"tenant_id": "tenant-a", "source_id": "usgs_earthquake"},
    )


@pytest.mark.asyncio
async def test_outbox_dispatcher_publishes_with_outbox_idempotency_key(monkeypatch):
    monkeypatch.setattr(dispatcher_mod, "system_worker_session", fake_system_session)
    message = _message()
    dispatcher = dispatcher_mod.OutboxDispatcher()
    dispatcher.repo = FakeRepo([message])
    dispatcher.js = FakeJetStream()

    await dispatcher.process_batch()

    assert dispatcher.js.js.calls[0][2] == {"Nats-Msg-Id": str(message.id)}
    assert dispatcher.repo.published[0]["message_id"] == message.id
    assert dispatcher.repo.failures == []


@pytest.mark.asyncio
async def test_outbox_dispatcher_persists_failure_for_bounded_retry(monkeypatch):
    monkeypatch.setattr(dispatcher_mod, "system_worker_session", fake_system_session)
    message = _message()
    dispatcher = dispatcher_mod.OutboxDispatcher()
    dispatcher.repo = FakeRepo([message])
    dispatcher.js = FakeJetStream(RuntimeError("nats unavailable"))

    await dispatcher.process_batch()

    assert dispatcher.repo.published == []
    assert dispatcher.repo.failures[0]["message_id"] == message.id
    assert dispatcher.repo.failures[0]["error"] == "nats unavailable"


@pytest.mark.asyncio
async def test_job_dispatch_uses_execution_id_as_broker_dedupe_key(monkeypatch):
    monkeypatch.setattr(dispatcher_mod, "system_worker_session", fake_system_session)
    execution_id = uuid4()
    message = SimpleNamespace(
        id=uuid4(),
        tenant_id="tenant-a",
        subject="geoint.jobs.usgs_earthquake",
        payload={
            "job_id": str(uuid4()),
            "execution_id": str(execution_id),
            "source_id": "usgs_earthquake",
            "job_type": "poll",
            "config": {},
            "tenant_id": "tenant-a",
        },
    )
    dispatcher = dispatcher_mod.OutboxDispatcher()
    dispatcher.repo = FakeRepo([message])
    dispatcher.js = FakeJetStream()

    await dispatcher.process_batch()

    assert dispatcher.js.js.calls[0][2] == {"Nats-Msg-Id": str(execution_id)}


@pytest.mark.asyncio
async def test_dead_lettered_job_dispatch_releases_schedule_atomically(monkeypatch):
    monkeypatch.setattr(dispatcher_mod, "system_worker_session", fake_system_session)
    job_id = uuid4()
    execution_id = uuid4()
    message = SimpleNamespace(
        id=uuid4(),
        tenant_id="tenant-a",
        subject="geoint.jobs.usgs_earthquake",
        payload={
            "job_id": str(job_id),
            "execution_id": str(execution_id),
            "source_id": "usgs_earthquake",
            "job_type": "poll",
            "config": {},
            "tenant_id": "tenant-a",
        },
    )
    repo = FakeRepo([message])
    repo.failure_outcome = "dead_lettered"
    jobs = FakeJobsRepo()
    dispatcher = dispatcher_mod.OutboxDispatcher()
    dispatcher.repo = repo
    dispatcher.jobs = jobs
    dispatcher.js = FakeJetStream(RuntimeError("nats unavailable"))

    await dispatcher.process_batch()

    assert len(jobs.failures) == 1
    failed_job_id, error, kwargs = jobs.failures[0]
    assert failed_job_id == job_id
    assert error == "nats unavailable"
    assert kwargs["execution_id"] == execution_id
    assert kwargs["commit"] is False
