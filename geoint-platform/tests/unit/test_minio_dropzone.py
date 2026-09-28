from datetime import UTC, datetime

import pytest

from app.sources.minio_dropzone.adapter import MinIODropzoneAdapter


@pytest.mark.asyncio
async def test_dropzone_geojson_feature_collection():
    adapter = MinIODropzoneAdapter()
    # No llamar a MinIO: solo normalize
    payload = [
        {
            "key": "incoming/test.geojson",
            "payload": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "id": "obj-1",
                        "properties": {
                            "entity_type": "vehicle",
                            "name": "Truck A",
                        },
                        "geometry": {
                            "type": "Point",
                            "coordinates": [-99.13, 19.43],
                        },
                    }
                ],
            },
        }
    ]
    # Evitar mark_processed real
    adapter.mark_processed = lambda *a, **k: None  # type: ignore

    result = []
    async for obs in adapter.normalize(payload, datetime.now(UTC)):
        result.append(obs)

    assert len(result) == 1
    assert result[0].entity_id == "obj-1"
    assert result[0].position is not None
    assert result[0].position.lon == -99.13
    assert result[0].source_id == "minio_dropzone"


def test_dropzone_does_not_autocreate_bucket_when_disabled(monkeypatch):
    from app.sources.minio_dropzone import adapter as adapter_mod

    class FakeClient:
        def __init__(self):
            self.created = []

        def bucket_exists(self, _bucket):
            return False

        def make_bucket(self, bucket):
            self.created.append(bucket)

    adapter = object.__new__(MinIODropzoneAdapter)
    adapter.bucket = "tenant-dropzone"
    adapter.client = FakeClient()
    monkeypatch.setattr(adapter_mod.settings, "minio_create_bucket", False)

    with pytest.raises(RuntimeError, match="MINIO_CREATE_BUCKET"):
        adapter._ensure_bucket()

    assert adapter.client.created == []
