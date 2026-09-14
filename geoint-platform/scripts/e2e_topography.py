#!/usr/bin/env python3
"""E2E topography without full Docker stack.

Validates against samples/synthetic_cdmx_dem.tif:
  1) sample elevation
  2) profile
  3) clip bbox
  4) LOS
  5) Terrarium live (network)
  6) ObjectStore mock roundtrip

Exit 0 only if all critical checks pass.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEM = ROOT / "samples" / "synthetic_cdmx_dem.tif"
PASS = 0
FAIL = 0


def ok(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}  {detail}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


def main() -> int:
    print("=== E2E Topography ===")
    ok("dem_file_exists", DEM.exists(), str(DEM))
    if not DEM.exists():
        return 1

    from app.topography.engine import TopographyEngine
    from app.topography.providers import AwsTerrariumProvider, decode_terrarium_rgb

    engine = TopographyEngine()

    # 1 elevation center-ish
    lon, lat = -99.05, 19.35
    elev = engine.sample_elevation(str(DEM), lon, lat)
    ok("sample_elevation", elev is not None and 1900 < elev < 2600, f"elev={elev}")

    # 2 profile
    coords = [[-99.20, 19.40], [-99.00, 19.30]]
    pts = engine.profile(str(DEM), coords, sample_distance_m=50)
    ok("profile_points", len(pts) >= 5, f"n={len(pts)}")
    elevs = [p["elevation_m"] for p in pts if p["elevation_m"] is not None]
    ok("profile_has_elev", len(elevs) >= 3, f"elev_samples={len(elevs)}")

    # 3 clip
    with tempfile.TemporaryDirectory() as td:
        clip = str(Path(td) / "clip.tif")
        engine.clip_bbox(str(DEM), clip, [-99.15, 19.25, -99.00, 19.45])
        ok("clip_exists", Path(clip).stat().st_size > 1000)
        elev2 = engine.sample_elevation(clip, -99.10, 19.35)
        ok("clip_sample", elev2 is not None, f"elev={elev2}")

        # 4 LOS on clipped
        los = engine.line_of_sight(clip, -99.12, 19.38, -99.05, 19.30, observer_height_m=2.0)
        ok("los_keys", "visible" in los and "profile" in los, f"visible={los.get('visible')}")

    # 5 terrarium decode unit
    ok("terrarium_decode_sealevel", abs(decode_terrarium_rgb(128, 0, 0)) < 0.01)

    # 6 live terrarium
    async def live():
        p = AwsTerrariumProvider(zoom=12)
        return await p.sample_point(-99.1332, 19.4326)

    try:
        r = asyncio.run(live())
        ok(
            "terrarium_live_cdmx",
            r is not None and r.get("elevation_m") is not None and 1500 < r["elevation_m"] < 3000,
            f"elev={r.get('elevation_m') if r else None}",
        )
    except Exception as e:
        ok("terrarium_live_cdmx", False, str(e))

    # 7 object store mock
    try:
        from unittest.mock import MagicMock, patch

        import app.infrastructure.object_store as osm

        store_data: dict[str, bytes] = {}
        mock = MagicMock()
        mock.bucket_exists.return_value = True

        def put_object(bucket, key, data, length, content_type=None):
            store_data[f"{bucket}/{key}"] = data.read() if hasattr(data, "read") else data

        def get_object(bucket, key):
            resp = MagicMock()
            resp.read.return_value = store_data[f"{bucket}/{key}"]
            resp.close = MagicMock()
            resp.release_conn = MagicMock()
            return resp

        mock.put_object.side_effect = put_object
        mock.get_object.side_effect = get_object
        with patch.object(osm, "Minio", return_value=mock):
            with patch.object(osm, "settings") as s:
                s.minio_endpoint = "localhost:9000"
                s.minio_access_key = "x"
                s.minio_secret_key = "y"
                s.minio_secure = False
                s.minio_bucket_raw = "geoint-raw"
                store = osm.ObjectStore()
                payload = DEM.read_bytes()[:4096]
                uri = store._put_bytes_sync("dem/test/e2e.tif", payload, "image/tiff")
                got = store._get_bytes_sync("dem/test/e2e.tif")
                ok("minio_mock_roundtrip", got == payload, uri)
    except Exception as e:
        ok("minio_mock_roundtrip", False, str(e))

    print(f"\n=== Result: {PASS} passed, {FAIL} failed ===")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
