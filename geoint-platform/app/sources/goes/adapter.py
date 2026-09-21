"""NOAA GOES-R (ABI) — índice de productos en AWS Open Data.

Bucket público típico: noaa-goes16 / noaa-goes18.
Lista productos recientes (metadatos); no descarga netCDF completo por defecto.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from xml.etree import ElementTree

import httpx

from app.core.config import settings
from app.domain.models import Observation
from app.sources.base import SourceAdapter, SourceMetadata


class GOESAdapter(SourceAdapter):
    metadata = SourceMetadata(
        source_id="goes",
        source_type="satellite_weather",
        description="NOAA GOES-R ABI product index (AWS Open Data)",
        endpoint="https://noaa-goes16.s3.amazonaws.com",
        authentication="none",
        license_name="NOAA GOES — open data (attribution requested)",
        commercial_allowed=True,
        attribution_required=True,
        access_policy="operator",
        commercial_status="allowed",
        retention="transient",
    )

    def __init__(self) -> None:
        satellite = getattr(settings, "goes_satellite", "goes16")
        self.bucket_url = f"https://noaa-{satellite}.s3.amazonaws.com"
        self.product = getattr(settings, "goes_product", "ABI-L2-CMIPF")

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.get(self.bucket_url, params={"list-type": "2", "max-keys": "1"})
                return r.is_success
        except Exception:
            return False

    async def fetch(
        self,
        product: str | None = None,
        max_keys: int = 15,
            **kwargs: Any,
) -> Any:
        self._reject_unexpected_fetch_kwargs(kwargs)
        product = product or self.product
        now = datetime.now(UTC)
        # Prefijo ABI: Product/year/doy/hour/
        doy = now.timetuple().tm_yday
        prefix = f"{product}/{now:%Y}/{doy:03d}/{now:%H}/"
        async with httpx.AsyncClient(timeout=45) as client:
            r = await client.get(
                self.bucket_url,
                params={
                    "list-type": "2",
                    "prefix": prefix,
                    "max-keys": str(max_keys),
                },
            )
            r.raise_for_status()
            return {
                "product": product,
                "prefix": prefix,
                "bucket_url": self.bucket_url,
                "xml": r.text,
            }

    async def normalize(
        self,
        raw_data: Any,
        received_at: datetime,
    ) -> AsyncIterator[Observation]:
        if not isinstance(raw_data, dict):
            return
        product = raw_data.get("product", self.product)
        xml_text = raw_data.get("xml") or ""
        bucket = raw_data.get("bucket_url", self.bucket_url)
        for key in self._parse_s3_keys(xml_text):
            observed_at = self._time_from_key(key) or received_at
            yield Observation(
                entity_id=f"goes:{product}",
                entity_type="satellite_weather",
                source_id="goes",
                source_record_id=key,
                observed_at=observed_at,
                received_at=received_at,
                position=None,
                attributes={
                    "product": product,
                    "s3_key": key,
                    "uri": f"{bucket}/{key}",
                },
                provenance={
                    "source_id": "goes",
                    "adapter": self.__class__.__name__,
                    "attribution": "NOAA GOES",
                },
                raw_payload={"key": key},
            )

    @staticmethod
    def _parse_s3_keys(xml_text: str) -> list[str]:
        keys: list[str] = []
        try:
            root = ElementTree.fromstring(xml_text)
            for el in root.iter():
                if el.tag.endswith("Key") and el.text:
                    keys.append(el.text)
        except ElementTree.ParseError:
            for m in re.finditer(r"<Key>([^<]+)</Key>", xml_text):
                keys.append(m.group(1))
        return keys

    @staticmethod
    def _time_from_key(key: str) -> datetime | None:
        # _sYYYYDDDHHMMSSs...
        m = re.search(r"_s(\d{4})(\d{3})(\d{2})(\d{2})(\d{2})", key)
        if not m:
            return None
        try:
            year, doy, hh, mm, ss = map(int, m.groups())
            dt = datetime(year, 1, 1, hh, mm, ss, tzinfo=UTC)
            from datetime import timedelta

            return dt + timedelta(days=doy - 1)
        except ValueError:
            return None
