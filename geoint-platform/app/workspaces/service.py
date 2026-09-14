from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.workspaces.models import SavedLayer, Workspace


def _ws_dict(w: Workspace) -> dict[str, Any]:
    return {
        "id": str(w.id),
        "name": w.name,
        "description": w.description,
        "is_default": w.is_default,
        "owner_user_id": w.owner_user_id,
        "aoi_geojson": w.aoi_geojson,
        "map_center_lon": w.map_center_lon,
        "map_center_lat": w.map_center_lat,
        "map_zoom": w.map_zoom,
        "settings": w.settings or {},
        "created_at": w.created_at.isoformat() if w.created_at else None,
        "updated_at": w.updated_at.isoformat() if w.updated_at else None,
    }


def _layer_dict(layer: SavedLayer) -> dict[str, Any]:
    return {
        "id": str(layer.id),
        "workspace_id": str(layer.workspace_id),
        "name": layer.name,
        "layer_type": layer.layer_type,
        "config": layer.config or {},
        "visible": layer.visible,
        "sort_order": layer.sort_order,
        "style": layer.style or {},
    }


class WorkspaceService:
    async def list_workspaces(self, session: AsyncSession, tenant_id: str) -> list[dict[str, Any]]:
        result = await session.execute(
            select(Workspace).where(Workspace.tenant_id == tenant_id).order_by(Workspace.name)
        )
        return [_ws_dict(w) for w in result.scalars().all()]

    async def get(
        self, session: AsyncSession, tenant_id: str, workspace_id: uuid.UUID
    ) -> Workspace | None:
        w = await session.get(Workspace, workspace_id)
        if w is None or w.tenant_id != tenant_id:
            return None
        return w

    async def create(
        self,
        session: AsyncSession,
        *,
        tenant_id: str,
        name: str,
        description: str | None = None,
        owner_user_id: str | None = None,
        aoi_geojson: dict | None = None,
        map_center_lon: float | None = None,
        map_center_lat: float | None = None,
        map_zoom: float | None = None,
        is_default: bool = False,
        settings: dict | None = None,
    ) -> dict[str, Any]:
        if is_default:
            await self._clear_default(session, tenant_id)
        w = Workspace(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            name=name,
            description=description,
            owner_user_id=owner_user_id,
            aoi_geojson=aoi_geojson,
            map_center_lon=map_center_lon,
            map_center_lat=map_center_lat,
            map_zoom=map_zoom,
            is_default=is_default,
            settings=settings or {},
        )
        session.add(w)
        await session.commit()
        await session.refresh(w)
        return _ws_dict(w)

    async def update(
        self,
        session: AsyncSession,
        tenant_id: str,
        workspace_id: uuid.UUID,
        **fields: Any,
    ) -> dict[str, Any] | None:
        w = await self.get(session, tenant_id, workspace_id)
        if not w:
            return None
        if fields.get("is_default"):
            await self._clear_default(session, tenant_id)
        for k, v in fields.items():
            if v is not None and hasattr(w, k):
                setattr(w, k, v)
        await session.commit()
        await session.refresh(w)
        return _ws_dict(w)

    async def delete(self, session: AsyncSession, tenant_id: str, workspace_id: uuid.UUID) -> bool:
        w = await self.get(session, tenant_id, workspace_id)
        if not w:
            return False
        await session.delete(w)
        await session.commit()
        return True

    async def list_layers(
        self, session: AsyncSession, tenant_id: str, workspace_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        result = await session.execute(
            select(SavedLayer)
            .where(
                SavedLayer.tenant_id == tenant_id,
                SavedLayer.workspace_id == workspace_id,
            )
            .order_by(SavedLayer.sort_order, SavedLayer.name)
        )
        return [_layer_dict(x) for x in result.scalars().all()]

    async def add_layer(
        self,
        session: AsyncSession,
        *,
        tenant_id: str,
        workspace_id: uuid.UUID,
        name: str,
        layer_type: str,
        config: dict | None = None,
        visible: bool = True,
        sort_order: int = 0,
        style: dict | None = None,
    ) -> dict[str, Any] | None:
        w = await self.get(session, tenant_id, workspace_id)
        if not w:
            return None
        layer = SavedLayer(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            name=name,
            layer_type=layer_type,
            config=config or {},
            visible=visible,
            sort_order=sort_order,
            style=style or {},
        )
        session.add(layer)
        await session.commit()
        await session.refresh(layer)
        return _layer_dict(layer)

    async def _clear_default(self, session: AsyncSession, tenant_id: str) -> None:
        result = await session.execute(
            select(Workspace).where(
                Workspace.tenant_id == tenant_id,
                Workspace.is_default.is_(True),
            )
        )
        for w in result.scalars().all():
            w.is_default = False
