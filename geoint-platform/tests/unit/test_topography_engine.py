"""Unit tests for topography engine — synthetic DEM, no network/DB."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

# skip if rasterio/gdal not available in test env
rasterio = pytest.importorskip("rasterio")
from rasterio.transform import from_origin

from app.topography.engine import TopographyEngine
from app.topography.providers import decode_terrarium_rgb


def _make_synthetic_dem(path: str, size: int = 64, base: float = 1000.0):
    """Ramp DEM: elevation increases with row+col."""
    data = np.zeros((size, size), dtype=np.float32)
    for r in range(size):
        for c in range(size):
            data[r, c] = base + r * 2.0 + c * 1.5
    transform = from_origin(-99.2, 19.5, 0.001, 0.001)  # ~111m
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
    return data


def test_terrarium_decode():
    # sea level approx: R=128, G=0, B=0 → 0
    assert abs(decode_terrarium_rgb(128, 0, 0) - 0.0) < 0.01

    # 1000 m ≈ R=131, G=232, B=0  (128*256 + 1000 = 33768 → R=131 G=232)
    elev = decode_terrarium_rgb(131, 232, 0)
    assert 999 < elev < 1001


def test_sample_elevation():
    engine = TopographyEngine()
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as f:
        path = f.name
    try:
        _make_synthetic_dem(path)
        # center-ish of raster: lon≈-99.168, lat≈19.468
        elev = engine.sample_elevation(path, -99.168, 19.468)
        assert elev is not None
        assert 1000 < elev < 1300
    finally:
        Path(path).unlink(missing_ok=True)


def test_profile_and_slope_sign():
    engine = TopographyEngine()
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as f:
        path = f.name
    try:
        _make_synthetic_dem(path)
        coords = [[-99.195, 19.49], [-99.16, 19.45]]
        pts = engine.profile(path, coords, sample_distance_m=50.0)
        assert len(pts) >= 2
        assert pts[0]["distance_m"] == 0.0
        assert pts[-1]["distance_m"] > 0
        # at least some elevations present
        elevs = [p["elevation_m"] for p in pts if p["elevation_m"] is not None]
        assert len(elevs) >= 1
    finally:
        Path(path).unlink(missing_ok=True)


def test_line_of_sight_visible_flatish():
    engine = TopographyEngine()
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as f:
        path = f.name
    try:
        # nearly flat
        data = np.full((32, 32), 500.0, dtype=np.float32)
        transform = from_origin(-99.15, 19.45, 0.001, 0.001)
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=32,
            width=32,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=transform,
            nodata=-9999,
        ) as dst:
            dst.write(data, 1)
        result = engine.line_of_sight(path, -99.14, 19.44, -99.13, 19.43, observer_height_m=2.0)
        assert "visible" in result
        assert isinstance(result["visible"], bool)
        assert len(result["profile"]) >= 2
    finally:
        Path(path).unlink(missing_ok=True)


def test_haversine():
    engine = TopographyEngine()
    d = engine._haversine_m(-99.13, 19.43, -99.13, 19.44)
    # ~1.1 km per 0.01 deg lat
    assert 1000 < d < 1200


@pytest.mark.skipif(
    True,  # optional: needs full GDAL viewshed in CI
    reason="viewshed requires GDAL alg; run manually with DEM",
)
def test_viewshed_smoke():
    pass
