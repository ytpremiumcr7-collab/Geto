from datetime import datetime, timezone

import pytest

from app.sources.usgs.adapter import USGSEarthquakeAdapter


@pytest.mark.asyncio
async def test_usgs_normalization():

    adapter = USGSEarthquakeAdapter()

    received = datetime.now(timezone.utc)

    payload = {
        "features": [
            {
                "id": "test123",
                "properties": {
                    "mag": 5.4,
                    "place": "Test",
                    "time": 1700000000000,
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [
                        -98.0,
                        19.0,
                        10.0,
                    ],
                },
            }
        ]
    }

    result = []

    async for obs in adapter.normalize(
        payload,
        received,
    ):
        result.append(obs)

    assert len(result) == 1
    assert result[0].entity_id == "earthquake:test123"
    assert result[0].position.lat == 19.0
    assert result[0].position.lon == -98.0
    assert result[0].attributes["magnitude"] == 5.4

