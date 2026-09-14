import pytest
from app.geofencing.geometry_validate import (
    InvalidGeofenceGeometry,
    validate_and_normalize_geofence_geometry,
)


def test_valid_polygon():
    g = {
        "type": "Polygon",
        "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
    }
    mp = validate_and_normalize_geofence_geometry(g)
    assert mp.geom_type == "MultiPolygon"


def test_rejects_empty():
    with pytest.raises(InvalidGeofenceGeometry):
        validate_and_normalize_geofence_geometry({"type": "Polygon", "coordinates": []})


def test_rejects_out_of_bounds():
    g = {
        "type": "Polygon",
        "coordinates": [[[0, 0], [1, 0], [1, 95], [0, 95], [0, 0]]],
    }
    with pytest.raises(InvalidGeofenceGeometry):
        validate_and_normalize_geofence_geometry(g)
