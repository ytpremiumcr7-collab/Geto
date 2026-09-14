from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import settings
from app.domain.models import GeoPoint, Observation
from app.sources.base import SourceAdapter, SourceMetadata


class USGSEarthquakeAdapter(SourceAdapter):
    metadata = SourceMetadata(
        source_id="usgs_earthquake",
        source_type="earthquake",
        description="USGS real-time earthquake GeoJSON",
        endpoint="https://earthquake.usgs.gov/earthquakes/feed/",
        authentication="none",
        license_name="USGS",
        commercial_allowed=True,
        attribution_required=True,
    )

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(settings.usgs_url)
                return response.is_success
        except Exception:
            return False

    async def fetch(self) -> Any:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(settings.usgs_url)
            response.raise_for_status()
            return response.json()

    async def normalize(
        self,
        raw_data: Any,
        received_at: datetime,
    ) -> AsyncIterator[Observation]:

        for feature in raw_data.get("features", []):
            properties = feature.get("properties") or {}
            geometry = feature.get("geometry") or {}

            coordinates = geometry.get("coordinates") or []

            if len(coordinates) < 2:
                continue

            longitude = coordinates[0]
            latitude = coordinates[1]
            depth_km = coordinates[2] if len(coordinates) > 2 else None

            event_id = feature.get("id")

            if not event_id:
                continue

            timestamp_ms = properties.get("time")

            observed_at = (
                datetime.fromtimestamp(
                    timestamp_ms / 1000,
                    tz=UTC,
                )
                if timestamp_ms
                else received_at
            )

            yield Observation(
                entity_id=f"earthquake:{event_id}",
                entity_type="earthquake",
                source_id="usgs_earthquake",
                source_record_id=event_id,
                observed_at=observed_at,
                received_at=received_at,
                position=GeoPoint(
                    lon=longitude,
                    lat=latitude,
                    altitude_m=(-depth_km * 1000 if depth_km is not None else None),
                ),
                confidence=None,
                attributes={
                    "magnitude": properties.get("mag"),
                    "place": properties.get("place"),
                    "url": properties.get("url"),
                    "felt": properties.get("felt"),
                    "cdi": properties.get("cdi"),
                    "mmi": properties.get("mmi"),
                    "alert": properties.get("alert"),
                    "status": properties.get("status"),
                    "tsunami": properties.get("tsunami"),
                    "sig": properties.get("sig"),
                    "net": properties.get("net"),
                    "code": properties.get("code"),
                    "types": properties.get("types"),
                },
                provenance={
                    "source_id": "usgs_earthquake",
                    "adapter": self.__class__.__name__,
                },
                raw_payload=feature,
            )
