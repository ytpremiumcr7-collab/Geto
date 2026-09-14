"""ObjectStore binary put/get with mock MinIO client (no real network)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import app.infrastructure.object_store as osm


def test_put_get_bytes_roundtrip():
    store_data: dict[str, bytes] = {}

    mock_client = MagicMock()
    mock_client.bucket_exists.return_value = True

    def put_object(bucket, key, data, length, content_type=None):
        store_data[f"{bucket}/{key}"] = data.read() if hasattr(data, "read") else data

    def get_object(bucket, key):
        raw = store_data[f"{bucket}/{key}"]
        resp = MagicMock()
        resp.read.return_value = raw
        resp.close = MagicMock()
        resp.release_conn = MagicMock()
        return resp

    mock_client.put_object.side_effect = put_object
    mock_client.get_object.side_effect = get_object

    with patch.object(osm, "Minio", return_value=mock_client):
        with patch.object(osm, "settings") as settings:
            settings.minio_endpoint = "localhost:9000"
            settings.minio_access_key = "x"
            settings.minio_secret_key = "y"
            settings.minio_secure = False
            settings.minio_bucket_raw = "geoint-raw"

            store = osm.ObjectStore()
            payload = b"COG-FAKE-BYTES-12345"
            uri = store._put_bytes_sync("dem/test/a.tif", payload, "image/tiff")
            assert uri.startswith("s3://geoint-raw/")
            got = store._get_bytes_sync("dem/test/a.tif")
            assert got == payload
