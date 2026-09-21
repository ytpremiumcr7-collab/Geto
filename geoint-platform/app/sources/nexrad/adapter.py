"""NOAA NEXRAD Level II — índice de volúmenes en AWS Open Data (sin API de pago).

Lista objetos recientes en s3://noaa-nexrad-level2 vía HTTP público de AWS.
No descarga el binario completo por defecto (solo metadatos de scan → Observation).
Atribución: NOAA NEXRAD.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from xml.etree import ElementTree

import httpx

from app.core.config import settings
from app.domain.models import GeoPoint, Observation
from app.sources.base import SourceAdapter, SourceMetadata

# Subconjunto de sitios NEXRAD (lat, lon) — ampliación trivial desde catálogo NOAA
NEXRAD_SITES: dict[str, tuple[float, float]] = {
    "KTLX": (35.333, -97.278),  # Oklahoma City
    "KEVX": (30.565, -85.922),
    "KJAX": (30.485, -81.702),
    "KLSX": (32.317, -106.823),
    "KMKX": (42.968, -88.551),
    "KOKX": (40.866, -72.864),
    "KDIX": (39.947, -74.411),
    "KLOT": (41.604, -88.085),
    "KFTG": (39.786, -104.546),
    "KATX": (48.194, -122.496),
}

S3_LIST = "https://noaa-nexrad-level2.s3.amazonaws.com"


class NEXRADAdapter(SourceAdapter):
    metadata = SourceMetadata(
        source_id="nexrad",
        source_type="radar",
        description="NOAA NEXRAD Level II volume index (AWS Open Data)",
        endpoint=S3_LIST,
        authentication="none",
        license_name="NOAA NEXRAD — public domain / open data (attribution requested)",
        commercial_allowed=True,
        attribution_required=True,
        access_policy="operator",
        commercial_status="allowed",
        retention="transient",
    )

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.get(S3_LIST, params={"list-type": "2", "max-keys": "1"})
                return r.is_success
        except Exception:
            return False

    async def fetch(
        self,
        site: str | None = None,
        max_keys: int = 20,
        **kwargs: Any,
    ) -> Any:
        """Lista claves S3 recientes para un sitio (default KTLX o settings)."""
        self._reject_unexpected_fetch_kwargs(kwargs)
        site = (site or getattr(settings, "nexrad_default_site", "KTLX")).upper()
        now = datetime.now(UTC)
        # Prefijo típico: YYYY/MM/DD/SITE
        prefix = f"{now:%Y/%m/%d}/{site}/"
        async with httpx.AsyncClient(timeout=45) as client:
            r = await client.get(
                S3_LIST,
                params={
                    "list-type": "2",
                    "prefix": prefix,
                    "max-keys": str(max_keys),
                },
            )
            r.raise_for_status()
            return {"site": site, "prefix": prefix, "xml": r.text}

    async def normalize(
        self,
        raw_data: Any,
        received_at: datetime,
    ) -> AsyncIterator[Observation]:
        if not isinstance(raw_data, dict):
            return
        site = raw_data.get("site", "KTLX")
        xml_text = raw_data.get("xml") or ""
        lat, lon = NEXRAD_SITES.get(site, (None, None))
        keys = self._parse_s3_keys(xml_text)
        for key in keys:
            # Nombre tipo: KTLX20240101_000000_V06
            observed_at = self._time_from_key(key) or received_at
            yield Observation(
                entity_id=f"nexrad:{site}",
                entity_type="radar_site",
                source_id="nexrad",
                source_record_id=key,
                observed_at=observed_at,
                received_at=received_at,
                position=(
                    GeoPoint(lon=lon, lat=lat) if lat is not None and lon is not None else None
                ),
                attributes={
                    "site": site,
                    "s3_key": key,
                    "product": "Level2",
                    "uri": f"s3://noaa-nexrad-level2/{key}",
                },
                provenance={
                    "source_id": "nexrad",
                    "adapter": self.__class__.__name__,
                    "attribution": "NOAA NEXRAD",
                },
                raw_payload={"key": key, "site": site},
            )

    @staticmethod
    def _parse_s3_keys(xml_text: str) -> list[str]:
        keys: list[str] = []
        try:
            root = ElementTree.fromstring(xml_text)
            # Namespace AWS S3
            for el in root.iter():
                if el.tag.endswith("Key") and el.text:
                    keys.append(el.text)
        except ElementTree.ParseError:
            for m in re.finditer(r"<Key>([^<]+)</Key>", xml_text):
                keys.append(m.group(1))
        return keys

    @staticmethod
    def _time_from_key(key: str) -> datetime | None:
        # .../KTLX20240615_123456_V06
        m = re.search(r"(\d{8})_(\d{6})", key)
        if not m:
            return None
        try:
            return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").replace(tzinfo=UTC)
        except ValueError:
            return None
