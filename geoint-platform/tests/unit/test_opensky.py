from datetime import UTC, datetime

import pytest

from app.sources.opensky.adapter import OpenSkyAdapter


@pytest.mark.asyncio
async def test_opensky_normalization():

    adapter = OpenSkyAdapter()

    payload = {
        "states": [
            [
                "abc123",
                "TEST123 ",
                "Mexico",
                1700000000,
                1700000000,
                -98.0,
                19.0,
                10000,
                False,
                220,
                90,
                0,
                None,
                10050,
                "1200",
            ]
        ]
    }

    result = []

    async for obs in adapter.normalize(
        payload,
        datetime.now(UTC),
    ):
        result.append(obs)

    assert len(result) == 1
    assert result[0].entity_id == "icao24:abc123"
    assert result[0].position.lon == -98.0
    assert result[0].position.lat == 19.0
    assert result[0].speed_mps == 220
