from datetime import datetime
from typing import Any, AsyncIterator

import httpx

from app.core.config import settings
from app.domain.models import Observation
from app.sources.base import SourceAdapter, SourceMetadata


class CelesTrakAdapter(SourceAdapter):

    metadata = SourceMetadata(
        source_id="celestrak",
        source_type="orbit",
        description="CelesTrak GP orbital elements",
        endpoint="https://celestrak.org/NORAD/elements/gp.php",
        authentication="none",
        license_name="CelesTrak usage policy",
        commercial_allowed=None,
        attribution_required=True,
    )

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get(
                    settings.celestrak_base_url,
                    params={
                        "GROUP": settings.celestrak_group,
                        "FORMAT": "JSON",
                    },
                )

                return response.is_success

        except Exception:
            return False

    async def fetch(
        self,
        group: str | None = None,
    ) -> Any:

        async with httpx.AsyncClient(timeout=30) as client:

            response = await client.get(
                settings.celestrak_base_url,
                params={
                    "GROUP": group or settings.celestrak_group,
                    "FORMAT": "JSON",
                },
            )

            response.raise_for_status()

            return response.json()

    async def normalize(
        self,
        raw_data: Any,
        received_at: datetime,
    ) -> AsyncIterator[Observation]:

        for item in raw_data:

            norad_id = item.get("NORAD_CAT_ID")

            if not norad_id:
                continue

            yield Observation(
                entity_id=f"norad:{norad_id}",
                entity_type="satellite",
                source_id="celestrak",
                source_record_id=str(norad_id),
                observed_at=received_at,
                received_at=received_at,
                attributes={
                    "name": item.get("OBJECT_NAME"),
                    "object_id": item.get("OBJECT_ID"),
                    "epoch": item.get("EPOCH"),
                    "mean_motion": item.get("MEAN_MOTION"),
                    "eccentricity": item.get("ECCENTRICITY"),
                    "inclination": item.get("INCLINATION"),
                    "raan": item.get("RA_OF_ASC_NODE"),
                    "arg_perigee": item.get("ARG_OF_PERICENTER"),
                    "mean_anomaly": item.get("MEAN_ANOMALY"),
                    "bstar": item.get("BSTAR"),
                    "tle_line1": item.get("TLE_LINE1"),
                    "tle_line2": item.get("TLE_LINE2"),
                },
                provenance={
                    "source_id": "celestrak",
                    "adapter": self.__class__.__name__,
                },
                raw_payload=item,
            )

