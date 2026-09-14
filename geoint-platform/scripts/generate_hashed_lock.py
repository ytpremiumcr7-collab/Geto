#!/usr/bin/env python3
"""Regenerate requirements.lock.txt with PyPI SHA256 hashes from requirements.in.

Usage:
  python scripts/generate_hashed_lock.py

Then install:
  pip install --require-hashes -r requirements.lock.txt
  pip install --no-deps -e .
"""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IN_FILE = ROOT / "requirements.in"
OUT_FILE = ROOT / "requirements.lock.txt"


def pypi_info(name: str, version: str | None = None) -> dict:
    url = (
        f"https://pypi.org/pypi/{name}/{version}/json"
        if version
        else f"https://pypi.org/pypi/{name}/json"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "geoint-lock/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def hashes_for(name: str, version: str) -> list[str]:
    data = pypi_info(name, version)
    out: list[str] = []
    for f in data.get("urls") or []:
        if f.get("packagetype") not in ("bdist_wheel", "sdist"):
            continue
        h = (f.get("digests") or {}).get("sha256")
        if h and h not in out:
            out.append(h)
    return out


def main() -> None:
    pins: list[tuple[str, str]] = []
    for line in IN_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "==" not in line:
            continue
        n, v = line.split("==", 1)
        pins.append((n.strip(), v.strip()))

    out = [
        "# geoint-platform locked dependencies with SHA256 hashes",
        "# Install third-party deps:",
        "#   pip install --require-hashes -r requirements.lock.txt",
        "# Then the local project (no deps — already satisfied by the lock):",
        "#   pip install --no-deps -e .",
        "# Regenerate: python scripts/generate_hashed_lock.py",
        "",
    ]
    for name, ver in pins:
        hs = hashes_for(name, ver)
        if not hs:
            raise SystemExit(f"No hashes for {name}=={ver}")
        out.append(f"{name}=={ver} \\")
        for i, h in enumerate(hs):
            cont = " \\" if i < len(hs) - 1 else ""
            out.append(f"    --hash=sha256:{h}{cont}")
        print(f"OK {name}=={ver} ({len(hs)} hashes)")
        time.sleep(0.1)
    OUT_FILE.write_text("\n".join(out) + "\n")
    print(f"Wrote {OUT_FILE}")


if __name__ == "__main__":
    main()
