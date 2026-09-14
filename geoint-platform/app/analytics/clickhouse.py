"""ClickHouse analytics client — product queries (not just connectivity)."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)

# Allowlisted query templates only (no arbitrary SQL from clients)
QUERY_TEMPLATES: dict[str, str] = {
    "observations_by_source_24h": """
        SELECT source_id, count() AS n
        FROM geoint.observations
        WHERE tenant_id = {tenant:String}
          AND observed_at >= now() - INTERVAL 24 HOUR
        GROUP BY source_id
        ORDER BY n DESC
        LIMIT 50
    """,
    "observations_per_hour_24h": """
        SELECT toStartOfHour(observed_at) AS hour, count() AS n
        FROM geoint.observations
        WHERE tenant_id = {tenant:String}
          AND observed_at >= now() - INTERVAL 24 HOUR
        GROUP BY hour
        ORDER BY hour
    """,
    "entity_types_24h": """
        SELECT entity_type, count() AS n
        FROM geoint.observations
        WHERE tenant_id = {tenant:String}
          AND observed_at >= now() - INTERVAL 24 HOUR
        GROUP BY entity_type
        ORDER BY n DESC
        LIMIT 30
    """,
    "top_entities_24h": """
        SELECT entity_id, entity_type, count() AS n
        FROM geoint.observations
        WHERE tenant_id = {tenant:String}
          AND observed_at >= now() - INTERVAL 24 HOUR
        GROUP BY entity_id, entity_type
        ORDER BY n DESC
        LIMIT 25
    """,
}


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
            raise ValueError(f"Unknown template_id: {template_id}. Allowed: {sorted(QUERY_TEMPLATES)}")

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
                    log.warning("clickhouse_query_failed status=%s body=%s", r.status_code, r.text[:500])
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
