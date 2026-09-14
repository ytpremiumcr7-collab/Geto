from datetime import datetime, timezone
from typing import Any, AsyncIterator

import httpx

from app.core.config import settings
from app.domain.models import GeoPoint, Observation
from app.sources.base import SourceAdapter, SourceMetadata


class AviationWeatherAdapter(SourceAdapter):

    metadata = SourceMetadata(
        source_id="aviation_weather",
        source_type="weather",
        description="AviationWeather.gov METAR data",
        endpoint="https://aviationweather.gov/api/data",
        authentication="none",
        license_name="AviationWeather.gov",
        commercial_allowed=True,
        attribution_required=True,
    )

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(
                timeout=20,
                headers={
                    "User-Agent":
                        settings.aviation_weather_user_agent
                },
            ) as client:

                response = await client.get(
                    f"{settings.aviation_weather_base_url}/metar",
                    params={
                        "ids": "KMCI",
                        "format": "json",
                    },
                )

                return response.is_success

        except Exception:
            return False

    async def fetch(
        self,
        station_ids: str = "KMCI",
    ) -> Any:

        async with httpx.AsyncClient(
            timeout=30,
            headers={
                "User-Agent":
                    settings.aviation_weather_user_agent
            },
        ) as client:

            response = await client.get(
                f"{settings.aviation_weather_base_url}/metar",
                params={
                    "ids": station_ids,
                    "format": "json",
                },
            )

            response.raise_for_status()

            return response.json()

    async def normalize(
        self,
        raw_data: Any,
        received_at: datetime,
    ) -> AsyncIterator[Observation]:

        if isinstance(raw_data, dict):
            records = raw_data.get("data", [])
        else:
            records = raw_data

        for row in records:

            station = row.get("icaoId")

            lat = row.get("lat")
            lon = row.get("lon")

            if not station or lat is None or lon is None:
                continue

            report_time = row.get("reportTime")

            try:
                observed_at = (
                    datetime.fromisoformat(
                        report_time.replace(
                            "Z",
                            "+00:00",
                        )
                    )
                    if report_time
                    else received_at
                )
            except Exception:
                observed_at = received_at

            yield Observation(
                entity_id=f"airport:{station}",
                entity_type="airport",
                source_id="aviation_weather",
                source_record_id=station,
                observed_at=observed_at,
                received_at=received_at,
                position=GeoPoint(
                    lon=float(lon),
                    lat=float(lat),
                ),
                attributes={
                    "station": station,
                    "raw_metar": row.get("rawOb"),
                    "temperature_c": row.get("temp"),
                    "dewpoint_c": row.get("dewp"),
                    "wind_dir_deg": row.get("wdir"),
                    "wind_speed_kt": row.get("wspd"),
                    "wind_gust_kt": row.get("wgst"),
                    "visibility_m": row.get("visib"),
                    "altimeter_hpa": row.get("altim"),
                    "clouds": row.get("clouds"),
                },
                provenance={
                    "source_id": "aviation_weather",
                    "adapter": self.__class__.__name__,
                },
                raw_payload=row,
            )

