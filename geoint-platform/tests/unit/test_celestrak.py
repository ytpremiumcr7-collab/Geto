from datetime import UTC, datetime

import pytest

from app.sources.celestrak.adapter import CelesTrakAdapter


@pytest.mark.asyncio
async def test_celestrak_normalization():
    adapter = CelesTrakAdapter()

    payload = [
        {
            "OBJECT_NAME": "ISS",
            "NORAD_CAT_ID": 25544,
            "OBJECT_ID": "1998-067A",
            "EPOCH": "2026-01-01T00:00:00.000Z",
            "MEAN_MOTION": 15.5,
        }
    ]

    result = []

    async for obs in adapter.normalize(
        payload,
        datetime.now(UTC),
    ):
        result.append(obs)

    assert len(result) == 1
    assert result[0].entity_id == "norad:25544"
