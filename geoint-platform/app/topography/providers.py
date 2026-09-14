"""DEM providers.

Tier 1 MVP:
  - LocalMinioProvider: COGs already in MinIO (analysis)
  - AwsTerrariumProvider: point elevation from public Terrarium tiles (viz/quick)

Tier 1 interfaces (ingest-first, no anonymous API spam):
  - InegiProvider: documents how to obtain CEM/MDE; registers local files
  - CopernicusDemProvider: optional CDSE S3 credentials → tile fetch into MinIO
"""

from __future__ import annotations

import io
import math
import struct
from abc import ABC, abstractmethod
from typing import Any

import httpx

try:
    import structlog

    log = structlog.get_logger()
except ImportError:
    import logging

    log = logging.getLogger(__name__)

from app.topography.models import DemProvider

# AWS Terrain Tiles (Terrarium encoding) — same source MapLibre uses
TERRARIUM_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"

# Simple process-local tile cache to avoid redundant HTTP on dense profiles
_TILE_CACHE: dict[str, bytes] = {}
_TILE_CACHE_MAX = 256


def _lonlat_to_tile(lon: float, lat: float, z: int) -> tuple[int, int]:
    lat = max(min(lat, 85.05112878), -85.05112878)
    n = 2**z
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
    return x % n, max(0, min(n - 1, y))


def decode_terrarium_rgb(r: int, g: int, b: int) -> float:
    """Terrarium: elevation = (R * 256 + G + B / 256) - 32768"""
    return (r * 256.0 + g + b / 256.0) - 32768.0


class DemProviderBase(ABC):
    provider_id: DemProvider

    @abstractmethod
    async def sample_point(self, lon: float, lat: float) -> dict[str, Any] | None:
        """Return {elevation_m, resolution_m, product_name, ...} or None."""


class AwsTerrariumProvider(DemProviderBase):
    """Public global elevation via Terrarium PNG tiles (no key)."""

    provider_id = DemProvider.AWS_TERRARIUM

    def __init__(self, zoom: int = 15, timeout: float = 15.0):
        self.zoom = zoom
        self.timeout = timeout

    async def sample_point(self, lon: float, lat: float) -> dict[str, Any] | None:
        z = self.zoom
        x, y = _lonlat_to_tile(lon, lat, z)
        url = TERRARIUM_URL.format(z=z, x=x, y=y)
        cache_key = f"{z}/{x}/{y}"
        data = _TILE_CACHE.get(cache_key)
        if data is None:
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    r = await client.get(url)
                    r.raise_for_status()
                    data = r.content
                if len(_TILE_CACHE) >= _TILE_CACHE_MAX:
                    # drop arbitrary oldest-ish key
                    _TILE_CACHE.pop(next(iter(_TILE_CACHE)), None)
                _TILE_CACHE[cache_key] = data
            except Exception as e:
                log.warning("terrarium_fetch_failed", error=str(e), url=url)
                return None

        # decode PNG without heavy deps if possible — use stdlib + zlib for IHDR/IDAT
        elev = self._decode_png_center(data)
        if elev is None:
            return None
        # approx resolution at equator for z
        res_m = 40075016.686 / (256 * (2**z))
        return {
            "elevation_m": elev,
            "resolution_m": round(res_m, 2),
            "product_name": "AWS Terrain Tiles (Terrarium)",
            "provider": self.provider_id.value,
            "source": "aws_terrarium",
            "crs": "EPSG:3857/4326",
            "vertical_datum": "EGM96-ish (Mapzen Terrarium)",
            "tile": f"{z}/{x}/{y}",
        }

    def _decode_png_center(self, png_bytes: bytes) -> float | None:
        """Minimal PNG reader for 256x256 RGB Terrarium tiles."""
        try:
            import numpy as np
            from PIL import Image

            img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
            arr = np.array(img)
            h, w, _ = arr.shape
            r, g, b = arr[h // 2, w // 2]
            return decode_terrarium_rgb(int(r), int(g), int(b))
        except ImportError:
            pass
        # fallback: pure struct scan for simple uncompressed or use zlib
        try:
            import zlib

            # find IDAT
            pos = 8
            idat = b""
            width = height = None
            while pos + 8 <= len(png_bytes):
                length = struct.unpack(">I", png_bytes[pos : pos + 4])[0]
                ctype = png_bytes[pos + 4 : pos + 8]
                chunk = png_bytes[pos + 8 : pos + 8 + length]
                if ctype == b"IHDR":
                    width, height = struct.unpack(">II", chunk[:8])
                elif ctype == b"IDAT":
                    idat += chunk
                elif ctype == b"IEND":
                    break
                pos += 12 + length
            if not idat or not width or not height:
                return None
            raw = zlib.decompress(idat)
            # filter byte per row + RGB
            row_len = 1 + width * 3
            cy, cx = height // 2, width // 2
            row_start = cy * row_len + 1
            i = row_start + cx * 3
            r, g, b = raw[i], raw[i + 1], raw[i + 2]
            return decode_terrarium_rgb(r, g, b)
        except Exception as e:
            log.warning("terrarium_png_decode_failed", error=str(e))
            return None


class LocalRasterProvider(DemProviderBase):
    """Elevation from a local GeoTIFF/COG path (resolved by service from MinIO)."""

    provider_id = DemProvider.LOCAL

    def __init__(self, raster_path: str, meta: dict[str, Any] | None = None):
        self.raster_path = raster_path
        self.meta = meta or {}

    async def sample_point(self, lon: float, lat: float) -> dict[str, Any] | None:
        from app.topography.engine import TopographyEngine

        engine = TopographyEngine()
        elev = engine.sample_elevation(self.raster_path, lon, lat)
        if elev is None:
            return None
        return {
            "elevation_m": elev,
            "resolution_m": self.meta.get("resolution_m"),
            "product_name": self.meta.get("product_name", "local DEM"),
            "provider": self.meta.get("provider", self.provider_id.value),
            "source": self.meta.get("provider", "local"),
            "crs": self.meta.get("crs"),
            "vertical_datum": self.meta.get("vertical_datum"),
            "dem_id": self.meta.get("dem_id"),
        }


class InegiProvider(DemProviderBase):
    """INEGI CEM / MDE — no public bulk REST API.

    MVP: catalog + local file registration only.
    Users download CEM tiles from INEGI portal and drop into MinIO.
    """

    provider_id = DemProvider.INEGI

    async def sample_point(self, lon: float, lat: float) -> dict[str, Any] | None:
        # Mexico approximate bbox
        if not (-118.5 <= lon <= -86.5 and 14.0 <= lat <= 33.0):
            return None
        return None  # must use registered local DEM covering the point

    def registration_help(self) -> dict[str, str]:
        return {
            "portal": "https://www.inegi.org.mx/app/geo2/elevacionesmex/",
            "products": "CEM 15m/30m/…, MDE terreno 1.5m/5m (zonas)",
            "workflow": (
                "1) Descargar GeoTIFF desde portal INEGI "
                "2) mc cp archivo.tif local/geoint-raw/dem/mexico/inegi/ "
                "3) POST /api/v1/topography/dem/register"
            ),
            "note": "No API anónima de elevación por punto; ingest-first.",
        }


class CopernicusDemProvider(DemProviderBase):
    """Copernicus DEM GLO-30 — requires CDSE registration + S3 credentials.

    MVP: interface + optional env credentials; prefer pre-ingested tiles in MinIO.
    """

    provider_id = DemProvider.COPERNICUS_DEM

    def __init__(
        self,
        access_key: str | None = None,
        secret_key: str | None = None,
        endpoint: str = "https://eodata.dataspace.copernicus.eu",
    ):
        self.access_key = access_key
        self.secret_key = secret_key
        self.endpoint = endpoint

    async def sample_point(self, lon: float, lat: float) -> dict[str, Any] | None:
        # No anonymous point API — require local DEM
        return None

    def registration_help(self) -> dict[str, str]:
        return {
            "register": "https://dataspace.copernicus.eu/",
            "docs": "https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM",
            "workflow": (
                "1) Crear cuenta CDSE + generar S3 keys "
                "2) Descargar tiles GLO-30 para AOI "
                "3) Subir COG a MinIO dem/global/copernicus/ "
                "4) POST /api/v1/topography/dem/register"
            ),
            "note": "View service restringido desde 2026-07; ingest-first obligatorio.",
        }
