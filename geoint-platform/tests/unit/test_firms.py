from datetime import UTC, datetime

import pytest

from app.sources.firms.adapter import NASAFIRMSAdapter


@pytest.mark.asyncio
async def test_firms_normalization():
    adapter = NASAFIRMSAdapter()

    payload = """latitude,longitude,bright_ti4,acq_date,acq_time,satellite,confidence
19.0,-98.0,320.1,2026-01-01,1200,NOAA-20,high
"""

    result = []

    async for obs in adapter.normalize(
        payload,
        datetime.now(UTC),
    ):
        result.append(obs)

    assert len(result) == 1
    assert result[0].entity_type == "fire"
    assert result[0].confidence == 1.0
