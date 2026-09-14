"""WebSocket connections por tenant_id (memoria local por instancia API)."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from uuid import UUID

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, tenant_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[tenant_id].add(websocket)

    async def disconnect(self, tenant_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            conns = self._connections.get(tenant_id)
            if not conns:
                return
            conns.discard(websocket)
            if not conns:
                self._connections.pop(tenant_id, None)

    async def publish(self, tenant_id: str, payload: dict) -> None:
        async with self._lock:
            targets = list(self._connections.get(tenant_id, set()))
        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(tenant_id, ws)


manager = ConnectionManager()
