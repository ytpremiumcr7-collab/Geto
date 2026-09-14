"""Fuente sin API externa: lee GeoJSON/JSON desde un prefijo MinIO (drop zone).

Flujo ops:
  1. Un proceso o partner sube archivos a s3://bucket/incoming/{tenant}/...
  2. SourceJob `minio_dropzone` lista objetos nuevos, normaliza, mueve a processed/.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from minio import Minio

from app.core.config import settings
from app.domain.models import GeoPoint, Observation
from app.sources.base import SourceAdapter, SourceMetadata


class MinIODropzoneAdapter(SourceAdapter):
    metadata = SourceMetadata(
        source_id="minio_dropzone",
        source_type="file_drop",
        description="GeoJSON/JSON drop zone on MinIO (no external API)",
        endpoint="minio://geoint-raw/incoming/",
        authentication="minio_credentials",
        license_name="operator-controlled",
        commercial_allowed=True,
        attribution_required=False,
    )

    def __init__(self) -> None:
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        self.bucket = getattr(settings, "minio_bucket_dropzone", None) or settings.minio_bucket_raw
        self.prefix_incoming = getattr(settings, "dropzone_prefix_incoming", "incoming/")
        self.prefix_processed = getattr(settings, "dropzone_prefix_processed", "processed/")
        self.prefix_failed = getattr(settings, "dropzone_prefix_failed", "failed/")

    def _ensure_bucket(self) -> None:
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    async def health(self) -> bool:
        try:
            self._ensure_bucket()
            return True
        except Exception:
            return False

    async def fetch(self, prefix: str | None = None, max_objects: int = 50) -> Any:
        """Lista y descarga hasta max_objects del prefijo incoming."""
        self._ensure_bucket()
        base = prefix or self.prefix_incoming
        objects = self.client.list_objects(self.bucket, prefix=base, recursive=True)
        batch: list[dict[str, Any]] = []
        for obj in objects:
            if obj.is_dir:
                continue
            name = obj.object_name or ""
            if not name.endswith((".json", ".geojson")):
                continue
            response = self.client.get_object(self.bucket, name)
            try:
                raw = response.read()
                data = json.loads(raw.decode("utf-8"))
            finally:
                response.close()
                response.release_conn()
            batch.append({"key": name, "payload": data})
            if len(batch) >= max_objects:
                break
        return batch

    def mark_processed(self, key: str, *, failed: bool = False) -> None:
        """Mueve objeto a processed/ o failed/ (copy + remove)."""
        dest_prefix = self.prefix_failed if failed else self.prefix_processed
        # conservar nombre de archivo
        filename = key.rsplit("/", 1)[-1]
        dest = f"{dest_prefix.rstrip('/')}/{filename}"
        from minio.commonconfig import CopySource

        self.client.copy_object(
            self.bucket,
            dest,
            CopySource(self.bucket, key),
        )
        self.client.remove_object(self.bucket, key)

    async def normalize(
        self,
        raw_data: Any,
        received_at: datetime,
    ) -> AsyncIterator[Observation]:
        if not isinstance(raw_data, list):
            return

        for item in raw_data:
            key = item.get("key", "unknown")
            payload = item.get("payload")
            try:
                async for obs in self._normalize_payload(payload, received_at, key):
                    yield obs
                try:
                    self.mark_processed(key, failed=False)
                except Exception:
                    pass
            except Exception:
                try:
                    self.mark_processed(key, failed=True)
                except Exception:
                    pass

    async def _normalize_payload(
        self,
        payload: Any,
        received_at: datetime,
        source_key: str,
    ) -> AsyncIterator[Observation]:
        # FeatureCollection
        if isinstance(payload, dict) and payload.get("type") == "FeatureCollection":
            for feature in payload.get("features") or []:
                obs = self._feature_to_observation(feature, received_at, source_key)
                if obs:
                    yield obs
            return

        # single Feature
        if isinstance(payload, dict) and payload.get("type") == "Feature":
            obs = self._feature_to_observation(payload, received_at, source_key)
            if obs:
                yield obs
            return

        # lista de observations ya normalizadas / dicts planos
        if isinstance(payload, list):
            for row in payload:
                obs = self._dict_to_observation(row, received_at, source_key)
                if obs:
                    yield obs
            return

        if isinstance(payload, dict):
            obs = self._dict_to_observation(payload, received_at, source_key)
            if obs:
                yield obs

    def _feature_to_observation(
        self,
        feature: dict,
        received_at: datetime,
        source_key: str,
    ) -> Observation | None:
        props = feature.get("properties") or {}
        geom = feature.get("geometry") or {}
        coords = geom.get("coordinates") or []
        position = None
        if geom.get("type") == "Point" and len(coords) >= 2:
            position = GeoPoint(
                lon=float(coords[0]),
                lat=float(coords[1]),
                altitude_m=float(coords[2]) if len(coords) > 2 else None,
            )

        entity_id = str(
            props.get("entity_id")
            or feature.get("id")
            or props.get("id")
            or f"drop:{source_key}:{props.get('name', 'unk')}"
        )
        entity_type = str(props.get("entity_type") or props.get("type") or "unknown")

        observed_at = received_at
        for key in ("observed_at", "time", "datetime", "timestamp"):
            if props.get(key):
                try:
                    raw_t = props[key]
                    if isinstance(raw_t, (int, float)):
                        observed_at = datetime.fromtimestamp(
                            raw_t / 1000 if raw_t > 1e12 else raw_t,
                            tz=UTC,
                        )
                    else:
                        observed_at = datetime.fromisoformat(str(raw_t).replace("Z", "+00:00"))
                except Exception:
                    pass
                break

        return Observation(
            entity_id=entity_id,
            entity_type=entity_type,
            source_id="minio_dropzone",
            source_record_id=f"{source_key}:{entity_id}",
            observed_at=observed_at,
            received_at=received_at,
            position=position,
            attributes={k: v for k, v in props.items() if k not in {"entity_id", "entity_type"}},
            provenance={
                "source_id": "minio_dropzone",
                "object_key": source_key,
                "adapter": self.__class__.__name__,
            },
            raw_payload=feature,
        )

    def _dict_to_observation(
        self,
        row: dict,
        received_at: datetime,
        source_key: str,
    ) -> Observation | None:
        lon = row.get("lon") or row.get("longitude") or row.get("lng")
        lat = row.get("lat") or row.get("latitude")
        position = None
        if lon is not None and lat is not None:
            position = GeoPoint(lon=float(lon), lat=float(lat), altitude_m=row.get("altitude_m"))

        entity_id = str(row.get("entity_id") or row.get("id") or f"drop:{source_key}")
        return Observation(
            entity_id=entity_id,
            entity_type=str(row.get("entity_type") or "unknown"),
            source_id="minio_dropzone",
            source_record_id=str(row.get("id") or entity_id),
            observed_at=received_at,
            received_at=received_at,
            position=position,
            attributes=row,
            provenance={"source_id": "minio_dropzone", "object_key": source_key},
            raw_payload=row,
        )
