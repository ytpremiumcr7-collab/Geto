from datetime import UTC, datetime

import pytest

from app.sources.horizons.adapter import JPLHorizonsAdapter


@pytest.mark.asyncio
async def test_horizons_normalize_excerpt():
    adapter = JPLHorizonsAdapter()
    raw = {"result": "Target body name: Earth (399)\nSome ephemeris lines\n"}
    result = []
    async for obs in adapter.normalize(raw, datetime.now(UTC)):
        result.append(obs)
    assert len(result) == 1
    assert result[0].source_id == "jpl_horizons"
    assert "earth" in result[0].entity_id
