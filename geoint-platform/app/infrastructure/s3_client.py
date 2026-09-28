"""Protocol-level S3 client helpers.

Geto contracts against S3 settings. The locked MinIO Python package is used only
as an implementation detail of the S3 transport and is not exposed to domain
modules or deployment configuration.
"""

from __future__ import annotations

from typing import Any

from minio import Minio
from minio.commonconfig import CopySource

from app.core.config import settings


def create_s3_client() -> Minio:
    return Minio(
        settings.s3_endpoint,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        secure=settings.s3_secure,
    )


def ensure_bucket(client: Any, bucket: str, *, allow_create: bool) -> str:
    if client.bucket_exists(bucket):
        return bucket
    if not allow_create:
        raise RuntimeError(f"S3 bucket {bucket!r} does not exist and S3_CREATE_BUCKET is false")
    client.make_bucket(bucket)
    return bucket


def copy_object(
    client: Any,
    *,
    bucket: str,
    source_key: str,
    destination_key: str,
) -> None:
    client.copy_object(
        bucket,
        destination_key,
        CopySource(bucket, source_key),
    )
