from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.workers import job_scheduler as scheduler_mod


class FakeSession:
    pass


@asynccontextmanager
async def fake_system_session():
    yield FakeSession()


@asynccontextmanager
async def fake_tenant_session(_tenant_id: str):
    yield FakeSession()


class FakeRepo:
    def __init__(self, jobs):
        self.jobs = jobs
        self.failures = []

    async def claim_due_jobs(self, _session, **_kwargs):
        return self.jobs

    async def mark_failure(self, _session, job_id, error, **kwargs):
        self.failures.append((job_id, error, kwargs))


class FakeJetStream:
    def __init__(self, error: Exception | None = None):
        self.calls = []
        self.error = error

    async def publish_job(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error


@pytest.mark.asyncio
async def test_scheduler_publishes_persisted_execution_identity(monkeypatch):
    monkeypatch.setattr(scheduler_mod, "system_worker_session", fake_system_session)
    monkeypatch.setattr(scheduler_mod, "tenant_session", fake_tenant_session)
    job_id = uuid4()
    execution_id = uuid4()
    job = SimpleNamespace(
        id=job_id,
        execution_id=execution_id,
        source_id="usgs_earthquake",
        job_type="poll",
        config={},
        tenant_id="tenant-a",
    )

    scheduler = scheduler_mod.JobScheduler()
    scheduler.repo = FakeRepo([job])
    scheduler.js = FakeJetStream()

    await scheduler.tick()

    assert scheduler.js.calls == [
        {
            "job_id": job_id,
            "execution_id": execution_id,
            "source_id": "usgs_earthquake",
            "job_type": "poll",
            "config": {},
            "tenant_id": "tenant-a",
        }
    ]


@pytest.mark.asyncio
async def test_scheduler_publish_failure_retries_same_execution(monkeypatch):
    monkeypatch.setattr(scheduler_mod, "system_worker_session", fake_system_session)
    monkeypatch.setattr(scheduler_mod, "tenant_session", fake_tenant_session)
    job_id = uuid4()
    execution_id = uuid4()
    job = SimpleNamespace(
        id=job_id,
        execution_id=execution_id,
        source_id="usgs_earthquake",
        job_type="poll",
        config={},
        tenant_id="tenant-a",
    )

    scheduler = scheduler_mod.JobScheduler()
    scheduler.repo = FakeRepo([job])
    scheduler.js = FakeJetStream(RuntimeError("nats down"))

    await scheduler.tick()

    assert scheduler.repo.failures
    _, _, kwargs = scheduler.repo.failures[0]
    assert kwargs["execution_id"] == execution_id
