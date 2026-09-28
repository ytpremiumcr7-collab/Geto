from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.sources.s3_dropzone.adapter import S3DropzoneAdapter


async def _collect(adapter, raw):
    return [item async for item in adapter.normalize(raw, datetime.now(UTC))]


def _adapter_without_s3_backend():
    adapter = object.__new__(S3DropzoneAdapter)
    adapter.bucket = "drop"
    adapter.prefix_processed = "processed/"
    adapter.prefix_failed = "failed/"
    adapter.moved = []

    def mark_processed(key: str, *, failed: bool = False):
        adapter.moved.append((key, failed))

    adapter.mark_processed = mark_processed
    return adapter


def test_normalize_does_not_ack_input_before_database_commit():
    adapter = _adapter_without_s3_backend()
    raw = [
        {
            "key": "incoming/a.json",
            "payload": {"id": "asset-1", "lon": -99.1, "lat": 19.4},
        }
    ]

    rows = asyncio.run(_collect(adapter, raw))

    assert len(rows) == 1
    assert adapter.moved == []


def test_after_commit_acknowledges_dropzone_inputs():
    adapter = _adapter_without_s3_backend()
    raw = [
        {
            "key": "incoming/a.json",
            "payload": {"id": "asset-1", "lon": -99.1, "lat": 19.4},
        }
    ]

    asyncio.run(adapter.after_commit(raw))

    assert adapter.moved == [("incoming/a.json", False)]
