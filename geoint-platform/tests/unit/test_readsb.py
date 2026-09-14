from datetime import datetime, timezone

import pytest

from app.sources.readsb.adapter import ReadsbLocalAdapter


@pytest.mark.asyncio
async def test_readsb_normalize():
    adapter = ReadsbLocalAdapter(path="/tmp/does-not-matter.json")
    payload = {
        "now": 1700000000.0,
        "aircraft": [
            {
                "hex": "abc123",
                "flight": "TEST1  ",
                "lat": 19.43,
                "lon": -99.13,
                "alt_baro": 10000,
                "gs": 400,
                "track": 180,
                "seen_pos": 1.0,
            },
            {"hex": "no_pos"},  # skip
        ],
    }
    result = []
    async for obs in adapter.normalize(payload, datetime.now(timezone.utc)):
        result.append(obs)

    assert len(result) == 1
    assert result[0].entity_id == "icao24:abc123"
    assert result[0].source_id == "readsb_local"
    assert result[0].position.lat == 19.43
    assert result[0].attributes["flight"] == "TEST1"
