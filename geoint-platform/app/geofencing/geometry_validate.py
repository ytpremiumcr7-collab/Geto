"""Validate geofence GeoJSON before persist — reject pathological geometries."""

from __future__ import annotations

from typing import Any

from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.validation import explain_validity, make_valid

MAX_COORDINATES = 50_000
MAX_GEOJSON_BYTES = 2_000_000


class InvalidGeofenceGeometry(ValueError):
    pass


def validate_and_normalize_geofence_geometry(geojson: dict[str, Any]) -> MultiPolygon:
    import json

    raw = json.dumps(geojson, default=str)
    if len(raw.encode("utf-8")) > MAX_GEOJSON_BYTES:
        raise InvalidGeofenceGeometry(
            f"geometry payload exceeds {MAX_GEOJSON_BYTES} bytes"
        )

    try:
        geom = shape(geojson)
    except Exception as e:
        raise InvalidGeofenceGeometry(f"invalid GeoJSON: {e}") from e

    if geom.is_empty:
        raise InvalidGeofenceGeometry("geometry is empty")

    # Count coordinates (rough complexity bound)
    coords = 0
    try:
        def _count(g):
            nonlocal coords
            if g.is_empty:
                return
            if g.geom_type == "Polygon":
                coords += len(g.exterior.coords)
                for ring in g.interiors:
                    coords += len(ring.coords)
            elif g.geom_type == "MultiPolygon":
                for poly in g.geoms:
                    _count(poly)
            else:
                coords += len(getattr(g, "coords", []) or [])

        _count(geom)
    except Exception:
        coords = MAX_COORDINATES + 1
    if coords > MAX_COORDINATES:
        raise InvalidGeofenceGeometry(
            f"geometry has too many coordinates ({coords} > {MAX_COORDINATES})"
        )

    if not geom.is_valid:
        geom = make_valid(geom)
        if geom.is_empty or not geom.is_valid:
            raise InvalidGeofenceGeometry(
                f"geometry invalid and could not be repaired: {explain_validity(shape(geojson))}"
            )

    if geom.geom_type == "Polygon":
        geom = MultiPolygon([geom])
    elif geom.geom_type == "GeometryCollection":
        polys = [g for g in geom.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
        if not polys:
            raise InvalidGeofenceGeometry("no polygon in geometry collection")
        parts = []
        for g in polys:
            if g.geom_type == "Polygon":
                parts.append(g)
            else:
                parts.extend(list(g.geoms))
        geom = MultiPolygon(parts)
    if geom.geom_type != "MultiPolygon":
        raise InvalidGeofenceGeometry(
            f"geometry must be Polygon or MultiPolygon, got {geom.geom_type}"
        )

    # Bounds sanity (WGS84)
    minx, miny, maxx, maxy = geom.bounds
    if miny < -90 or maxy > 90 or minx < -180 or maxx > 180:
        raise InvalidGeofenceGeometry("coordinates out of WGS84 bounds")

    return geom
