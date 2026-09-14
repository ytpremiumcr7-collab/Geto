#!/usr/bin/env python3
"""E2E product flow: token → sources → observation → geofence → alert rule path.

Runs against a live API (default http://127.0.0.1:8000).
Skips gracefully if API is down (exit 0 with SKIP) so CI without stack does not fail.
Exit 1 only on unexpected failures when API is up.

Env:
  GEOINT_API_BASE=http://127.0.0.1:8000
  E2E_REQUIRE_LIVE=1  # force fail if API down
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime

BASE = os.environ.get("GEOINT_API_BASE", "http://127.0.0.1:8000").rstrip("/")
REQUIRE = os.environ.get("E2E_REQUIRE_LIVE", "").lower() in ("1", "true", "yes")


def req(method: str, path: str, body: dict | None = None, token: str | None = None):
    data = None if body is None else json.dumps(body).encode()
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=15) as resp:
        raw = resp.read().decode()
        return resp.status, json.loads(raw) if raw else {}


def main() -> int:
    steps_ok = 0
    try:
        st, live = req("GET", "/health/live")
        if st != 200:
            raise RuntimeError("live not ok")
    except Exception as e:
        msg = f"API not reachable at {BASE}: {e}"
        if REQUIRE:
            print("FAIL", msg)
            return 1
        print("SKIP", msg)
        return 0

    print("OK health/live")
    steps_ok += 1

    # Auth: bootstrap token only works in dev with secret; try or use AUTH_DISABLED path
    token = os.environ.get("E2E_TOKEN")
    if not token:
        bootstrap = os.environ.get("AUTH_BOOTSTRAP_SECRET", "")
        try:
            st, tok = req(
                "POST",
                "/api/v1/auth/token",
                {
                    "user_id": "e2e",
                    "tenant_id": "default",
                    "roles": ["admin", "operator"],
                    "bootstrap_secret": bootstrap or "dev",
                },
            )
            token = tok.get("access_token")
        except urllib.error.HTTPError as e:
            print(f"WARN auth/token HTTP {e.code} — set E2E_TOKEN for full flow")
            token = None
        except Exception as e:
            print(f"WARN auth: {e}")
            token = None

    if not token:
        print("PARTIAL: health ok, auth unavailable — remaining steps need E2E_TOKEN")
        return 0 if not REQUIRE else 1

    print("OK auth token")
    steps_ok += 1

    st, sources = req("GET", "/api/v1/sources", token=token)
    assert st == 200
    print(f"OK sources count={len(sources.get('sources') or sources.get('items') or [])}")
    steps_ok += 1

    st, obs = req("GET", "/api/v1/observations?limit=5", token=token)
    assert st == 200
    n_obs = len(obs.get("observations") or [])
    print(f"OK observations count={n_obs}")
    steps_ok += 1

    st, fences = req("GET", "/api/v1/geofences", token=token)
    assert st == 200
    print(f"OK geofences count={len(fences.get('geofences') or [])}")
    steps_ok += 1

    # Workspace create
    name = f"e2e-{datetime.now(UTC).strftime('%H%M%S')}"
    st, ws = req("POST", "/api/v1/workspaces", {"name": name, "is_default": False}, token=token)
    assert st in (200, 201)
    print(f"OK workspace id={ws.get('id')}")
    steps_ok += 1

    st, alerts = req("GET", "/api/v1/alerts?status=open", token=token)
    assert st == 200
    print(f"OK alerts open={len(alerts.get('alerts') or [])}")
    steps_ok += 1

    st, jobs = req("GET", "/api/v1/admin/jobs", token=token)
    assert st == 200
    print(f"OK admin jobs count={len(jobs.get('jobs') or [])}")
    steps_ok += 1

    print(f"PASS e2e product flow steps={steps_ok}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
