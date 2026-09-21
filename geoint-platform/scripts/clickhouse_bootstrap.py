#!/usr/bin/env python3
"""Apply deploy/clickhouse/init.sql and optionally seed sample rows."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

URL = os.environ.get("CLICKHOUSE_URL", "http://localhost:8123").rstrip("/")
INIT = Path(__file__).resolve().parents[1] / "deploy" / "clickhouse" / "init.sql"


def _statements(sql: str) -> list[str]:
    # init.sql contains only simple statements. Strip comment-only lines before
    # splitting so a leading comment cannot accidentally discard the statement
    # that follows it in the same semicolon-delimited chunk.
    uncommented = "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    )
    return [statement.strip() for statement in uncommented.split(";") if statement.strip()]


def main() -> int:
    statements = _statements(INIT.read_text())
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
            seed_path = (
                Path(__file__).resolve().parents[1]
                / "scripts"
                / "clickhouse_seed_staging.sql"
            )
            if seed_path.exists():
                seed = seed_path.read_text()
            else:
                seed = """
                INSERT INTO geoint.observations
                (tenant_id, source_id, entity_id, entity_type, observed_at, lon, lat)
                VALUES
                ('default', 'opensky', 'SEED-1', 'aircraft', now64(3), -99.1, 19.4)
                """
            r = client.post(f"{URL}/", content=seed.encode())
            print("SEED", r.status_code, r.text[:120])
    print("ClickHouse bootstrap OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
