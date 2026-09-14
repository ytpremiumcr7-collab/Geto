"""Sink analítico ClickHouse (observaciones agregables / replay analytics).

ClickHouse ya está en docker-compose. Este writer es at-least-once best-effort:
no sustituye PostGIS como fuente de verdad operacional.
"""

from __future__ import annotations

from typing import Any

import structlog

from app.core.config import settings

log = structlog.get_logger()

DDL = """
CREATE TABLE IF NOT EXISTS geoint_observations (
    tenant_id String,
    entity_id String,
    entity_type String,
    source_id String,
    observed_at DateTime64(3, 'UTC'),
    received_at DateTime64(3, 'UTC'),
    lon Nullable(Float64),
    lat Nullable(Float64),
    altitude_m Nullable(Float64),
    speed_mps Nullable(Float64),
    heading_deg Nullable(Float64),
    confidence Nullable(Float64)
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(observed_at)
ORDER BY (tenant_id, source_id, entity_id, observed_at)
"""


class ClickHouseSink:
    def __init__(self) -> None:
        self.url = getattr(settings, "clickhouse_url", "http://localhost:8123")
        self.enabled = getattr(settings, "clickhouse_enabled", False)
        self._ready = False

    async def ensure_schema(self) -> None:
        if not self.enabled:
            return
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(self.url, content=DDL)
            r.raise_for_status()
        self._ready = True

    async def write_observations(
        self,
        rows: list[dict[str, Any]],
        tenant_id: str = "default",
    ) -> int:
        if not self.enabled or not rows:
            return 0
        if not self._ready:
            await self.ensure_schema()
        import httpx

        lines = []
        for o in rows:
            pos = o.get("position") or {}
            lines.append(
                {
                    "tenant_id": tenant_id,
                    "entity_id": o.get("entity_id"),
                    "entity_type": o.get("entity_type"),
                    "source_id": o.get("source_id"),
                    "observed_at": o.get("observed_at"),
                    "received_at": o.get("received_at"),
                    "lon": pos.get("lon"),
                    "lat": pos.get("lat"),
                    "altitude_m": pos.get("altitude_m"),
                    "speed_mps": o.get("speed_mps"),
                    "heading_deg": o.get("heading_deg"),
                    "confidence": o.get("confidence"),
                }
            )
        # JSONEachRow
        body = "\n".join(__import__("json").dumps(x, default=str) for x in lines)
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"{self.url}/?query=INSERT%20INTO%20geoint_observations%20FORMAT%20JSONEachRow",
                content=body,
                headers={"Content-Type": "application/json"},
            )
            if not r.is_success:
                log.warning("clickhouse_insert_failed", status=r.status_code, body=r.text[:300])
                return 0
        return len(lines)
