#!/usr/bin/env python3
"""Apply deploy/clickhouse/init.sql and optionally seed sample rows."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

URL = os.environ.get("CLICKHOUSE_URL", "http://localhost:8123").rstrip("/")
INIT = Path(__file__).resolve().parents[1] / "deploy" / "clickhouse" / "init.sql"


def main() -> int:
    sql = INIT.read_text()
    # Split on semicolons carefully — simple statements only
    statements = [s.strip() for s in sql.split(";") if s.strip() and not s.strip().startswith("--")]
    with httpx.Client(timeout=30.0) as client:
        r = client.get(f"{URL}/ping")
        if r.status_code != 200:
            print(f"FAIL ping {r.status_code}", file=sys.stderr)
            return 1
        for stmt in statements:
            r = client.post(f"{URL}/", content=stmt.encode())
            if r.status_code >= 400:
                print(f"FAIL {r.status_code}: {r.text[:300]}", file=sys.stderr)
                return 1
            print("OK", stmt.split()[0:4])
        if os.environ.get("CLICKHOUSE_SEED") == "1":
            seed = """
            INSERT INTO geoint.observations
            (tenant_id, source_id, entity_id, entity_type, observed_at, lon, lat)
            VALUES
            ('default', 'opensky', 'SEED-1', 'aircraft', now64(3), -99.1, 19.4)
            """
            r = client.post(f"{URL}/", content=seed.encode())
            print("SEED", r.status_code, r.text[:80])
    print("ClickHouse bootstrap OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
