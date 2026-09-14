"""Decision-support quality model for DEM / LOS / viewshed.

Engineering controls for operational *support* — not ICAO/FAA/DoD safety-of-life
certification. Callers must treat grade ``not_for_safety_of_life`` as binding.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

DecisionGrade = Literal[
    "exploratory",
    "operational_support",
    "not_for_safety_of_life",
]


@dataclass(frozen=True)
class TerrainQuality:
    """Uncertainty and lineage attached to every terrain product response."""

    decision_grade: DecisionGrade
    horizontal_uncertainty_m: float
    vertical_uncertainty_m: float
    dem_resolution_m: float | None
    vertical_datum: str
    crs: str
    refraction_model: str
    curvature_applied: bool
    confidence_0_1: float
    limiting_factors: tuple[str, ...]
    certification: str = (
        "NOT certified for safety-of-life, IFR procedure design, or weapons employment. "
        "Suitable as decision-support when uncertainty is carried forward by the operator."
    )

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["limiting_factors"] = list(self.limiting_factors)
        return d


def estimate_dem_resolution_m(pixel_size: float, crs_is_geographic: bool) -> float:
    """Approximate ground sample distance from geotransform pixel size."""
    if crs_is_geographic or abs(pixel_size) < 0.01:
        # degrees → meters (equatorial approx; sufficient for GSD classing)
        return abs(pixel_size) * 111_120.0
    return abs(pixel_size)


def build_los_quality(
    *,
    dem_resolution_m: float | None,
    sample_distance_m: float,
    refraction_k: float | None,
    curvature_applied: bool,
    provider: str | None = None,
    vertical_datum: str = "unknown",
    crs: str = "EPSG:4326",
) -> TerrainQuality:
    """Derive horizontal/vertical uncertainty and confidence for LOS."""
    factors: list[str] = [
        "DEM surface only (no vegetation/building clutter)",
        "Sample spacing may miss narrow peaks",
    ]
    res = dem_resolution_m if dem_resolution_m and dem_resolution_m > 0 else 30.0
    # Horizontal: ~1 pixel + half sample step
    horiz = max(res, sample_distance_m * 0.5)
    # Vertical: typical open DEM relative accuracy class (rule of thumb 0.5–1× GSD)
    vert = max(2.0, res * 0.5)
    if provider and "terrarium" in provider.lower():
        factors.append("AWS Terrarium ~30 m global; not survey-grade")
        vert = max(vert, 10.0)
    if refraction_k is None:
        factors.append("No atmospheric refraction on geometric LOS ray")
        conf = 0.55
        grade: DecisionGrade = "exploratory"
    else:
        factors.append(f"Refraction k={refraction_k} (standard atmosphere approx)")
        conf = 0.72
        grade = "operational_support"
    if res > 25:
        conf = min(conf, 0.65)
        factors.append("Coarse DEM GSD limits tactical confidence")
    if sample_distance_m > res:
        factors.append("sample_distance_m coarser than DEM GSD")
        conf = min(conf, 0.6)
    # Always attach safety binding grade tag for consumers that ignore numerics
    return TerrainQuality(
        decision_grade=grade,
        horizontal_uncertainty_m=round(horiz, 1),
        vertical_uncertainty_m=round(vert, 1),
        dem_resolution_m=round(res, 2),
        vertical_datum=vertical_datum,
        crs=crs,
        refraction_model=("none" if refraction_k is None else f"effective_earth_k={refraction_k}"),
        curvature_applied=curvature_applied,
        confidence_0_1=round(conf, 2),
        limiting_factors=tuple(factors),
    )


def build_viewshed_quality(
    *,
    dem_resolution_m: float | None,
    max_distance_m: float,
    curvature_coeff: float,
    crs: str = "EPSG:4326",
    vertical_datum: str = "unknown",
) -> TerrainQuality:
    res = dem_resolution_m if dem_resolution_m and dem_resolution_m > 0 else 30.0
    factors = [
        "GDAL Wang viewshed (edge mode)",
        "Clutter not modeled",
        f"max_distance_m={max_distance_m}",
    ]
    if abs(curvature_coeff - 1.0) > 1e-6:
        factors.append(f"curvature_coeff={curvature_coeff}")
    conf = 0.7 if res <= 15 else 0.6 if res <= 30 else 0.5
    if max_distance_m > 20_000:
        factors.append("Long-range viewshed: geographic CRS conversion is approximate")
        conf = min(conf, 0.55)
    return TerrainQuality(
        decision_grade="operational_support" if conf >= 0.6 else "exploratory",
        horizontal_uncertainty_m=round(res, 1),
        vertical_uncertainty_m=round(max(2.0, res * 0.5), 1),
        dem_resolution_m=round(res, 2),
        vertical_datum=vertical_datum,
        crs=crs,
        refraction_model=f"gdal_curvature_coeff={curvature_coeff}",
        curvature_applied=True,
        confidence_0_1=round(conf, 2),
        limiting_factors=tuple(factors),
    )
