"""JPL Horizons (API pública) — efemérides / vectores.

Documentación: https://ssd-api.jpl.nasa.gov/doc/horizons.html
Sin API key. Uso razonable; no martillar el endpoint.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

import httpx

from app.core.config import settings
from app.domain.models import Observation
from app.sources.base import SourceAdapter, SourceMetadata


class JPLHorizonsAdapter(SourceAdapter):
    metadata = SourceMetadata(
        source_id="jpl_horizons",
        source_type="ephemeris",
        description="JPL Horizons ephemerides (public SSD API)",
        endpoint="https://ssd.jpl.nasa.gov/api/horizons.api",
        authentication="none",
        license_name="NASA/JPL public data",
        commercial_allowed=True,
        attribution_required=True,
        access_policy="operator",
        commercial_status="allowed",
        retention="standard",
    )

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                # COMMAND='MB' lista cuerpos menores — respuesta corta de prueba
                r = await client.get(
                    settings.horizons_base_url,
                    params={
                        "format": "json",
                        "COMMAND": "'1'",
                        "OBJ_DATA": "YES",
                        "MAKE_EPHEM": "NO",
                    },
                )
                return r.is_success
        except Exception:
            return False

    async def fetch(
        self,
        command: str | None = None,
        center: str = "500@399",
        start: str | None = None,
        stop: str | None = None,
        step: str = "1d",
            **kwargs: Any,
) -> Any:
        """command: id Horizons, p.ej. '399' Tierra, '301' Luna, '199' Mercurio."""
        self._reject_unexpected_fetch_kwargs(kwargs)
        cmd = command or getattr(settings, "horizons_default_command", "399")
        params = {
            "format": "json",
            "COMMAND": f"'{cmd}'",
            "OBJ_DATA": "YES",
            "MAKE_EPHEM": "YES",
            "EPHEM_TYPE": "VECTORS",
            "CENTER": f"'{center}'",
            "START_TIME": f"'{start or '2024-01-01'}'",
            "STOP_TIME": f"'{stop or '2024-01-02'}'",
            "STEP_SIZE": f"'{step}'",
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(settings.horizons_base_url, params=params)
            response.raise_for_status()
            return response.json()

    async def normalize(
        self,
        raw_data: Any,
        received_at: datetime,
    ) -> AsyncIterator[Observation]:
        if not isinstance(raw_data, dict):
            return
        result = raw_data.get("result") or ""
        # Parseo mínimo del bloque de texto Horizons (líneas de vectores)
        entity = "horizons:body"
        for line in str(result).splitlines():
            if "Target body name:" in line:
                entity = f"horizons:{line.split('Target body name:')[-1].strip().split()[0]}"
                break

        # Sin posición geo en VECTORS heliocéntricos/geocéntricos: guardamos atributos
        yield Observation(
            entity_id=entity.lower().replace(" ", "_"),
            entity_type="celestial_body",
            source_id="jpl_horizons",
            source_record_id=entity,
            observed_at=received_at,
            received_at=received_at,
            position=None,
            attributes={
                "signature": (raw_data.get("signature") or {}),
                "result_excerpt": str(result)[:2000],
            },
            provenance={
                "source_id": "jpl_horizons",
                "adapter": self.__class__.__name__,
            },
            raw_payload={"signature": raw_data.get("signature")},
        )
