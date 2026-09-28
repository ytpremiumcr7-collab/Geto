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

    main = next(cfg for cfg in fake.configs if "geoint.jobs.>" in cfg.subjects)
    assert "geoint.event.>" in main.subjects
    assert "geoint.alert.>" in main.subjects
    assert "geoint.ingestion.>" in main.subjects


def test_duplicate_window_covers_full_outbox_retry_horizon(monkeypatch):
    from app.messaging import jetstream as jetstream_mod

    monkeypatch.setattr(jetstream_mod.settings, "outbox_max_attempts", 8)
    monkeypatch.setattr(jetstream_mod.settings, "outbox_base_backoff_seconds", 5)
    monkeypatch.setattr(jetstream_mod.settings, "outbox_lease_seconds", 120)

    # 7 delayed retries: 5+10+20+40+80+160+320 = 635 seconds.
    # Add two lease windows so a publish-success / DB-commit-failure race remains
    # within NATS duplicate tracking even after a lease expires and is reclaimed.
    assert jetstream_mod.outbox_duplicate_window_seconds() >= 875

    client = JetStreamClient()
    fake = _FakeJs()
    client.js = fake
    asyncio.run(client.ensure_streams())

    main = next(cfg for cfg in fake.configs if "geoint.jobs.>" in cfg.subjects)
    assert main.duplicate_window >= 875


def test_source_worker_does_not_define_a_second_stream_topology():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2] / "app" / "workers" / "source_worker.py"
    ).read_text()

    assert "StreamConfig(" not in source
    assert "add_stream(" not in source
