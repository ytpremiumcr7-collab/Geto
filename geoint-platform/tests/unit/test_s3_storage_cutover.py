from pathlib import Path

from app.core.config import Settings
from app.policies.source_access import SOURCE_POLICIES
from app.sources.registry import create_adapters


def test_runtime_storage_contract_is_vendor_neutral_s3():
    fields = Settings.model_fields

    for required in (
        "s3_endpoint",
        "s3_access_key",
        "s3_secret_key",
        "s3_bucket_raw",
        "s3_secure",
        "s3_create_bucket",
    ):
        assert required in fields

    for legacy in (
        "minio_endpoint",
        "minio_access_key",
        "minio_secret_key",
        "minio_bucket_raw",
        "minio_secure",
        "minio_create_bucket",
    ):
        assert legacy not in fields


def test_dropzone_source_identity_is_s3_not_vendor_specific():
    adapters = create_adapters()

    assert "s3_dropzone" in adapters
    assert "minio_dropzone" not in adapters
    assert "s3_dropzone" in SOURCE_POLICIES
    assert "minio_dropzone" not in SOURCE_POLICIES


def test_production_compose_uses_maintained_s3_service_not_legacy_minio_images():
    root = Path(__file__).resolve().parents[2]
    compose = (root / "docker-compose.prod.yml").read_text()

    assert "object-store:" in compose
    assert "chrislusf/seaweedfs:4.47" in compose
    assert "minio/minio:" not in compose
    assert "minio/mc:" not in compose
    assert "minio-mc:" not in compose


def test_dr_uses_protocol_level_snapshot_tool_not_vendor_cli():
    root = Path(__file__).resolve().parents[2]
    backup = (root / "scripts" / "backup.sh").read_text()
    restore = (root / "scripts" / "restore.sh").read_text()

    assert "s3_snapshot.py" in backup
    assert "s3_snapshot.py" in restore
    assert "mc mirror" not in backup
    assert "mc mirror" not in restore
