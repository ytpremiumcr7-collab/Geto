from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import settings
from app.domain.models import GeoPoint, Observation
from app.sources.base import SourceAdapter, SourceMetadata
from app.sources.opensky.token import OpenSkyTokenManager


class OpenSkyAdapter(SourceAdapter):
    metadata = SourceMetadata(
        source_id="opensky",
        source_type="adsb",
        description="OpenSky Network aircraft state vectors (research/non-commercial; restricted)",
        endpoint="https://opensky-network.org/api",
        authentication="oauth2_client_credentials",
        license_name="OpenSky terms — commercial use requires authorization",
        commercial_allowed=False,
        attribution_required=True,
        access_policy="goodmode_only",
        commercial_status="restricted",
        retention="transient",
    )

    def __init__(self):
        self.tokens = OpenSkyTokenManager()

    async def _headers(self):
        token = await self.tokens.get_token()

        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

    async def health(self) -> bool:
        try:
            headers = await self._headers()

            async with httpx.AsyncClient(timeout=settings.opensky_timeout_seconds) as client:
                response = await client.get(
                    f"{settings.opensky_base_url}/states/all",
                    params={
                        "lamin": settings.default_aoi_south,
                        "lomin": settings.default_aoi_west,
                        "lamax": settings.default_aoi_north,
                        "lomax": settings.default_aoi_east,
                    },
                    headers=headers,
                )

                return response.is_success

        except Exception:
            return False

    async def fetch(
        self,
        lamin: float | None = None,
        lomin: float | None = None,
        lamax: float | None = None,
        lomax: float | None = None,
            **kwargs: Any,
) -> Any:
        self._reject_unexpected_fetch_kwargs(kwargs)
        headers = await self._headers()

        params = {}

        if lamin is not None:
            params["lamin"] = lamin

        if lomin is not None:
            params["lomin"] = lomin

        if lamax is not None:
            params["lamax"] = lamax

        if lomax is not None:
            params["lomax"] = lomax

        async with httpx.AsyncClient(timeout=settings.opensky_timeout_seconds) as client:
            response = await client.get(
                f"{settings.opensky_base_url}/states/all",
                params=params,
                headers=headers,
            )

            if response.status_code == 401:
                self.tokens.token = None
                headers = await self._headers()

                response = await client.get(
                    f"{settings.opensky_base_url}/states/all",
                    params=params,
                    headers=headers,
                )

            response.raise_for_status()

            return response.json()

    async def normalize(
        self,
        raw_data: Any,
        received_at: datetime,
    ) -> AsyncIterator[Observation]:
        states = raw_data.get("states") or []

        for state in states:
            if len(state) < 8:
                continue

            icao24 = state[0]

            longitude = state[5]
            latitude = state[6]

            if not icao24 or longitude is None or latitude is None:
                continue

            timestamp = (
                datetime.fromtimestamp(
                    state[3],
                    tz=UTC,
                )
                if state[3]
                else received_at
            )

            yield Observation(
                entity_id=f"icao24:{icao24}",
                entity_type="aircraft",
                source_id="opensky",
                source_record_id=icao24,
                observed_at=timestamp,
                received_at=received_at,
                position=GeoPoint(
                    lon=longitude,
                    lat=latitude,
                    altitude_m=(
                        state[7] if state[7] is not None else state[13] if len(state) > 13 else None
                    ),
                ),
                speed_mps=(state[9] if len(state) > 9 else None),
                heading_deg=(state[10] if len(state) > 10 else None),
                attributes={
                    "callsign": (state[1].strip() if state[1] else None),
                    "on_ground": state[8],
                    "vertical_rate_mps": (state[11] if len(state) > 11 else None),
                    "squawk": (state[14] if len(state) > 14 else None),
                },
                provenance={
                    "source_id": "opensky",
                    "adapter": self.__class__.__name__,
                },
                raw_payload=state,
            )
