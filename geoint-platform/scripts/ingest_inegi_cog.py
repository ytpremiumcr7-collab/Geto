#!/usr/bin/env python3
"""Register an INEGI (or any) COG/GeoTIFF already in MinIO or on disk into dem_assets.

Usage:
  # Local file → upload to MinIO + register
  python -m scripts.ingest_inegi_cog ./CEM_15m_CDMX.tif \\
      --provider inegi --product "CEM 15m CDMX" --resolution 15 \\
      --tenant default

  # Already in MinIO
  python -m scripts.ingest_inegi_cog s3://geoint-raw/dem/mexico/inegi/cem.tif \\
      --provider inegi --product "CEM 15m" --resolution 15 \\
      --bbox -99.4,19.1,-98.9,19.6

  # Auto bbox from raster geotransform
  python -m scripts.ingest_inegi_cog ./mde.tif --provider inegi --product "MDE 5m" --resolution 5

Requires: DATABASE_URL, MINIO_*, and rasterio for bbox inference.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
from pathlib import Path

# allow running as module from project root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _bbox_from_raster(path: str) -> tuple[float, float, float, float, str]:
    import rasterio
    from rasterio.warp import transform_bounds

    with rasterio.open(path) as ds:
        b = ds.bounds
        crs = str(ds.crs) if ds.crs else "EPSG:4326"
        if ds.crs and str(ds.crs) not in ("EPSG:4326", "OGC:CRS84"):
            w, s, e, n = transform_bounds(ds.crs, "EPSG:4326", *b)
        else:
            w, s, e, n = b.left, b.bottom, b.right, b.top
        return float(w), float(s), float(e), float(n), crs


async def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest/register DEM COG for topography")
    ap.add_argument("path", help="Local .tif/.cog path or s3://bucket/key")
    ap.add_argument(
        "--provider",
        default="inegi",
        choices=["inegi", "copernicus_dem", "local", "usgs", "opentopography"],
    )
    ap.add_argument("--product", required=True, help="Product name e.g. 'CEM 15m zona centro'")
    ap.add_argument("--resolution", type=float, required=True, help="Resolution in meters")
    ap.add_argument("--product-type", default="dtm", choices=["dtm", "dsm", "dem"])
    ap.add_argument("--tenant", default="default")
    ap.add_argument("--crs", default=None)
    ap.add_argument("--vertical-datum", default="NAVD88 / local")
    ap.add_argument("--bbox", default=None, help="west,south,east,north (EPSG:4326)")
    ap.add_argument("--version", default=None)
    ap.add_argument("--minio-key", default=None, help="Override object key under dem/")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    from app.core.config import settings
    from app.db.session import SessionLocal
    from app.infrastructure.object_store import ObjectStore
    from app.topography.models import DemAssetCreate, DemProductType, DemProvider
    from app.topography.service import TopographyService

    src = args.path
    local_path: Path | None = None
    file_uri: str
    checksum: str | None = None

    store = ObjectStore()

    if src.startswith("s3://"):
        file_uri = src
        # optional: download to compute bbox if not provided
        if not args.bbox:
            without = src[5:]
            bucket, key = without.split("/", 1)
            data = await store.get_bytes(key, bucket=bucket)
            tmp = Path("/tmp") / f"dem_ingest_{hashlib.md5(key.encode()).hexdigest()[:10]}.tif"
            tmp.write_bytes(data)
            local_path = tmp
    else:
        local_path = Path(src).resolve()
        if not local_path.exists():
            print(f"ERROR: file not found: {local_path}", file=sys.stderr)
            return 1
        checksum = _sha256_file(local_path)
        key = args.minio_key or f"dem/{args.provider}/{local_path.name}"
        if args.dry_run:
            file_uri = f"s3://{settings.minio_bucket_raw}/{key}"
            print(f"[dry-run] would upload → {file_uri}")
        else:
            data = local_path.read_bytes()
            file_uri = await store.put_bytes(key, data, content_type="image/tiff")
            print(f"Uploaded → {file_uri}")

    # bbox
    if args.bbox:
        parts = [float(x.strip()) for x in args.bbox.split(",")]
        if len(parts) != 4:
            print("ERROR: --bbox must be west,south,east,north", file=sys.stderr)
            return 1
        west, south, east, north = parts
        crs = args.crs or "EPSG:4326"
    elif local_path:
        west, south, east, north, crs = _bbox_from_raster(str(local_path))
        if args.crs:
            crs = args.crs
        print(f"BBox from raster: {west:.6f},{south:.6f},{east:.6f},{north:.6f} ({crs})")
    else:
        print("ERROR: provide --bbox when using remote s3 without download", file=sys.stderr)
        return 1

    body = DemAssetCreate(
        provider=DemProvider(args.provider),
        product_name=args.product,
        product_type=DemProductType(args.product_type),
        resolution_m=args.resolution,
        crs=crs,
        vertical_datum=args.vertical_datum,
        bbox_west=west,
        bbox_south=south,
        bbox_east=east,
        bbox_north=north,
        file_uri=file_uri,
        checksum_sha256=checksum,
        source_version=args.version,
        extra={"ingested_by": "scripts.ingest_inegi_cog"},
    )

    if args.dry_run:
        print("[dry-run] would register:", body.model_dump())
        return 0

    async with SessionLocal() as session:
        svc = TopographyService(session)
        asset = await svc.register_dem(args.tenant, body)
        print("Registered dem_id:", asset.get("id"))
        print("  provider:", asset.get("provider"))
        print("  product:", asset.get("product_name"))
        print("  resolution_m:", asset.get("resolution_m"))
        print("  file_uri:", asset.get("file_uri"))
        print(
            "  bbox:",
            asset.get("bbox_west"),
            asset.get("bbox_south"),
            asset.get("bbox_east"),
            asset.get("bbox_north"),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
