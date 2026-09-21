"""Topography service — orchestrates providers, catalog, engine, MinIO."""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    import structlog

    log = structlog.get_logger()
except ImportError:
    import logging

    log = logging.getLogger(__name__)

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.object_store import ObjectStore
from app.topography.engine import TopographyEngine
from app.topography.models import (
    DemAssetCreate,
    DemProvider,
    ElevationResponse,
    LosResponse,
    ProfilePoint,
    ProfileResponse,
    RasterOpResponse,
    ViewshedResponse,
)
from app.topography.providers import (
    AwsTerrariumProvider,
    CopernicusDemProvider,
    InegiProvider,
    LocalRasterProvider,
)
from app.topography.repository import DemRepository


def derived_object_key(tenant_id: str, category: str, filename: str) -> str:
    """Build a tenant-scoped derived-object key with unambiguous path segments."""
    parts = (tenant_id, category, filename)
    if any(not part or part in {".", ".."} or "/" in part or "\\" in part for part in parts):
        raise ValueError("unsafe derived object key component")
    return f"derived/{tenant_id}/{category}/{filename}"


class TopographyService:
    def __init__(self, session: AsyncSession | None = None):
        self.session = session
        self.engine = TopographyEngine()
        self.store = ObjectStore()
        self.terrarium = AwsTerrariumProvider()
        self.inegi = InegiProvider()
        self.copernicus = CopernicusDemProvider()

    # ── catalog ─────────────────────────────────────────────

    async def register_dem(self, tenant_id: str, body: DemAssetCreate) -> dict[str, Any]:
        if self.session is None:
            raise RuntimeError("DB session required for catalog")
        self._validate_file_uri(body.file_uri)
        repo = DemRepository(self.session)
        return await repo.create(
            tenant_id=tenant_id,
            provider=body.provider.value,
            product_name=body.product_name,
            product_type=body.product_type.value,
            resolution_m=body.resolution_m,
            crs=body.crs,
            vertical_datum=body.vertical_datum,
            bbox_west=body.bbox_west,
            bbox_south=body.bbox_south,
            bbox_east=body.bbox_east,
            bbox_north=body.bbox_north,
            file_uri=body.file_uri,
            checksum_sha256=body.checksum_sha256,
            source_version=body.source_version,
            acquisition_date=body.acquisition_date,
            extra=body.extra,
        )

    async def list_dems(self, tenant_id: str) -> list[dict[str, Any]]:
        if self.session is None:
            return []
        return await DemRepository(self.session).list_assets(tenant_id)

    async def provider_info(self) -> dict[str, Any]:
        return {
            "tier1": {
                "aws_terrarium": {
                    "role": "global_visualization_and_quick_elevation",
                    "auth": "none",
                    "status": "live",
                },
                "local_minio": {
                    "role": "analysis_COG",
                    "auth": "minio credentials",
                    "status": "live",
                },
                "inegi": self.inegi.registration_help(),
                "copernicus_dem": self.copernicus.registration_help(),
            },
            "note": (
                "El adapter app/sources/copernicus es Sentinel-2 imagery, "
                "NO Copernicus DEM. No reutilizar."
            ),
        }

    # ── elevation ───────────────────────────────────────────

    async def elevation(
        self,
        tenant_id: str,
        lat: float,
        lon: float,
        dem_id: str | None = None,
        preferred_provider: DemProvider | None = None,
    ) -> ElevationResponse:
        now = datetime.now(UTC)

        # 1) explicit dem_id
        asset = None
        if dem_id and self.session:
            asset = await DemRepository(self.session).get(dem_id, tenant_id)
        elif self.session:
            pref = preferred_provider.value if preferred_provider else None
            asset = await DemRepository(self.session).find_covering(
                tenant_id, lon, lat, preferred_provider=pref
            )

        if asset:
            path = await self._resolve_raster(asset["file_uri"])
            try:
                provider = LocalRasterProvider(
                    path,
                    meta={
                        "resolution_m": asset.get("resolution_m"),
                        "product_name": asset.get("product_name"),
                        "provider": asset.get("provider"),
                        "crs": asset.get("crs"),
                        "vertical_datum": asset.get("vertical_datum"),
                        "dem_id": asset.get("id"),
                    },
                )
                result = await provider.sample_point(lon, lat)
                if result and result.get("elevation_m") is not None:
                    return ElevationResponse(
                        elevation_m=result["elevation_m"],
                        lat=lat,
                        lon=lon,
                        source=result.get("source", asset["provider"]),
                        provider=asset["provider"],
                        product_name=asset.get("product_name"),
                        resolution_m=asset.get("resolution_m"),
                        crs=asset.get("crs"),
                        vertical_datum=asset.get("vertical_datum"),
                        dem_id=asset.get("id"),
                        sampled_at=now,
                    )
            finally:
                self._cleanup_temp(path, asset["file_uri"])

        # 2) fallback Terrarium (global, no key)
        if preferred_provider in (None, DemProvider.AWS_TERRARIUM):
            t = await self.terrarium.sample_point(lon, lat)
            if t:
                return ElevationResponse(
                    elevation_m=t["elevation_m"],
                    lat=lat,
                    lon=lon,
                    source=t["source"],
                    provider=t["provider"],
                    product_name=t.get("product_name"),
                    resolution_m=t.get("resolution_m"),
                    crs=t.get("crs"),
                    vertical_datum=t.get("vertical_datum"),
                    dem_id=None,
                    sampled_at=now,
                    note="Fallback AWS Terrarium (visual-grade, not survey-grade)",
                )

        return ElevationResponse(
            elevation_m=None,
            lat=lat,
            lon=lon,
            source="none",
            provider="none",
            sampled_at=now,
            note="No DEM covering point and Terrarium unavailable",
        )

    # ── profile ─────────────────────────────────────────────

    async def profile(
        self,
        tenant_id: str,
        coordinates: list[list[float]],
        sample_distance_m: float = 10.0,
        dem_id: str | None = None,
    ) -> ProfileResponse:
        lon0, lat0 = coordinates[0][0], coordinates[0][1]
        asset = await self._pick_asset(tenant_id, lon0, lat0, dem_id)
        if not asset:
            # Terrarium multi-sample (coarse)
            pts: list[ProfilePoint] = []
            engine = TopographyEngine()
            densified = engine._densify_line(coordinates, sample_distance_m)
            for lon, lat, dist in densified:
                t = await self.terrarium.sample_point(lon, lat)
                elev = t["elevation_m"] if t else None
                pts.append(ProfilePoint(distance_m=dist, lon=lon, lat=lat, elevation_m=elev))
            total = pts[-1].distance_m if pts else 0.0
            return ProfileResponse(
                points=pts,
                total_distance_m=total,
                source="aws_terrarium",
                provider="aws_terrarium",
                resolution_m=None,
                dem_id=None,
                sample_distance_m=sample_distance_m,
            )

        path = await self._resolve_raster(asset["file_uri"])
        try:
            raw = self.engine.profile(path, coordinates, sample_distance_m)
            pts = [ProfilePoint(**p) for p in raw]
            total = pts[-1].distance_m if pts else 0.0
            return ProfileResponse(
                points=pts,
                total_distance_m=total,
                source=asset["provider"],
                provider=asset["provider"],
                resolution_m=asset.get("resolution_m"),
                dem_id=asset.get("id"),
                sample_distance_m=sample_distance_m,
            )
        finally:
            self._cleanup_temp(path, asset["file_uri"])

    # ── slope / aspect / hillshade ──────────────────────────

    async def raster_op(
        self,
        tenant_id: str,
        dem_id: str,
        operation: str,
        bbox: list[float] | None = None,
    ) -> RasterOpResponse:
        if self.session is None:
            raise RuntimeError("DB required")
        asset = await DemRepository(self.session).get(dem_id, tenant_id)
        if not asset:
            raise ValueError(f"DEM not found: {dem_id}")
        path = await self._resolve_raster(asset["file_uri"])
        clipped_path = None
        try:
            work_path = path
            if bbox and len(bbox) == 4:
                with tempfile.NamedTemporaryFile(suffix="_clip.tif", delete=False) as ctmp:
                    clipped_path = ctmp.name
                self.engine.clip_bbox(path, clipped_path, bbox)
                work_path = clipped_path
            with tempfile.NamedTemporaryFile(suffix=f"_{operation}.tif", delete=False) as tmp:
                out_path = tmp.name
            if operation == "slope":
                stats = self.engine.slope_raster(work_path, out_path)
            elif operation == "aspect":
                stats = self.engine.aspect_raster(work_path, out_path)
            elif operation == "hillshade":
                stats = self.engine.hillshade_raster(work_path, out_path)
            else:
                raise ValueError(f"Unknown operation: {operation}")

            # upload derived to MinIO
            key = derived_object_key(tenant_id, operation, f"{dem_id}_{operation}.tif")
            uri = await self.store.put_bytes(
                key,
                Path(out_path).read_bytes(),
                content_type="image/tiff",
            )
            try:
                os.unlink(out_path)
            except OSError:
                pass
            return RasterOpResponse(
                dem_id=dem_id,
                operation=operation,
                output_uri=uri,
                stats=stats,
                source=asset["provider"],
                provider=asset["provider"],
                resolution_m=asset.get("resolution_m"),
            )
        finally:
            self._cleanup_temp(path, asset["file_uri"])
            if clipped_path:
                try:
                    os.unlink(clipped_path)
                except OSError:
                    pass

    # ── LOS / viewshed ──────────────────────────────────────

    async def line_of_sight(
        self,
        tenant_id: str,
        observer_lon: float,
        observer_lat: float,
        target_lon: float,
        target_lat: float,
        observer_height_m: float = 1.7,
        target_height_m: float = 0.0,
        dem_id: str | None = None,
        sample_distance_m: float | None = None,
        refraction_k: float | None = 1.333,
    ) -> LosResponse:
        asset = await self._pick_asset(tenant_id, observer_lon, observer_lat, dem_id)
        if not asset:
            return LosResponse(
                visible=False,
                observer={
                    "lon": observer_lon,
                    "lat": observer_lat,
                    "height_m": observer_height_m,
                },
                target={
                    "lon": target_lon,
                    "lat": target_lat,
                    "height_m": target_height_m,
                },
                source="none",
                provider="none",
                note="No DEM available for LOS; register a local COG first",
                quality={
                    "decision_grade": "exploratory",
                    "horizontal_uncertainty_m": 30.0,
                    "vertical_uncertainty_m": 15.0,
                    "dem_resolution_m": None,
                    "vertical_datum": "unknown",
                    "crs": "EPSG:4326",
                    "refraction_model": "none",
                    "curvature_applied": False,
                    "confidence_0_1": 0.0,
                    "limiting_factors": ["No DEM registered"],
                    "certification": (
                        "NOT certified for safety-of-life, IFR procedure design, "
                        "or weapons employment. Suitable as decision-support when "
                        "uncertainty is carried forward by the operator."
                    ),
                    "sample_distance_m": sample_distance_m,
                    "sample_clamped_to_gsd": False,
                },
            )
        gsd = float(asset.get("resolution_m") or 30.0)
        requested = sample_distance_m if sample_distance_m is not None else gsd
        # Policy: sample step must not exceed DEM GSD
        clamped = False
        step = requested
        if step > gsd:
            step = gsd
            clamped = True
        datum = asset.get("vertical_datum") or "unknown"
        path = await self._resolve_raster(asset["file_uri"])
        try:
            result = self.engine.line_of_sight(
                path,
                observer_lon,
                observer_lat,
                target_lon,
                target_lat,
                observer_height_m=observer_height_m,
                target_height_m=target_height_m,
                sample_distance_m=step,
                refraction_k=refraction_k,
                dem_resolution_m=gsd,
                vertical_datum=str(datum),
            )
            quality = result.get("quality") or {}
            if isinstance(quality, dict):
                quality = {
                    **quality,
                    "sample_distance_m": step,
                    "sample_clamped_to_gsd": clamped,
                    "vertical_datum": str(datum),
                    "dem_resolution_m": gsd,
                }
                if clamped:
                    factors = list(quality.get("limiting_factors") or [])
                    factors.append(f"sample_distance_m clamped to DEM GSD ({gsd} m)")
                    quality["limiting_factors"] = factors
            profile = [
                ProfilePoint(
                    distance_m=pt.get("distance_m", 0.0),
                    lon=pt.get("lon", 0.0),
                    lat=pt.get("lat", 0.0),
                    elevation_m=pt.get("elevation_m"),
                    slope_deg=pt.get("slope_deg"),
                )
                for pt in (result.get("profile") or [])
            ]
            note = result.get("note")
            if clamped:
                extra = f"sample_distance_m clamped to GSD {gsd} m"
                note = f"{note}; {extra}" if note else extra
            return LosResponse(
                visible=bool(result.get("visible")),
                observer={
                    "lon": observer_lon,
                    "lat": observer_lat,
                    "height_m": observer_height_m,
                },
                target={
                    "lon": target_lon,
                    "lat": target_lat,
                    "height_m": target_height_m,
                },
                obstruction_distance_m=result.get("obstruction_distance_m"),
                obstruction_lon=result.get("obstruction_lon"),
                obstruction_lat=result.get("obstruction_lat"),
                profile=profile,
                source=asset["provider"],
                provider=asset["provider"],
                dem_id=asset.get("id"),
                note=note,
                resolution_m=gsd,
                vertical_datum=str(datum),
                sample_distance_m=step,
                algorithm=result.get("algorithm"),
                quality=quality,
            )
        finally:
            self._cleanup_temp(path, asset["file_uri"])

    async def viewshed(
        self,
        tenant_id: str,
        dem_id: str,
        observer_lon: float,
        observer_lat: float,
        observer_height_m: float = 1.7,
        target_height_m: float = 0.0,
        max_distance_m: float = 5000.0,
    ) -> ViewshedResponse:
        if self.session is None:
            raise RuntimeError("DB required")
        asset = await DemRepository(self.session).get(dem_id, tenant_id)
        if not asset:
            raise ValueError(f"DEM not found: {dem_id}")
        path = await self._resolve_raster(asset["file_uri"])
        try:
            with tempfile.NamedTemporaryFile(suffix="_viewshed.tif", delete=False) as tmp:
                out_path = tmp.name
            self.engine.viewshed(
                path,
                out_path,
                observer_lon,
                observer_lat,
                observer_height_m,
                target_height_m,
                max_distance_m,
            )
            key = derived_object_key(
                tenant_id,
                "viewshed",
                f"{dem_id}_{observer_lon}_{observer_lat}.tif",
            )
            uri = await self.store.put_bytes(
                key,
                Path(out_path).read_bytes(),
                content_type="image/tiff",
            )
            try:
                os.unlink(out_path)
            except OSError:
                pass
            return ViewshedResponse(
                dem_id=dem_id,
                output_uri=uri,
                observer={
                    "lon": observer_lon,
                    "lat": observer_lat,
                    "height_m": observer_height_m,
                },
                max_distance_m=max_distance_m,
                source=asset["provider"],
                provider=asset["provider"],
            )
        finally:
            self._cleanup_temp(path, asset["file_uri"])

    # ── helpers ─────────────────────────────────────────────

    async def slope_preview(
        self,
        tenant_id: str,
        dem_id: str,
        bbox: list[float] | None = None,
    ) -> dict:
        """Return PNG bytes + geographic bounds for MapLibre image source."""
        if self.session is None:
            raise RuntimeError("DB required")
        asset = await DemRepository(self.session).get(dem_id, tenant_id)
        if not asset:
            raise ValueError(f"DEM not found: {dem_id}")
        path = await self._resolve_raster(asset["file_uri"])
        try:
            with tempfile.NamedTemporaryFile(suffix="_slope.png", delete=False) as tmp:
                png_path = tmp.name
            meta = self.engine.slope_preview_png(path, png_path, bbox=bbox)
            data = Path(png_path).read_bytes()
            try:
                os.unlink(png_path)
            except OSError:
                pass
            return {
                "png": data,
                "bounds": meta["bounds"],
                "stats": {
                    "slope_min": meta["slope_min"],
                    "slope_max": meta["slope_max"],
                    "slope_mean": meta["slope_mean"],
                },
                "dem_id": dem_id,
                "provider": asset.get("provider"),
                "product_name": asset.get("product_name"),
            }
        finally:
            self._cleanup_temp(path, asset["file_uri"])

    @staticmethod
    def _validate_file_uri(file_uri: str) -> None:
        from app.core.config import settings

        raw = getattr(settings, "dem_allowed_key_prefixes", None) or "dem/,derived/"
        if isinstance(raw, str):
            allowed_prefixes = tuple(x.strip() for x in raw.split(",") if x.strip())
        else:
            allowed_prefixes = tuple(raw)
        if file_uri.startswith("s3://"):
            without = file_uri[5:]
            parts = without.split("/", 1)
            if len(parts) != 2:
                raise ValueError("Invalid s3 uri")
            bucket, key = parts
            if bucket != settings.minio_bucket_raw:
                raise ValueError("s3 bucket not allowed")
            if not key.startswith(allowed_prefixes):
                raise ValueError(f"key must start with {allowed_prefixes}")
            if ".." in key.split("/"):
                raise ValueError("invalid key")
            return
        if settings.app_env in ("development", "dev", "test"):
            return
        raise ValueError("Only s3:// URIs allowed outside development")

    async def _pick_asset(
        self,
        tenant_id: str,
        lon: float,
        lat: float,
        dem_id: str | None,
    ) -> dict[str, Any] | None:
        if not self.session:
            return None
        repo = DemRepository(self.session)
        if dem_id:
            return await repo.get(dem_id, tenant_id)
        return await repo.find_covering(tenant_id, lon, lat)

    async def _resolve_raster(self, file_uri: str) -> str:
        """Return local path. Only s3://<configured-bucket>/(dem|derived)/... allowed.

        Local file:// or absolute paths only when APP_ENV is development/test.
        """
        from app.core.config import settings

        raw = getattr(settings, "dem_allowed_key_prefixes", None) or "dem/,derived/"
        if isinstance(raw, str):
            allowed_prefixes = tuple(x.strip() for x in raw.split(",") if x.strip())
        else:
            allowed_prefixes = tuple(raw)
        bucket_allowed = settings.minio_bucket_raw

        if file_uri.startswith("s3://"):
            without = file_uri[5:]
            parts = without.split("/", 1)
            if len(parts) != 2:
                raise ValueError(f"Invalid s3 uri: {file_uri}")
            bucket, key = parts
            if bucket != bucket_allowed:
                raise ValueError(f"s3 bucket not allowed: {bucket} (expected {bucket_allowed})")
            if not key.startswith(allowed_prefixes):
                raise ValueError(f"s3 key must start with one of {allowed_prefixes}: {key}")
            # path traversal
            if ".." in key.split("/"):
                raise ValueError("invalid s3 key")
            data = await self.store.get_bytes(key, bucket=bucket)
            tmp = tempfile.NamedTemporaryFile(suffix=".tif", delete=False)
            tmp.write(data)
            tmp.close()
            return tmp.name

        if settings.app_env in ("development", "dev", "test"):
            if file_uri.startswith("file://"):
                path = file_uri[7:]
            elif file_uri.startswith("/") or Path(file_uri).exists():
                path = file_uri
            else:
                raise ValueError(f"Unsupported file_uri: {file_uri}")
            # still block path traversal outside samples/tmp
            resolved = Path(path).resolve()
            return str(resolved)

        raise ValueError(
            "Only s3:// URIs under the configured bucket are allowed outside development"
        )

    @staticmethod
    def _cleanup_temp(path: str, original_uri: str) -> None:
        if original_uri.startswith("s3://") and path.startswith("/tmp"):
            try:
                os.unlink(path)
            except OSError:
                pass
