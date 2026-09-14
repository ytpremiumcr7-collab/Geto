import os

import pytest
from httpx import ASGITransport, AsyncClient

# Auth deshabilitado en tests de integración ASGI
os.environ["AUTH_DISABLED"] = "true"

# Settings se cachean: limpiar antes de importar app
from app.core.config import get_settings

get_settings.cache_clear()

from app.main import app  # noqa: E402


@pytest.mark.asyncio
async def test_sources_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/sources")

    assert response.status_code == 200
    sources = response.json()["sources"]
    ids = {source["source_id"] for source in sources}
    assert "opensky" in ids
    assert "celestrak" in ids
    assert "usgs_earthquake" in ids
    assert "nasa_firms" in ids
    assert "aviation_weather" in ids
    assert "copernicus" in ids
    assert "minio_dropzone" in ids
    assert "readsb_local" in ids
    assert "ais_file" in ids
    assert "jpl_horizons" in ids
    assert "nexrad" in ids
    assert "goes" in ids
