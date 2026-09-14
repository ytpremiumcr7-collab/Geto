"""MinIO ObjectStore — JSON + binary (COG/GeoTIFF) via to_thread."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from io import BytesIO

from minio import Minio

from app.core.config import settings


class ObjectStore:
    def __init__(self):
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )

    def ensure_bucket(self, bucket: str | None = None) -> str:
        b = bucket or settings.minio_bucket_raw
        if not self.client.bucket_exists(b):
            self.client.make_bucket(b)
        return b

    def _put_json_sync(self, key: str, payload) -> str:
        data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        bucket = self.ensure_bucket()
        self.client.put_object(
            bucket,
            key,
            BytesIO(data),
            length=len(data),
            content_type="application/json",
        )
        return f"s3://{bucket}/{key}"

    async def put_json(self, key: str, payload) -> str:
        return await asyncio.to_thread(self._put_json_sync, key, payload)

    def put_json_sync(self, key: str, payload) -> str:
        return self._put_json_sync(key, payload)

    def _put_bytes_sync(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        bucket: str | None = None,
    ) -> str:
        b = self.ensure_bucket(bucket)
        self.client.put_object(
            b,
            key,
            BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        return f"s3://{b}/{key}"

    async def put_bytes(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        bucket: str | None = None,
    ) -> str:
        return await asyncio.to_thread(
            self._put_bytes_sync, key, data, content_type, bucket
        )

    def _get_bytes_sync(self, key: str, bucket: str | None = None) -> bytes:
        b = bucket or settings.minio_bucket_raw
        response = self.client.get_object(b, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    async def get_bytes(self, key: str, bucket: str | None = None) -> bytes:
        return await asyncio.to_thread(self._get_bytes_sync, key, bucket)

    def make_key(self, source_id: str, entity_id: str | None = None) -> str:
        now = datetime.now(timezone.utc)
        suffix = entity_id or "batch"
        return f"{source_id}/{now:%Y/%m/%d}/{now:%H%M%S}_{suffix}.json"
