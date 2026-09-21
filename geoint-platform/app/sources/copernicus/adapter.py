from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

import httpx

from app.core.config import settings
from app.domain.models import Observation
from app.sources.base import SourceAdapter, SourceMetadata


class CopernicusSTACAdapter(SourceAdapter):
    metadata = SourceMetadata(
        source_id="copernicus",
        source_type="satellite_imagery",
        description="Copernicus Data Space STAC catalog",
        endpoint="https://stac.dataspace.copernicus.eu/v1/",
        authentication="none",
        license_name="Copernicus Data Space terms",
        commercial_allowed=None,
        attribution_required=True,
    )

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get(
                    f"{settings.copernicus_stac_url.rstrip('/')}/collections"
                )

                return response.is_success

        except Exception:
            return False

    async def fetch(
        self,
        bbox: list[float] | None = None,
        datetime_range: str | None = None,
        limit: int = 20,
            **kwargs: Any,
) -> Any:
        self._reject_unexpected_fetch_kwargs(kwargs)
        payload = {
            "collections": [settings.copernicus_collection],
            "limit": limit,
        }

        if bbox:
            payload["bbox"] = bbox

        if datetime_range:
            payload["datetime"] = datetime_range

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{settings.copernicus_stac_url.rstrip('/')}/search",
                json=payload,
            )

            response.raise_for_status()

            return response.json()

    async def normalize(
        self,
        raw_data: Any,
        received_at: datetime,
    ) -> AsyncIterator[Observation]:
        for item in raw_data.get("features", []):
            item_id = item.get("id")

            if not item_id:
                continue

            properties = item.get("properties", {})
            geometry = item.get("geometry")

            position = None

            if geometry and geometry.get("type") == "Point":
                coords = geometry.get("coordinates", [])

                if len(coords) >= 2:
                    from app.domain.models import GeoPoint

                    position = GeoPoint(
                        lon=coords[0],
                        lat=coords[1],
                    )

            observed_at = received_at

            dt = properties.get("datetime")

            if dt:
                try:
                    observed_at = datetime.fromisoformat(dt.replace("Z", "+00:00"))
                except Exception:
                    pass

            yield Observation(
                entity_id=f"satellite_image:{item_id}",
                entity_type="satellite_image",
                source_id="copernicus",
                source_record_id=item_id,
                observed_at=observed_at,
                received_at=received_at,
                position=position,
                attributes={
                    "collection": item.get("collection"),
                    "assets": item.get("assets"),
                    "cloud_cover": properties.get("eo:cloud_cover"),
                    "platform": properties.get("platform"),
                    "constellation": properties.get("constellation"),
                },
                provenance={
                    "source_id": "copernicus",
                    "adapter": self.__class__.__name__,
                },
                raw_payload=item,
            )
