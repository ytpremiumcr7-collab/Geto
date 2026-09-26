from __future__ import annotations

import asyncio
from uuid import uuid4

from app.messaging.jetstream import JetStreamClient


class _FakeJetStream:
    def __init__(self):
        self.calls = []

    async def publish(self, subject, payload, headers=None):
        self.calls.append((subject, payload, headers))


def test_recurring_job_publication_uses_execution_id_not_job_id():
    client = JetStreamClient()
    fake = _FakeJetStream()
    client.js = fake
    job_id = uuid4()
    execution_id = uuid4()

    asyncio.run(
        client.publish_job(
            job_id=job_id,
            execution_id=execution_id,
            source_id="usgs_earthquake",
            job_type="poll",
            config={},
            tenant_id="tenant-a",
        )
    )

    assert len(fake.calls) == 1
    _, _, headers = fake.calls[0]
    assert headers["Nats-Msg-Id"] == str(execution_id)
