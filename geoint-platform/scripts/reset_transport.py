#!/usr/bin/env python3
"""Reset ephemeral transport state during an explicitly confirmed DR restore."""

from __future__ import annotations

import asyncio
import os

import nats
import redis.asyncio as redis
from nats.js.errors import NotFoundError

from app.core.config import settings


async def main() -> int:
    if os.environ.get("RESTORE_CONFIRM") != "YES":
        raise SystemExit("refusing transport reset; RESTORE_CONFIRM=YES is required")

    cache = redis.from_url(settings.redis_url, decode_responses=True)
    try:
        await cache.flushdb()
    finally:
        await cache.aclose()

    nc = await nats.connect(settings.nats_url, name="geoint-dr-reset")
    try:
        js = nc.jetstream()
        for stream in (settings.nats_stream, f"{settings.nats_stream}_DLQ"):
            try:
                await js.delete_stream(stream)
                print("deleted JetStream stream", stream)
            except NotFoundError:
                print("JetStream stream already absent", stream)
    finally:
        await nc.drain()

    print("transport reset complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
