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
