"""ClickHouse analytics client — product queries (not just connectivity)."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)

# Allowlisted query templates only (no arbitrary SQL from clients)
QUERY_TEMPLATES: dict[str, str] = {
    "observations_by_source_24h": """
        SELECT source_id, uniqExact(observation_id) AS n
        FROM geoint.observations
        WHERE tenant_id = {tenant:String}
          AND observed_at >= now() - INTERVAL 24 HOUR
        GROUP BY source_id
        ORDER BY n DESC
        LIMIT 50
    """,
    "observations_per_hour_24h": """
        SELECT toStartOfHour(observed_at) AS hour, uniqExact(observation_id) AS n
        FROM geoint.observations
        WHERE tenant_id = {tenant:String}
          AND observed_at >= now() - INTERVAL 24 HOUR
        GROUP BY hour
        ORDER BY hour
    """,
    "entity_types_24h": """
        SELECT entity_type, uniqExact(observation_id) AS n
        FROM geoint.observations
        WHERE tenant_id = {tenant:String}
          AND observed_at >= now() - INTERVAL 24 HOUR
        GROUP BY entity_type
        ORDER BY n DESC
        LIMIT 30
    """,
    "top_entities_24h": """
        SELECT entity_id, entity_type, uniqExact(observation_id) AS n
        FROM geoint.observations
        WHERE tenant_id = {tenant:String}
          AND observed_at >= now() - INTERVAL 24 HOUR
        GROUP BY entity_id, entity_type
        ORDER BY n DESC
        LIMIT 25
    """,
}


def _observed_at_epoch_ms(value: Any) -> int:
    if isinstance(value, datetime):
        observed_at = value
    else:
        raw = str(value or "").strip()
        if not raw:
            raise ValueError("observed_at is required for analytics identity")
        if raw.endswith("Z"):
            raw = f"{raw[:-1]}+00:00"
        observed_at = datetime.fromisoformat(raw)

    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=UTC)
    else:
        observed_at = observed_at.astimezone(UTC)

    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    delta = observed_at - epoch
    return delta.days * 86_400_000 + delta.seconds * 1_000 + delta.microseconds // 1_000


def observation_identity(tenant_id: str, row: dict[str, Any]) -> str:
    """Stable hash of the same fields as the PostgreSQL observation uniqueness key."""
    source_id = str(row.get("source_id") or "")
    entity_id = str(row.get("entity_id") or "")
    observed_at_ms = _observed_at_epoch_ms(row.get("observed_at"))
    material = "\x1f".join((tenant_id, source_id, entity_id, str(observed_at_ms)))
    return hashlib.sha256(material.encode("utf-8")).hexdigest().upper()


class ClickHouseSink:
    """Write normalized observation batches through ClickHouse HTTP.

    The caller supplies tenant_id server-side; row data cannot override it.
    Writes raise on HTTP errors so the transactional outbox can retry safely.
    """

    def __init__(self, url: str | None = None):
        self.url = (url or settings.clickhouse_url).rstrip("/")
        self.enabled = bool(getattr(settings, "clickhouse_enabled", False))

    async def write_observations(
        self,
        rows: list[dict[str, Any]],
        *,
        tenant_id: str,
    ) -> int:
        if not self.enabled or not rows:
            return 0

        normalized: list[dict[str, Any]] = []
        for row in rows:
            position = row.get("position") or {}
            lon = position.get("lon")
            lat = position.get("lat")
            if lon is None or lat is None:
                log.warning(
                    "clickhouse_observation_without_position tenant=%s source=%s entity=%s",
                    tenant_id,
                    row.get("source_id"),
                    row.get("entity_id"),
                )
                continue

            properties = {
                "received_at": row.get("received_at"),
                "speed_mps": row.get("speed_mps"),
                "heading_deg": row.get("heading_deg"),
                "confidence": row.get("confidence"),
            }
            normalized.append(
                {
                    "observation_id": observation_identity(tenant_id, row),
                    "tenant_id": tenant_id,
                    "source_id": str(row.get("source_id") or ""),
                    "entity_id": str(row.get("entity_id") or ""),
                    "entity_type": str(row.get("entity_type") or "unknown"),
                    "observed_at": row.get("observed_at"),
                    "lon": float(lon),
                    "lat": float(lat),
                    "alt_m": position.get("altitude_m"),
                    "properties": json.dumps(
                        properties,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        default=str,
                    ),
                }
            )

        if not normalized:
            return 0

        query = (
            "INSERT INTO geoint.observations "
            "(observation_id, tenant_id, source_id, entity_id, entity_type, observed_at, "
            "lon, lat, alt_m, properties) FORMAT JSONEachRow"
        )
        body = "\n".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":"), default=str)
            for row in normalized
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.url}/",
                params={"query": query, "date_time_input_format": "best_effort"},
                content=body.encode("utf-8"),
                headers={"Content-Type": "application/x-ndjson"},
            )
            response.raise_for_status()
        return len(normalized)


class ClickHouseClient:
    def __init__(self, url: str | None = None):
        self.url = (url or settings.clickhouse_url).rstrip("/")
        self.enabled = bool(getattr(settings, "clickhouse_enabled", False))

    async def ping(self) -> bool:
        if not self.enabled:
            return False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self.url}/ping")
                return r.status_code == 200
        except Exception:
            return False

    async def query(
        self,
        template_id: str,
        *,
        tenant_id: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.enabled:
            return {
                "enabled": False,
                "template_id": template_id,
                "rows": [],
                "note": "ClickHouse disabled (CLICKHOUSE_ENABLED=false)",
            }
        sql = QUERY_TEMPLATES.get(template_id)
        if not sql:
            allowed = sorted(QUERY_TEMPLATES)
            raise ValueError(f"Unknown template_id: {template_id}. Allowed: {allowed}")

        # Parameterized via ClickHouse HTTP query params
        q_params = {
            "default_format": "JSON",
            "param_tenant": tenant_id,
        }
        if params:
            for k, v in params.items():
                q_params[f"param_{k}"] = str(v)

        body = sql.strip()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(
                    f"{self.url}/?{urlencode(q_params)}",
                    content=body.encode("utf-8"),
                    headers={"Content-Type": "text/plain"},
                )
                if r.status_code >= 400:
                    log.warning(
                        "clickhouse_query_failed status=%s body=%s",
                        r.status_code,
                        r.text[:500],
                    )
                    return {
                        "enabled": True,
                        "template_id": template_id,
                        "rows": [],
                        "error": f"ClickHouse HTTP {r.status_code}",
                        "detail": r.text[:500],
                    }
                data = r.json()
                rows = data.get("data") or []
                return {
                    "enabled": True,
                    "template_id": template_id,
                    "rows": rows,
                    "statistics": data.get("statistics"),
                    "meta": data.get("meta"),
                }
        except Exception as e:
            log.exception("clickhouse_query_error")
            return {
                "enabled": True,
                "template_id": template_id,
                "rows": [],
                "error": str(e),
            }

    def list_templates(self) -> list[dict[str, str]]:
        return [
            {"id": k, "description": v.strip().split("\n")[0][:120]}
            for k, v in QUERY_TEMPLATES.items()
        ]
