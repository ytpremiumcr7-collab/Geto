"""DEM asset catalog — PostgreSQL metadata (rasters live in MinIO)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class DemRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        *,
        tenant_id: str,
        provider: str,
        product_name: str,
        product_type: str,
        resolution_m: float,
        crs: str,
        vertical_datum: str | None,
        bbox_west: float,
        bbox_south: float,
        bbox_east: float,
        bbox_north: float,
        file_uri: str,
        checksum_sha256: str | None = None,
        source_version: str | None = None,
        acquisition_date: str | None = None,
        byte_size: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        dem_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        await self.session.execute(
            text(
                """
                INSERT INTO dem_assets (
                    id, tenant_id, provider, product_name, product_type,
                    resolution_m, crs, vertical_datum,
                    bbox_west, bbox_south, bbox_east, bbox_north,
                    file_uri, checksum_sha256, source_version, acquisition_date,
                    byte_size, extra, created_at
                ) VALUES (
                    :id, :tenant_id, :provider, :product_name, :product_type,
                    :resolution_m, :crs, :vertical_datum,
                    :bbox_west, :bbox_south, :bbox_east, :bbox_north,
                    :file_uri, :checksum, :source_version, :acquisition_date,
                    :byte_size, CAST(:extra AS jsonb), :created_at
                )
                """
            ),
            {
                "id": dem_id,
                "tenant_id": tenant_id,
                "provider": provider,
                "product_name": product_name,
                "product_type": product_type,
                "resolution_m": resolution_m,
                "crs": crs,
                "vertical_datum": vertical_datum,
                "bbox_west": bbox_west,
                "bbox_south": bbox_south,
                "bbox_east": bbox_east,
                "bbox_north": bbox_north,
                "file_uri": file_uri,
                "checksum": checksum_sha256,
                "source_version": source_version,
                "acquisition_date": acquisition_date,
                "byte_size": byte_size,
                "extra": __import__("json").dumps(extra or {}),
                "created_at": now,
            },
        )
        await self.session.commit()
        return await self.get(dem_id, tenant_id)  # type: ignore

    async def get(self, dem_id: str, tenant_id: str) -> dict[str, Any] | None:
        row = (
            await self.session.execute(
                text(
                    """
                    SELECT id, tenant_id, provider, product_name, product_type,
                           resolution_m, crs, vertical_datum,
                           bbox_west, bbox_south, bbox_east, bbox_north,
                           file_uri, checksum_sha256, source_version,
                           acquisition_date, byte_size, extra, created_at
                    FROM dem_assets
                    WHERE id = :id AND tenant_id = :tenant_id
                    """
                ),
                {"id": dem_id, "tenant_id": tenant_id},
            )
        ).mappings().first()
        return dict(row) if row else None

    async def find_covering(
        self,
        tenant_id: str,
        lon: float,
        lat: float,
        preferred_provider: str | None = None,
    ) -> dict[str, Any] | None:
        params: dict[str, Any] = {
            "tenant_id": tenant_id,
            "lon": lon,
            "lat": lat,
        }
        provider_clause = ""
        if preferred_provider:
            provider_clause = "AND provider = :provider"
            params["provider"] = preferred_provider
        row = (
            await self.session.execute(
                text(
                    f"""
                    SELECT id, tenant_id, provider, product_name, product_type,
                           resolution_m, crs, vertical_datum,
                           bbox_west, bbox_south, bbox_east, bbox_north,
                           file_uri, checksum_sha256, source_version,
                           acquisition_date, byte_size, extra, created_at
                    FROM dem_assets
                    WHERE tenant_id = :tenant_id
                      AND bbox_west <= :lon AND bbox_east >= :lon
                      AND bbox_south <= :lat AND bbox_north >= :lat
                      {provider_clause}
                    ORDER BY resolution_m ASC NULLS LAST
                    LIMIT 1
                    """
                ),
                params,
            )
        ).mappings().first()
        return dict(row) if row else None

    async def list_assets(
        self, tenant_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        rows = (
            await self.session.execute(
                text(
                    """
                    SELECT id, tenant_id, provider, product_name, product_type,
                           resolution_m, crs, vertical_datum,
                           bbox_west, bbox_south, bbox_east, bbox_north,
                           file_uri, checksum_sha256, source_version,
                           acquisition_date, byte_size, extra, created_at
                    FROM dem_assets
                    WHERE tenant_id = :tenant_id
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                {"tenant_id": tenant_id, "limit": limit},
            )
        ).mappings().all()
        return [dict(r) for r in rows]
