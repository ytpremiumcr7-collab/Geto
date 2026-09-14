"""Clip bbox + synthetic DEM pipeline tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")
from rasterio.transform import from_origin

from app.topography.engine import TopographyEngine


def _dem(path: str, size: int = 100):
    data = np.zeros((size, size), dtype=np.float32)
    for r in range(size):
        for c in range(size):
            data[r, c] = 500.0 + r + c * 0.5
    # 0.01 deg ~ 1km, origin -99.5, 19.9
    transform = from_origin(-99.5, 19.9, 0.01, 0.01)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=size,
        width=size,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
        nodata=-9999,
    ) as dst:
        dst.write(data, 1)


def test_clip_bbox_reduces_extent():
    engine = TopographyEngine()
    with tempfile.TemporaryDirectory() as td:
        src = str(Path(td) / "src.tif")
        dst = str(Path(td) / "clip.tif")
        _dem(src, size=100)
        # clip center region
        engine.clip_bbox(src, dst, [-99.2, 19.4, -99.0, 19.7])
        with rasterio.open(dst) as ds:
            assert ds.width < 100 or ds.height < 100
            assert ds.bounds.left >= -99.25
            assert ds.bounds.right <= -98.95


def test_slope_after_clip():
    pytest.importorskip("osgeo.gdal")
    engine = TopographyEngine()
    with tempfile.TemporaryDirectory() as td:
        src = str(Path(td) / "src.tif")
        clip = str(Path(td) / "clip.tif")
        slope = str(Path(td) / "slope.tif")
        _dem(src, size=80)
        engine.clip_bbox(src, clip, [-99.3, 19.3, -99.1, 19.6])
        stats = engine.slope_raster(clip, slope)
        assert stats.get("width", 0) > 0
        assert Path(slope).exists()
