import csv
import io
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import settings
from app.domain.models import GeoPoint, Observation
from app.sources.base import SourceAdapter, SourceMetadata


class NASAFIRMSAdapter(SourceAdapter):
    metadata = SourceMetadata(
        source_id="nasa_firms",
        source_type="wildfire",
        description="NASA FIRMS fire detections",
        endpoint="https://firms.modaps.eosdis.nasa.gov/api/area/",
        authentication="map_key",
        license_name="NASA FIRMS",
        commercial_allowed=True,
        attribution_required=True,
    )

    async def health(self) -> bool:
        if not settings.firms_map_key:
            return False

        try:
            url = (
                "https://firms.modaps.eosdis.nasa.gov/"
                "api/area/csv/"
                f"{settings.firms_map_key}/"
                f"{settings.firms_source}/"
                f"{settings.firms_bbox}/"
                "1"
            )

            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(url)
                return response.is_success

        except Exception:
            return False

    async def fetch(self, **kwargs: Any) -> Any:
        self._reject_unexpected_fetch_kwargs(kwargs)
        if not settings.firms_map_key:
            raise RuntimeError("FIRMS_MAP_KEY is not configured")

        url = (
            "https://firms.modaps.eosdis.nasa.gov/"
            "api/area/csv/"
            f"{settings.firms_map_key}/"
            f"{settings.firms_source}/"
            f"{settings.firms_bbox}/"
            f"{settings.firms_day_range}"
        )

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(url)
            response.raise_for_status()

            return response.text

    async def normalize(
        self,
        raw_data: Any,
        received_at: datetime,
    ) -> AsyncIterator[Observation]:
        reader = csv.DictReader(io.StringIO(raw_data))

        for row in reader:
            try:
                latitude = float(row["latitude"])
                longitude = float(row["longitude"])
            except (
                KeyError,
                TypeError,
                ValueError,
            ):
                continue

            acq_date = row.get("acq_date")
            acq_time = row.get("acq_time")

            observed_at = received_at

            if acq_date and acq_time:
                try:
                    hhmm = acq_time.zfill(4)
                    observed_at = datetime.strptime(
                        f"{acq_date} {hhmm}",
                        "%Y-%m-%d %H%M",
                    ).replace(tzinfo=UTC)
                except ValueError:
                    pass

            entity_key = ":".join(
                [
                    row.get("satellite", "unknown"),
                    row.get("acq_date", ""),
                    row.get("acq_time", ""),
                    row.get("latitude", ""),
                    row.get("longitude", ""),
                ]
            )

            yield Observation(
                entity_id=f"fire:{entity_key}",
                entity_type="fire",
                source_id="nasa_firms",
                source_record_id=entity_key,
                observed_at=observed_at,
                received_at=received_at,
                position=GeoPoint(
                    lon=longitude,
                    lat=latitude,
                ),
                confidence=_parse_confidence(row.get("confidence")),
                attributes={
                    "satellite": row.get("satellite"),
                    "instrument": row.get("instrument"),
                    "bright_ti4": row.get("bright_ti4"),
                    "bright_ti5": row.get("bright_ti5"),
                    "frp": row.get("frp"),
                    "scan": row.get("scan"),
                    "track": row.get("track"),
                    "daynight": row.get("daynight"),
                    "version": row.get("version"),
                },
                provenance={
                    "source_id": "nasa_firms",
                    "adapter": self.__class__.__name__,
                },
                raw_payload=row,
            )


def _parse_confidence(value: str | None) -> float | None:
    if not value:
        return None

    value = value.strip().lower()

    if value in {"low", "l"}:
        return 0.33

    if value in {"nominal", "normal", "n"}:
        return 0.66

    if value in {"high", "h"}:
        return 1.0

    try:
        number = float(value)

        if number > 1:
            return min(number / 100, 1.0)

        return max(0.0, min(number, 1.0))

    except ValueError:
        return None
