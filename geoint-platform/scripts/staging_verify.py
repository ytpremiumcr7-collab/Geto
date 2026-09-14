#!/usr/bin/env python3
"""Staging real checks: JWKS, ClickHouse data, alert notifier health.

Exit 0 only if all required checks pass (or SKIP with --allow-skip for partial lab).

Env:
  JWT_JWKS_URL, JWT_ISSUER (optional)
  CLICKHOUSE_URL, CLICKHOUSE_ENABLED
  ALERT_NOTIFIER_HEALTH_URL (default http://127.0.0.1:8081)
  GEOINT_API_BASE (default http://127.0.0.1:8000)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def get(url: str, timeout: float = 10.0) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode()


def post(url: str, body: str) -> tuple[int, str]:
    req = urllib.request.Request(
        url,
        data=body.encode(),
        headers={"Content-Type": "text/plain"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, resp.read().decode()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-skip", action="store_true", help="exit 0 if optional deps down")
    args = ap.parse_args()
    failed = 0
    skipped = 0

    print("=== staging_verify ===\n")

    # 1) JWKS
    jwks_url = os.environ.get("JWT_JWKS_URL", "").strip()
    if not jwks_url:
        print("FAIL  JWT_JWKS_URL not set")
        failed += 1
    else:
        try:
            st, body = get(jwks_url)
            data = json.loads(body)
            keys = data.get("keys") or []
            if st == 200 and keys:
                print(f"PASS  JWKS {jwks_url} keys={len(keys)}")
            else:
                print(f"FAIL  JWKS empty or bad status={st}")
                failed += 1
        except Exception as e:
            print(f"FAIL  JWKS {e}")
            failed += 1

    # 2) ClickHouse
    ch_enabled = os.environ.get("CLICKHOUSE_ENABLED", "").lower() in ("1", "true", "yes")
    ch_url = os.environ.get("CLICKHOUSE_URL", "http://127.0.0.1:8123").rstrip("/")
    if not ch_enabled:
        print("SKIP  CLICKHOUSE_ENABLED not true")
        skipped += 1
    else:
        try:
            st, _ = get(f"{ch_url}/ping")
            if st != 200:
                raise RuntimeError(f"ping {st}")
            st, body = post(
                f"{ch_url}/?default_format=JSON",
                "SELECT count() AS n FROM geoint.observations",
            )
            if st >= 400:
                raise RuntimeError(body[:200])
            rows = json.loads(body).get("data") or []
            n = int(rows[0]["n"]) if rows else 0
            if n <= 0:
                print(f"FAIL  ClickHouse observations empty (n={n}) — run bootstrap + seed")
                failed += 1
            else:
                print(f"PASS  ClickHouse geoint.observations n={n}")
        except Exception as e:
            print(f"FAIL  ClickHouse {e}")
            failed += 1

    # 3) Alert notifier health
    health = os.environ.get("ALERT_NOTIFIER_HEALTH_URL", "http://127.0.0.1:8081").rstrip("/")
    try:
        st, body = get(f"{health}/health/live")
        live = json.loads(body)
        if st != 200 or live.get("status") != "live":
            raise RuntimeError(f"live {st} {body[:120]}")
        print(f"PASS  notifier live @ {health}")
        try:
            st2, body2 = get(f"{health}/health/ready")
            ready = json.loads(body2)
            if st2 == 200 and ready.get("status") == "ready":
                print(f"PASS  notifier ready ticks={ready.get('ticks')}")
            else:
                print(f"WARN  notifier not ready yet: {body2[:160]}")
        except Exception as e:
            print(f"WARN  notifier ready: {e}")
    except Exception as e:
        print(f"FAIL  notifier health {e}")
        failed += 1

    # 4) Optional API
    api = os.environ.get("GEOINT_API_BASE", "http://127.0.0.1:8000").rstrip("/")
    try:
        st, body = get(f"{api}/health/live")
        if st == 200:
            print(f"PASS  API live @ {api}")
        else:
            print(f"WARN  API status {st}")
    except Exception as e:
        print(f"SKIP  API {e}")
        skipped += 1

    print()
    if failed:
        print(f"RESULT FAIL failed={failed} skipped={skipped}")
        return 0 if args.allow_skip and failed == 0 else 1
    print(f"RESULT OK skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
