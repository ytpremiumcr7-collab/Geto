#!/usr/bin/env python3
"""Rebuild derived ClickHouse observation analytics from authoritative Postgres."""

from __future__ import annotations

import asyncio
from uuid import UUID

import httpx
from sqlalchemy import text

from app.analytics.clickhouse import ClickHouseSink, clickhouse_http_auth
from app.core.config import settings
from app.db.tenant import system_worker_session

BATCH_SIZE = 1000


async def _truncate() -> None:
    auth = clickhouse_http_auth()
    async with httpx.AsyncClient(timeout=30.0, auth=auth) as client:
        response = await client.post(
            f"{settings.clickhouse_url.rstrip('/')}/",
            content=b"TRUNCATE TABLE IF EXISTS geoint.observations",
        )
        response.raise_for_status()


async def _tenants() -> list[str]:
    async with system_worker_session() as session:
        result = await session.execute(
            text("SELECT DISTINCT tenant_id FROM observations ORDER BY tenant_id")
        )
        return [str(row[0]) for row in result.all()]


async def _rebuild_tenant(tenant_id: str) -> int:
    sink = ClickHouseSink()
    if not sink.enabled:
        raise RuntimeError("CLICKHOUSE_ENABLED=true is required for analytics rebuild")

    total = 0
    after: UUID | None = None
    while True:
        after_clause = "AND id > CAST(:after_id AS uuid)" if after is not None else ""
        query = f"""
            SELECT
                id,
                source_id,
                entity_id,
                entity_type,
                observed_at,
                received_at,
                ST_X(geometry) AS lon,
                ST_Y(geometry) AS lat,
                ST_Z(geometry) AS altitude_m,
                speed_mps,
                heading_deg,
                confidence
            FROM observations
            WHERE tenant_id = :tenant_id
              AND geometry IS NOT NULL
              {after_clause}
            ORDER BY id
            LIMIT :batch_size
        """
        params = {"tenant_id": tenant_id, "batch_size": BATCH_SIZE}
        if after is not None:
            params["after_id"] = str(after)
        async with system_worker_session() as session:
            result = await session.execute(text(query), params)
            rows = list(result.mappings().all())

        if not rows:
            return total

        payload = [
            {
                "source_id": row["source_id"],
                "entity_id": row["entity_id"],
                "entity_type": row["entity_type"],
                "observed_at": row["observed_at"].isoformat(),
                "received_at": row["received_at"].isoformat(),
                "position": {
                    "lon": float(row["lon"]),
                    "lat": float(row["lat"]),
                    "altitude_m": (
                        float(row["altitude_m"]) if row["altitude_m"] is not None else None
                    ),
                },
                "speed_mps": row["speed_mps"],
                "heading_deg": row["heading_deg"],
                "confidence": row["confidence"],
            }
            for row in rows
        ]
        total += await sink.write_observations(payload, tenant_id=tenant_id)
        after = rows[-1]["id"]


async def main() -> int:
    if not settings.clickhouse_enabled:
        print("ClickHouse disabled; rebuild skipped")
        return 0

    await _truncate()
    total = 0
    for tenant_id in await _tenants():
        inserted = await _rebuild_tenant(tenant_id)
        total += inserted
        print("rebuilt tenant", tenant_id, "rows", inserted)

    print("ClickHouse rebuild complete", total)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
