from datetime import datetime, timezone

import pytest

from app.sources.ais.adapter import AISFileAdapter


@pytest.mark.asyncio
async def test_ais_csv_normalize():
    adapter = AISFileAdapter(path="/tmp/x.csv")
    csv_text = """MMSI,LAT,LON,SOG,COG,BaseDateTime,VesselName
366123456,29.75,-95.36,12.5,90,2024-01-15 12:00:00,TEST VESSEL
"""
    raw = {"format": "csv", "path": "x.csv", "data": csv_text}
    result = []
    async for obs in adapter.normalize(raw, datetime.now(timezone.utc)):
        result.append(obs)

    assert len(result) == 1
    assert result[0].entity_id == "mmsi:366123456"
    assert result[0].entity_type == "vessel"
    assert result[0].position.lat == 29.75


@pytest.mark.asyncio
async def test_ais_geojson_normalize():
    adapter = AISFileAdapter()
    raw = {
        "format": "geojson",
        "path": "x.geojson",
        "data": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"MMSI": "111", "SOG": 5, "COG": 10},
                    "geometry": {"type": "Point", "coordinates": [-70.0, 42.0]},
                }
            ],
        },
    }
    result = []
    async for obs in adapter.normalize(raw, datetime.now(timezone.utc)):
        result.append(obs)
    assert len(result) == 1
    assert result[0].entity_id == "mmsi:111"
