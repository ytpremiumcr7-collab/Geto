from __future__ import annotations

import pytest

from app.sources.usgs.adapter import USGSEarthquakeAdapter


@pytest.mark.asyncio
async def test_concrete_adapter_rejects_unknown_fetch_keyword_before_io():
    adapter = USGSEarthquakeAdapter()

    with pytest.raises(TypeError, match="unexpected fetch keyword argument"):
        await adapter.fetch(typo_parameter=True)
