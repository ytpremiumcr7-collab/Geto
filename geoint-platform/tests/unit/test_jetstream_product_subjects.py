from __future__ import annotations

import asyncio

from app.messaging.jetstream import JetStreamClient


class _FakeJs:
    def __init__(self):
        self.configs = []

    async def stream_info(self, _name):
        raise RuntimeError("missing")

    async def add_stream(self, config):
        self.configs.append(config)

    async def update_stream(self, config):
        self.configs.append(config)


def test_main_stream_covers_all_product_subjects():
    client = JetStreamClient()
    fake = _FakeJs()
    client.js = fake

    asyncio.run(client.ensure_streams())

    main = next(
        cfg for cfg in fake.configs if "geoint.jobs.>" in cfg.subjects
    )
    assert "geoint.event.>" in main.subjects
    assert "geoint.alert.>" in main.subjects
    assert "geoint.ingestion.>" in main.subjects
