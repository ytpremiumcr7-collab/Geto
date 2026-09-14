"""AIS histórico / importación por archivo (CSV o GeoJSON).

Compatible con exports tipo MarineCadastre / AccessAIS (MMSI, LAT, LON, SOG, COG, BASEDATETIME).
Sin API de pago: apunta AIS_FILE_PATH o pasa path en config del job.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from app.core.config import settings
from app.domain.models import GeoPoint, Observation
from app.sources.base import SourceAdapter, SourceMetadata


class AISFileAdapter(SourceAdapter):
    metadata = SourceMetadata(
        source_id="ais_file",
        source_type="ais",
        description="AIS tracks from local CSV/GeoJSON (e.g. MarineCadastre exports)",
        endpoint="file://ais",
        authentication="none",
        license_name="Depends on dataset (NOAA MarineCadastre: public US data)",
        commercial_allowed=True,
        attribution_required=True,
        access_policy="operator",
        commercial_status="allowed",
        retention="long",
    )

    def __init__(self, path: str | None = None) -> None:
        self.path = Path(
            path or getattr(settings, "ais_file_path", None) or "/data/ais/latest.csv"
        )

    async def health(self) -> bool:
        return self.path.is_file()

    async def fetch(self, path: str | None = None) -> Any:
        target = Path(path) if path else self.path
        if not target.is_file():
            raise FileNotFoundError(f"AIS file not found: {target}")
        raw = target.read_text(encoding="utf-8", errors="replace")
        suffix = target.suffix.lower()
        if suffix in {".json", ".geojson"}:
            return {"format": "geojson", "path": str(target), "data": json.loads(raw)}
        return {"format": "csv", "path": str(target), "data": raw}

    async def normalize(
        self,
        raw_data: Any,
        received_at: datetime,
    ) -> AsyncIterator[Observation]:
        if not isinstance(raw_data, dict):
            return
        fmt = raw_data.get("format")
        if fmt == "geojson":
            async for obs in self._from_geojson(raw_data.get("data"), received_at):
                yield obs
            return
        if fmt == "csv":
            async for obs in self._from_csv(raw_data.get("data") or "", received_at):
                yield obs

    async def _from_geojson(
        self, data: Any, received_at: datetime
    ) -> AsyncIterator[Observation]:
        features = []
        if isinstance(data, dict) and data.get("type") == "FeatureCollection":
            features = data.get("features") or []
        elif isinstance(data, dict) and data.get("type") == "Feature":
            features = [data]
        for feature in features:
            props = feature.get("properties") or {}
            geom = feature.get("geometry") or {}
            coords = geom.get("coordinates") or []
            if geom.get("type") != "Point" or len(coords) < 2:
                continue
            mmsi = props.get("MMSI") or props.get("mmsi") or feature.get("id")
            if not mmsi:
                continue
            observed_at = self._parse_time(
                props.get("BaseDateTime")
                or props.get("basedatetime")
                or props.get("timestamp"),
                received_at,
            )
            yield Observation(
                entity_id=f"mmsi:{mmsi}",
                entity_type="vessel",
                source_id="ais_file",
                source_record_id=str(mmsi),
                observed_at=observed_at,
                received_at=received_at,
                position=GeoPoint(lon=float(coords[0]), lat=float(coords[1])),
                speed_mps=self._sog_to_mps(props.get("SOG") or props.get("sog")),
                heading_deg=self._float_or_none(props.get("COG") or props.get("cog")),
                attributes={
                    "vessel_name": props.get("VesselName") or props.get("name"),
                    "imo": props.get("IMO"),
                    "callsign": props.get("CallSign"),
                    "vessel_type": props.get("VesselType"),
                    "status": props.get("Status"),
                    "length": props.get("Length"),
                    "width": props.get("Width"),
                    "draft": props.get("Draft"),
                },
                provenance={
                    "source_id": "ais_file",
                    "adapter": self.__class__.__name__,
                    "dataset": "geojson",
                },
                raw_payload=feature,
            )

    async def _from_csv(
        self, text: str, received_at: datetime
    ) -> AsyncIterator[Observation]:
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            # Normalizar claves
            lower = { (k or "").strip().lower(): v for k, v in row.items() }
            mmsi = lower.get("mmsi") or row.get("MMSI")
            lat = lower.get("lat") or lower.get("latitude") or row.get("LAT")
            lon = lower.get("lon") or lower.get("longitude") or lower.get("lng") or row.get("LON")
            if not mmsi or lat is None or lon is None or lat == "" or lon == "":
                continue
            try:
                lat_f, lon_f = float(lat), float(lon)
            except (TypeError, ValueError):
                continue
            observed_at = self._parse_time(
                lower.get("basedatetime")
                or lower.get("base_date_time")
                or lower.get("timestamp")
                or row.get("BaseDateTime"),
                received_at,
            )
            yield Observation(
                entity_id=f"mmsi:{mmsi}",
                entity_type="vessel",
                source_id="ais_file",
                source_record_id=str(mmsi),
                observed_at=observed_at,
                received_at=received_at,
                position=GeoPoint(lon=lon_f, lat=lat_f),
                speed_mps=self._sog_to_mps(lower.get("sog") or row.get("SOG")),
                heading_deg=self._float_or_none(lower.get("cog") or row.get("COG")),
                attributes={
                    "vessel_name": lower.get("vesselname") or row.get("VesselName"),
                    "imo": lower.get("imo") or row.get("IMO"),
                    "callsign": lower.get("callsign") or row.get("CallSign"),
                    "vessel_type": lower.get("vesseltype") or row.get("VesselType"),
                    "status": lower.get("status") or row.get("Status"),
                },
                provenance={
                    "source_id": "ais_file",
                    "adapter": self.__class__.__name__,
                    "dataset": "csv",
                },
                raw_payload=row,
            )

    @staticmethod
    def _parse_time(value: Any, fallback: datetime) -> datetime:
        if not value:
            return fallback
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(
                    value / 1000 if value > 1e12 else value, tz=timezone.utc
                )
            except (OSError, ValueError, OverflowError):
                return fallback
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                try:
                    return datetime.strptime(str(value), fmt).replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
        return fallback

    @staticmethod
    def _sog_to_mps(value: Any) -> float | None:
        try:
            # SOG en nudos
            return float(value) * 0.514444
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
