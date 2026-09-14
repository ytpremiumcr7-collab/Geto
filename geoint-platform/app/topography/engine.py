"""Raster processing engine — GDAL + RasterIO + NumPy.

Operations: elevation (point), profile, slope, aspect, hillshade, LOS, viewshed.
Works on local file paths or paths resolved from MinIO (downloaded to temp).
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

try:
    import structlog

    log = structlog.get_logger()
except ImportError:
    import logging

    log = logging.getLogger(__name__)


def _require_rasterio():
    try:
        import rasterio
        from rasterio.transform import rowcol, xy
        from rasterio.warp import transform as rio_transform

        return rasterio, rowcol, xy, rio_transform
    except ImportError as e:
        raise RuntimeError(
            "rasterio is required for topography processing. Install with: pip install rasterio"
        ) from e


def _require_gdal():
    try:
        from osgeo import gdal

        gdal.UseExceptions()
        return gdal
    except ImportError as e:
        raise RuntimeError(
            "GDAL Python bindings required (libgdal-dev + gdal). "
            "They ship with the project Dockerfile."
        ) from e


class TopographyEngine:
    """Pure processing — no I/O beyond reading raster paths."""

    # Product metadata for API consumers (precision / limits)
    ALGORITHM_LOS = "profile-linear-occlusion-v1"
    ALGORITHM_VIEWSHED = "gdal-ViewshedGenerate-Wang-GVM_Edge"
    LOS_ASSUMPTIONS = (
        "Flat ray between observer and target heights above DEM; "
        "no atmospheric refraction; no vegetation/building clutter; "
        "sample spacing may miss narrow peaks."
    )
    VIEWSHED_ASSUMPTIONS = (
        "GDAL Wang viewshed; curvature_coeff models refraction approx; "
        "geographic CRS uses crude m→degree conversion; DEM surface only."
    )

    def sample_elevation(self, raster_path: str, lon: float, lat: float) -> float | None:
        rasterio, rowcol, xy, rio_transform = _require_rasterio()
        with rasterio.open(raster_path) as ds:
            # reproject point to raster CRS if needed
            src_crs = "EPSG:4326"
            if ds.crs and str(ds.crs) not in ("EPSG:4326", "OGC:CRS84"):
                xs, ys = rio_transform(src_crs, ds.crs, [lon], [lat])
                x, y = xs[0], ys[0]
            else:
                x, y = lon, lat
            row, col = rowcol(ds.transform, x, y)
            if row < 0 or col < 0 or row >= ds.height or col >= ds.width:
                return None
            data = ds.read(1, window=((row, row + 1), (col, col + 1)))
            val = float(data[0, 0])
            nodata = ds.nodata
            if nodata is not None and (val == nodata or np.isnan(val)):
                return None
            return val

    def clip_bbox(
        self,
        raster_path: str,
        out_path: str,
        bbox: list[float],
    ) -> str:
        """Clip raster to [west, south, east, north] (EPSG:4326 preferred).

        Prefer rasterio window clip when CRS is geographic; fall back to GDAL Warp.
        """
        rasterio, rowcol, xy, rio_transform = _require_rasterio()
        west, south, east, north = bbox
        if west >= east or south >= north:
            raise ValueError("Invalid bbox: west<east and south<north required")

        with rasterio.open(raster_path) as ds:
            crs = str(ds.crs) if ds.crs else "EPSG:4326"
            same_geo = crs in ("EPSG:4326", "OGC:CRS84", "") or "4326" in crs
            if same_geo:
                from rasterio.windows import from_bounds
                from rasterio.windows import transform as window_transform

                window = from_bounds(west, south, east, north, ds.transform)
                window = window.round_offsets().round_lengths()
                data = ds.read(window=window)
                transform = window_transform(window, ds.transform)
                profile = ds.profile.copy()
                profile.update(
                    {
                        "height": data.shape[1],
                        "width": data.shape[2],
                        "transform": transform,
                    }
                )
                with rasterio.open(out_path, "w", **profile) as dst:
                    dst.write(data)
                return out_path

        # Non-geographic CRS → GDAL Warp
        gdal = _require_gdal()
        src_crs = crs
        opts = gdal.WarpOptions(
            format="GTiff",
            outputBounds=(west, south, east, north),
            outputBoundsSRS="EPSG:4326",
            dstSRS=src_crs if src_crs not in ("", "None") else "EPSG:4326",
            creationOptions=["COMPRESS=DEFLATE", "TILED=YES"],
        )
        result = gdal.Warp(out_path, raster_path, options=opts)
        if result is None:
            raise RuntimeError(f"GDAL Warp clip failed for bbox={bbox}")
        result.FlushCache()
        result = None
        return out_path

    def profile(
        self,
        raster_path: str,
        coordinates: list[list[float]],
        sample_distance_m: float = 10.0,
    ) -> list[dict[str, Any]]:
        """coordinates: [[lon, lat], ...]. Returns list of dicts with distance/elev/slope."""
        rasterio, rowcol, xy, rio_transform = _require_rasterio()
        # densify polyline in geographic approx (haversine)
        densified = self._densify_line(coordinates, sample_distance_m)
        points: list[dict[str, Any]] = []
        prev_elev: float | None = None
        prev_dist = 0.0
        for i, (lon, lat, dist) in enumerate(densified):
            elev = self.sample_elevation(raster_path, lon, lat)
            slope = None
            if elev is not None and prev_elev is not None and dist > prev_dist:
                dd = dist - prev_dist
                if dd > 0:
                    slope = math.degrees(math.atan2(elev - prev_elev, dd))
            points.append(
                {
                    "distance_m": dist,
                    "lon": lon,
                    "lat": lat,
                    "elevation_m": elev,
                    "slope_deg": slope,
                }
            )
            if elev is not None:
                prev_elev = elev
            prev_dist = dist
        return points

    def slope_raster(
        self, raster_path: str, out_path: str, scale: float = 111120.0
    ) -> dict[str, Any]:
        """gdaldem slope → degrees. scale≈111120 for geographic CRS (m per degree)."""
        gdal = _require_gdal()
        # Use gdal.DEMProcessing
        gdal.DEMProcessing(
            out_path,
            raster_path,
            "slope",
            computeEdges=True,
            slopeFormat="degree",
            scale=scale,
        )
        return self._raster_stats(out_path)

    def aspect_raster(self, raster_path: str, out_path: str) -> dict[str, Any]:
        gdal = _require_gdal()
        gdal.DEMProcessing(out_path, raster_path, "aspect", computeEdges=True)
        return self._raster_stats(out_path)

    def hillshade_raster(
        self,
        raster_path: str,
        out_path: str,
        azimuth: float = 315.0,
        altitude: float = 45.0,
        z_factor: float = 1.0,
    ) -> dict[str, Any]:
        gdal = _require_gdal()
        gdal.DEMProcessing(
            out_path,
            raster_path,
            "hillshade",
            azimuth=azimuth,
            altitude=altitude,
            zFactor=z_factor,
            computeEdges=True,
        )
        return self._raster_stats(out_path)

    def line_of_sight(
        self,
        raster_path: str,
        observer_lon: float,
        observer_lat: float,
        target_lon: float,
        target_lat: float,
        observer_height_m: float = 1.7,
        target_height_m: float = 0.0,
        sample_distance_m: float = 5.0,
    ) -> dict[str, Any]:
        """Simple geometric LOS along densified profile (no refraction in MVP core).

        Returns visible flag + first obstruction distance if any.
        """
        coords = [[observer_lon, observer_lat], [target_lon, target_lat]]
        pts = self.profile(raster_path, coords, sample_distance_m)
        if not pts:
            return {
                "visible": False,
                "obstruction_distance_m": None,
                "obstruction_lon": None,
                "obstruction_lat": None,
                "profile": pts,
                "note": "empty profile",
            }

        obs_elev = pts[0].get("elevation_m")
        tgt_elev = pts[-1].get("elevation_m")
        if obs_elev is None or tgt_elev is None:
            return {
                "visible": False,
                "obstruction_distance_m": None,
                "obstruction_lon": None,
                "obstruction_lat": None,
                "profile": pts,
                "note": "missing elevation at endpoints",
            }

        h0 = obs_elev + observer_height_m
        h1 = tgt_elev + target_height_m
        total = pts[-1]["distance_m"] or 1.0

        for p in pts[1:-1]:
            d = p["distance_m"]
            e = p.get("elevation_m")
            if e is None:
                continue
            # linear LOS height at distance d
            los_h = h0 + (h1 - h0) * (d / total)
            if e > los_h:
                return {
                    "visible": False,
                    "obstruction_distance_m": d,
                    "obstruction_lon": p["lon"],
                    "obstruction_lat": p["lat"],
                    "profile": pts,
                    "note": None,
                    "algorithm": self.ALGORITHM_LOS,
                    "assumptions": self.LOS_ASSUMPTIONS,
                    "sample_distance_m": sample_distance_m,
                    "observer_height_m": observer_height_m,
                    "target_height_m": target_height_m,
                }

        return {
            "visible": True,
            "obstruction_distance_m": None,
            "obstruction_lon": None,
            "obstruction_lat": None,
            "profile": pts,
            "note": None,
            "algorithm": self.ALGORITHM_LOS,
            "assumptions": self.LOS_ASSUMPTIONS,
            "sample_distance_m": sample_distance_m,
            "observer_height_m": observer_height_m,
            "target_height_m": target_height_m,
        }

    def viewshed(
        self,
        raster_path: str,
        out_path: str,
        observer_lon: float,
        observer_lat: float,
        observer_height_m: float = 1.7,
        target_height_m: float = 0.0,
        max_distance_m: float = 5000.0,
        curvature_coeff: float = 0.85714,
    ) -> dict[str, Any]:
        """Uses GDAL ViewshedGenerate (Wang algorithm)."""
        gdal = _require_gdal()
        rasterio, rowcol, xy, rio_transform = _require_rasterio()

        with rasterio.open(raster_path) as ds:
            src_crs = "EPSG:4326"
            if ds.crs and str(ds.crs) not in ("EPSG:4326", "OGC:CRS84"):
                xs, ys = rio_transform(src_crs, ds.crs, [observer_lon], [observer_lat])
                ox, oy = xs[0], ys[0]
            else:
                ox, oy = observer_lon, observer_lat

        src_ds = gdal.Open(raster_path)
        if src_ds is None:
            raise RuntimeError(f"Cannot open DEM: {raster_path}")
        band = src_ds.GetRasterBand(1)

        # maxDistance in CRS units; for geographic approx degrees
        # If geographic, convert meters → degrees (~111120 m/deg)
        max_dist = max_distance_m
        gt = src_ds.GetGeoTransform()
        # crude: if pixel size < 0.01 assume degrees
        if abs(gt[1]) < 0.01:
            max_dist = max_distance_m / 111120.0

        result = gdal.ViewshedGenerate(
            band,
            "GTiff",
            out_path,
            ["COMPRESS=DEFLATE", "TILED=YES"],
            ox,
            oy,
            observer_height_m,
            target_height_m,
            255,  # visible
            0,  # invisible
            0,  # out of range
            -1.0,  # nodata
            curvature_coeff,
            gdal.GVM_Edge,
            max_dist,
        )
        if result is None:
            raise RuntimeError("ViewshedGenerate failed")
        result.FlushCache()
        result = None
        src_ds = None
        return {
            "output": out_path,
            "max_distance_m": max_distance_m,
            "algorithm": self.ALGORITHM_VIEWSHED,
            "assumptions": self.VIEWSHED_ASSUMPTIONS,
            "curvature_coeff": curvature_coeff,
            "observer_height_m": observer_height_m,
            "target_height_m": target_height_m,
        }

    # ── helpers ──────────────────────────────────────────────

    def slope_preview_png(
        self,
        raster_path: str,
        out_png: str,
        bbox: list[float] | None = None,
        max_size: int = 512,
    ) -> dict:
        """Compute slope (degrees) and write a simple colorized PNG for map overlay.

        Does not require GDAL — uses numpy gradient. Returns bounds + path.
        """
        rasterio, rowcol, xy, rio_transform = _require_rasterio()
        from PIL import Image

        with rasterio.open(raster_path) as ds:
            if bbox and len(bbox) == 4:
                west, south, east, north = bbox
                from rasterio.windows import from_bounds
                from rasterio.windows import transform as window_transform

                window = from_bounds(west, south, east, north, ds.transform)
                window = window.round_offsets().round_lengths()
                elev = ds.read(1, window=window).astype("float64")
                transform = window_transform(window, ds.transform)
            else:
                elev = ds.read(1).astype("float64")
                transform = ds.transform
                west, south, east, north = (
                    ds.bounds.left,
                    ds.bounds.bottom,
                    ds.bounds.right,
                    ds.bounds.top,
                )
            nodata = ds.nodata

        if nodata is not None:
            elev = np.where(elev == nodata, np.nan, elev)

        # pixel size in meters (approx for geographic)
        px_x = abs(transform.a) * 111320.0  # lon
        px_y = abs(transform.e) * 110540.0  # lat
        gy, gx = np.gradient(elev, px_y, px_x)
        slope = np.degrees(np.arctan(np.sqrt(gx * gx + gy * gy)))
        slope = np.nan_to_num(slope, nan=0.0)
        # downsample if huge
        h, w = slope.shape
        scale = max(h / max_size, w / max_size, 1.0)
        if scale > 1:
            new_h, new_w = int(h / scale), int(w / scale)
            yi = (np.linspace(0, h - 1, new_h)).astype(int)
            xi = (np.linspace(0, w - 1, new_w)).astype(int)
            slope = slope[yi][:, xi]

        # colorize 0-45 deg → viridis-ish RGB
        norm = np.clip(slope / 45.0, 0, 1)
        r = (norm * 255).astype(np.uint8)
        g = ((1 - np.abs(norm - 0.5) * 2) * 200).astype(np.uint8)
        b = ((1 - norm) * 255).astype(np.uint8)
        alpha = np.where(slope > 0.1, 180, 0).astype(np.uint8)
        rgba = np.dstack([r, g, b, alpha])
        Image.fromarray(rgba, "RGBA").save(out_png)
        return {
            "path": out_png,
            "bounds": [west, south, east, north],  # [w,s,e,n]
            "slope_min": float(np.nanmin(slope)),
            "slope_max": float(np.nanmax(slope)),
            "slope_mean": float(np.nanmean(slope)),
        }

    @staticmethod
    def _haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
        r = 6371000.0
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dl = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return 2 * r * math.asin(math.sqrt(a))

    def _densify_line(
        self, coordinates: list[list[float]], step_m: float
    ) -> list[tuple[float, float, float]]:
        out: list[tuple[float, float, float]] = []
        dist_acc = 0.0
        for i in range(len(coordinates) - 1):
            lon1, lat1 = coordinates[i][0], coordinates[i][1]
            lon2, lat2 = coordinates[i + 1][0], coordinates[i + 1][1]
            seg = self._haversine_m(lon1, lat1, lon2, lat2)
            if seg < 1e-6:
                continue
            n = max(1, int(math.ceil(seg / step_m)))
            for k in range(n):
                t = k / n
                lon = lon1 + (lon2 - lon1) * t
                lat = lat1 + (lat2 - lat1) * t
                d = dist_acc + seg * t
                out.append((lon, lat, d))
            dist_acc += seg
        # last point
        lon, lat = coordinates[-1][0], coordinates[-1][1]
        out.append((lon, lat, dist_acc))
        return out

    def _raster_stats(self, path: str) -> dict[str, Any]:
        rasterio, *_ = _require_rasterio()
        with rasterio.open(path) as ds:
            arr = ds.read(1, masked=True)
            return {
                "min": float(arr.min()) if arr.count() else None,
                "max": float(arr.max()) if arr.count() else None,
                "mean": float(arr.mean()) if arr.count() else None,
                "width": ds.width,
                "height": ds.height,
                "crs": str(ds.crs) if ds.crs else None,
            }
