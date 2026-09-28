"""S3 ObjectStore — JSON + binary (COG/GeoTIFF) via to_thread."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from io import BytesIO
from uuid import uuid4

from app.core.config import settings
from app.infrastructure.s3_client import create_s3_client, ensure_bucket


class ObjectStore:
    def __init__(self):
        self.client = create_s3_client()

    def ensure_bucket(self, bucket: str | None = None) -> str:
        target = bucket or settings.s3_bucket_raw
        return ensure_bucket(
            self.client,
            target,
            allow_create=bool(settings.s3_create_bucket),
        )

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
        target = self.ensure_bucket(bucket)
        self.client.put_object(
            target,
            key,
            BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        return f"s3://{target}/{key}"

    async def put_bytes(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        bucket: str | None = None,
    ) -> str:
        return await asyncio.to_thread(self._put_bytes_sync, key, data, content_type, bucket)

    def _get_bytes_sync(self, key: str, bucket: str | None = None) -> bytes:
        target = bucket or settings.s3_bucket_raw
        response = self.client.get_object(target, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    async def get_bytes(self, key: str, bucket: str | None = None) -> bytes:
        return await asyncio.to_thread(self._get_bytes_sync, key, bucket)

    def make_key(
        self,
        source_id: str,
        entity_id: str | None = None,
        *,
        tenant_id: str = "default",
        job_id: str | None = None,
        message_id: str | None = None,
    ) -> str:
        """Tenant-scoped unique object key (no cross-tenant / same-second collisions)."""
        now = datetime.now(UTC)
        uid = uuid4().hex
        job_part = (job_id or "noj")[:36]
        msg_part = (message_id or uid)[:64]
        suffix = entity_id or "batch"
        return (
            f"raw/{tenant_id}/{source_id}/{now:%Y/%m/%d}/"
            f"{job_part}_{msg_part}_{suffix}_{uid}.json"
        )
