"""ADS-B local vía readsb/dump1090: lee aircraft.json (sin API comercial).

readsb actualiza aircraft.json ~1/s. Configura READSB_AIRCRAFT_JSON_PATH.
Formato típico: { "now": <epoch>, "aircraft": [ { "hex", "lat", "lon", "alt_baro", ... } ] }
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.domain.models import GeoPoint, Observation
from app.sources.base import SourceAdapter, SourceMetadata


class ReadsbLocalAdapter(SourceAdapter):
    metadata = SourceMetadata(
        source_id="readsb_local",
        source_type="adsb",
        description="Local ADS-B via readsb/dump1090 aircraft.json (self-hosted)",
        endpoint="file://aircraft.json",
        authentication="none",
        license_name="Operator-owned receiver data",
        commercial_allowed=True,
        attribution_required=False,
        access_policy="internal",
        commercial_status="allowed",
        retention="standard",
    )

    def __init__(self, path: str | None = None) -> None:
        self.path = Path(
            path
            or getattr(settings, "readsb_aircraft_json_path", None)
            or "/run/readsb/aircraft.json"
        )

    async def health(self) -> bool:
        return self.path.is_file()

    async def fetch(self, path: str | None = None, **kwargs: Any) -> Any:
        self._reject_unexpected_fetch_kwargs(kwargs)
        target = Path(path) if path else self.path
        if not target.is_file():
            raise FileNotFoundError(f"readsb aircraft.json not found: {target}")
        text = target.read_text(encoding="utf-8")
        return json.loads(text)

    async def normalize(
        self,
        raw_data: Any,
        received_at: datetime,
    ) -> AsyncIterator[Observation]:
        if not isinstance(raw_data, dict):
            return

        now_epoch = raw_data.get("now")
        batch_time = received_at
        if isinstance(now_epoch, (int, float)):
            try:
                batch_time = datetime.fromtimestamp(float(now_epoch), tz=UTC)
            except (OSError, ValueError, OverflowError):
                pass

        for ac in raw_data.get("aircraft") or []:
            if not isinstance(ac, dict):
                continue
            hex_id = ac.get("hex")
            lat = ac.get("lat")
            lon = ac.get("lon")
            if not hex_id or lat is None or lon is None:
                continue

            alt = ac.get("alt_baro")
            if alt is None:
                alt = ac.get("alt_geom")
            # feet → meters if numeric
            alt_m = None
            if isinstance(alt, (int, float)) and alt != "ground":
                alt_m = float(alt) * 0.3048

            gs = ac.get("gs")  # knots
            speed_mps = float(gs) * 0.514444 if isinstance(gs, (int, float)) else None
            track = ac.get("track")
            heading = float(track) if isinstance(track, (int, float)) else None

            seen = ac.get("seen_pos") or ac.get("seen")
            observed_at = batch_time
            if isinstance(seen, (int, float)) and isinstance(now_epoch, (int, float)):
                try:
                    observed_at = datetime.fromtimestamp(float(now_epoch) - float(seen), tz=UTC)
                except (OSError, ValueError, OverflowError):
                    pass

            yield Observation(
                entity_id=f"icao24:{str(hex_id).lower()}",
                entity_type="aircraft",
                source_id="readsb_local",
                source_record_id=str(hex_id).lower(),
                observed_at=observed_at,
                received_at=received_at,
                position=GeoPoint(lon=float(lon), lat=float(lat), altitude_m=alt_m),
                speed_mps=speed_mps,
                heading_deg=heading,
                attributes={
                    "flight": (ac.get("flight") or "").strip() or None,
                    "squawk": ac.get("squawk"),
                    "category": ac.get("category"),
                    "nav_altitude_mcp": ac.get("nav_altitude_mcp"),
                    "baro_rate": ac.get("baro_rate"),
                    "rssi": ac.get("rssi"),
                    "messages": ac.get("messages"),
                    "on_ground": alt == "ground" or ac.get("alt_baro") == "ground",
                },
                provenance={
                    "source_id": "readsb_local",
                    "adapter": self.__class__.__name__,
                    "path": str(self.path),
                },
                raw_payload=ac,
            )
