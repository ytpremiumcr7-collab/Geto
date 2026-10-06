"""WebSocket connections scoped by tenant and readable source ids."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Collection

from fastapi import WebSocket


def _payload_source_id(payload: dict) -> str | None:
    direct = payload.get("source_id")
    if direct:
        return str(direct)
    nested = payload.get("payload")
    if isinstance(nested, dict) and nested.get("source_id"):
        return str(nested["source_id"])
    data = payload.get("data")
    if isinstance(data, dict) and data.get("source_id"):
        return str(data["source_id"])
    return None


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, dict[WebSocket, frozenset[str]]] = defaultdict(dict)
        self._lock = asyncio.Lock()

    async def connect(
        self,
        tenant_id: str,
        websocket: WebSocket,
        *,
        allowed_source_ids: Collection[str] | None = None,
    ) -> None:
        """Register an already-accepted socket.

        Protocol acceptance belongs to the route after authentication. Keeping it
        out of the manager prevents duplicate ASGI websocket.accept messages.
        """
        allowed = frozenset(str(item) for item in (allowed_source_ids or []) if str(item))
        async with self._lock:
            self._connections[tenant_id][websocket] = allowed

    async def disconnect(self, tenant_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            conns = self._connections.get(tenant_id)
            if not conns:
                return
            conns.pop(websocket, None)
            if not conns:
                self._connections.pop(tenant_id, None)

    async def publish(self, tenant_id: str, payload: dict) -> None:
        source_id = _payload_source_id(payload)
        async with self._lock:
            targets = list(self._connections.get(tenant_id, {}).items())

        dead: list[WebSocket] = []
        for ws, allowed_sources in targets:
            # Realtime event/alert payloads are source-scoped. Missing provenance
            # is denied rather than broadcast to every tenant socket.
            if not source_id or source_id not in allowed_sources:
                continue
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(tenant_id, ws)


manager = ConnectionManager()
