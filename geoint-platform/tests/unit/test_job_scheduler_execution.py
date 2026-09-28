from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.workers import job_scheduler as scheduler_mod


class FakeSession:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


session = FakeSession()


@asynccontextmanager
async def fake_system_session():
    yield session


class FakeRepo:
    def __init__(self, jobs):
        self.jobs = jobs

    async def claim_due_jobs(self, _session, **_kwargs):
        return self.jobs


class FakeOutbox:
    def __init__(self):
        self.calls = []

    async def enqueue(self, _session, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(id=uuid4())


@pytest.mark.asyncio
async def test_scheduler_enqueues_dispatch_in_same_database_transaction(monkeypatch):
    session.commits = 0
    monkeypatch.setattr(scheduler_mod, "system_worker_session", fake_system_session)
    job_id = uuid4()
    execution_id = uuid4()
    job = SimpleNamespace(
        id=job_id,
        execution_id=execution_id,
        source_id="usgs_earthquake",
        job_type="poll",
        config={"x": 1},
        tenant_id="tenant-a",
    )

    scheduler = scheduler_mod.JobScheduler()
    scheduler.repo = FakeRepo([job])
    scheduler.outbox = FakeOutbox()

    await scheduler.tick()

    assert scheduler.outbox.calls == [
        {
            "subject": "geoint.jobs.usgs_earthquake",
            "payload": {
                "job_id": str(job_id),
                "execution_id": str(execution_id),
                "source_id": "usgs_earthquake",
                "job_type": "poll",
                "config": {"x": 1},
                "tenant_id": "tenant-a",
            },
            "tenant_id": "tenant-a",
        }
    ]
    assert session.commits == 1


def test_scheduler_has_no_direct_broker_dependency():
    scheduler = scheduler_mod.JobScheduler()
    assert not hasattr(scheduler, "js")
