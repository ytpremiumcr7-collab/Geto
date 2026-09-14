"""DEM catalog and topography response models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class DemProvider(StrEnum):
    LOCAL = "local"
    INEGI = "inegi"
    COPERNICUS_DEM = "copernicus_dem"
    AWS_TERRARIUM = "aws_terrarium"
    USGS = "usgs"
    OPENTOPOGRAPHY = "opentopography"


class DemProductType(StrEnum):
    DTM = "dtm"  # bare earth
    DSM = "dsm"  # surface (buildings + veg)
    DEM = "dem"  # generic


class DemAssetCreate(BaseModel):
    provider: DemProvider
    product_name: str
    product_type: DemProductType = DemProductType.DTM
    resolution_m: float = Field(..., gt=0, le=1000, description="Ground sample distance (m)")
    crs: str = "EPSG:4326"
    vertical_datum: str = Field(
        ...,
        min_length=2,
        max_length=64,
        description="Required vertical datum, e.g. EGM96, NAVD88, ELLIPSOIDAL_WGS84",
    )
    bbox_west: float
    bbox_south: float
    bbox_east: float
    bbox_north: float
    file_uri: str  # s3://bucket/key or file://...
    checksum_sha256: str | None = None
    source_version: str | None = None
    acquisition_date: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class DemAssetOut(DemAssetCreate):
    id: str
    tenant_id: str
    created_at: datetime
    byte_size: int | None = None


class ElevationRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    dem_id: str | None = None  # if None, best available covering point
    preferred_provider: DemProvider | None = None


class ElevationResponse(BaseModel):
    elevation_m: float | None
    lat: float
    lon: float
    source: str
    provider: str
    product_name: str | None = None
    resolution_m: float | None = None
    crs: str | None = None
    vertical_datum: str | None = None
    dem_id: str | None = None
    sampled_at: datetime
    note: str | None = None


class ProfileRequest(BaseModel):
    coordinates: list[list[float]] = Field(
        ...,
        min_length=2,
        description="[[lon,lat], ...] line vertices",
    )
    sample_distance_m: float = Field(10.0, ge=1.0, le=5000.0)
    dem_id: str | None = None


class ProfilePoint(BaseModel):
    distance_m: float
    lon: float
    lat: float
    elevation_m: float | None
    slope_deg: float | None = None


class ProfileResponse(BaseModel):
    points: list[ProfilePoint]
    total_distance_m: float
    source: str
    provider: str
    resolution_m: float | None = None
    dem_id: str | None = None
    sample_distance_m: float


class RasterOpRequest(BaseModel):
    dem_id: str
    # optional AOI clip (lon/lat)
    bbox: list[float] | None = Field(None, description="[west, south, east, north]")


class RasterOpResponse(BaseModel):
    dem_id: str
    operation: str
    output_uri: str | None = None
    stats: dict[str, Any] = Field(default_factory=dict)
    source: str
    provider: str
    resolution_m: float | None = None


class LosRequest(BaseModel):
    observer_lon: float
    observer_lat: float
    target_lon: float
    target_lat: float
    observer_height_m: float = 1.7
    target_height_m: float = 0.0
    dem_id: str | None = None
    sample_distance_m: float | None = Field(
        None,
        ge=0.5,
        le=5000.0,
        description="Profile step; if omitted or > DEM GSD, clamped to resolution_m",
    )
    refraction_k: float | None = Field(
        1.333,
        description="Effective-Earth factor; None disables curvature (exploratory)",
    )
    curvature_coeff: float = Field(0.85714, description="Viewshed GDAL coeff (legacy field)")


class TerrainQualityOut(BaseModel):
    decision_grade: str
    horizontal_uncertainty_m: float
    vertical_uncertainty_m: float
    dem_resolution_m: float | None = None
    vertical_datum: str
    crs: str = "EPSG:4326"
    refraction_model: str
    curvature_applied: bool
    confidence_0_1: float
    limiting_factors: list[str] = Field(default_factory=list)
    certification: str
    sample_distance_m: float | None = None
    sample_clamped_to_gsd: bool = False


class LosResponse(BaseModel):
    visible: bool
    observer: dict[str, float]
    target: dict[str, float]
    obstruction_distance_m: float | None = None
    obstruction_lon: float | None = None
    obstruction_lat: float | None = None
    profile: list[ProfilePoint] = Field(default_factory=list)
    source: str
    provider: str
    dem_id: str | None = None
    note: str | None = None
    resolution_m: float | None = None
    vertical_datum: str | None = None
    sample_distance_m: float | None = None
    algorithm: str | None = None
    quality: TerrainQualityOut | dict[str, Any] | None = None


class ViewshedRequest(BaseModel):
    observer_lon: float
    observer_lat: float
    observer_height_m: float = 1.7
    max_distance_m: float = Field(5000.0, ge=50.0, le=100_000.0)
    dem_id: str
    target_height_m: float = 0.0


class ViewshedResponse(BaseModel):
    dem_id: str
    output_uri: str | None
    observer: dict[str, float]
    max_distance_m: float
    source: str
    provider: str
    note: str | None = None
    resolution_m: float | None = None
    vertical_datum: str | None = None
    quality: TerrainQualityOut | dict[str, Any] | None = None
