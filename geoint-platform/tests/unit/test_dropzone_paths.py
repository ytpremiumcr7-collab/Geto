import pytest

from app.ingestion.dispatcher import _fetch_kwargs
from app.sources.minio_dropzone.adapter import MinIODropzoneAdapter


def test_processed_destination_preserves_relative_path():
    adapter = object.__new__(MinIODropzoneAdapter)
    adapter.prefix_incoming = "incoming/"
    adapter.prefix_processed = "processed/"
    adapter.prefix_failed = "failed/"

    assert (
        adapter.destination_key("incoming/tenant-a/2026/track.json", failed=False)
        == "processed/tenant-a/2026/track.json"
    )
    assert (
        adapter.destination_key("incoming/tenant-b/track.json", failed=True)
        == "failed/tenant-b/track.json"
    )


def test_dropzone_fetch_prefix_is_tenant_scoped():
    kwargs = _fetch_kwargs("minio_dropzone", {}, tenant_id="tenant-a")
    assert kwargs["prefix"] == "incoming/tenant-a/"

    with pytest.raises(ValueError, match="tenant dropzone"):
        _fetch_kwargs(
            "minio_dropzone",
            {"prefix": "incoming/tenant-b/private/"},
            tenant_id="tenant-a",
        )
