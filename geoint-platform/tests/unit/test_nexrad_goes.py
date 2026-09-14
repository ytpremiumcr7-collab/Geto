from datetime import datetime, timezone

import pytest

from app.sources.goes.adapter import GOESAdapter
from app.sources.nexrad.adapter import NEXRADAdapter


@pytest.mark.asyncio
async def test_nexrad_normalize_from_xml():
    adapter = NEXRADAdapter()
    xml = """<?xml version="1.0"?>
    <ListBucketResult>
      <Contents><Key>2024/01/01/KTLX/KTLX20240101_120000_V06</Key></Contents>
    </ListBucketResult>
    """
    raw = {"site": "KTLX", "xml": xml}
    result = []
    async for obs in adapter.normalize(raw, datetime.now(timezone.utc)):
        result.append(obs)
    assert len(result) == 1
    assert result[0].entity_id == "nexrad:KTLX"
    assert result[0].position is not None


@pytest.mark.asyncio
async def test_goes_normalize_from_xml():
    adapter = GOESAdapter()
    xml = """<?xml version="1.0"?>
    <ListBucketResult>
      <Contents><Key>ABI-L2-CMIPF/2024/001/12/OR_ABI-L2-CMIPF-M6C13_G16_s20240011200000_e20240011200000_c20240011200000.nc</Key></Contents>
    </ListBucketResult>
    """
    raw = {"product": "ABI-L2-CMIPF", "xml": xml, "bucket_url": "https://noaa-goes16.s3.amazonaws.com"}
    result = []
    async for obs in adapter.normalize(raw, datetime.now(timezone.utc)):
        result.append(obs)
    assert len(result) == 1
    assert result[0].source_id == "goes"
