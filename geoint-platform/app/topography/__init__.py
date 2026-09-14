"""Topography engine — DEM catalog, elevation, profile, slope, aspect, hillshade, LOS/viewshed."""

from app.topography.engine import TopographyEngine

__all__ = ["TopographyEngine", "TopographyService"]


def __getattr__(name: str):
    if name == "TopographyService":
        from app.topography.service import TopographyService

        return TopographyService
    raise AttributeError(name)
