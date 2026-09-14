"""WebSocket multi-tenant.

Auth preferida (en orden):
1. Header Authorization: Bearer <jwt>
2. Primer mensaje JSON {"type":"auth","token":"..."}
3. Query ?token= (deprecado; logs de proxy pueden filtrarlo)
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.auth.jwt import JWTService
from app.realtime.manager import manager

router = APIRouter(tags=["realtime"])


def _token_from_header(websocket: WebSocket) -> str | None:
    auth = websocket.headers.get("authorization") or websocket.headers.get("Authorization")
    if not auth:
        return None
    parts = auth.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


@router.websocket("/ws/events")
async def events_websocket(websocket: WebSocket):
    token = _token_from_header(websocket) or websocket.query_params.get("token")
    principal = None

    if token:
        try:
            principal = JWTService().decode(token)
        except Exception:
            await websocket.close(code=4401)
            return
        await websocket.accept()
    else:
        # Auth por primer mensaje
        await websocket.accept()
        try:
            first = await websocket.receive_json()
        except Exception:
            await websocket.close(code=4401)
            return
        if not isinstance(first, dict) or first.get("type") != "auth" or not first.get("token"):
            await websocket.close(code=4401)
            return
        try:
            principal = JWTService().decode(str(first["token"]))
        except Exception:
            await websocket.close(code=4401)
            return
        await websocket.send_json({"type": "auth_ok", "tenant_id": principal.tenant_id})

    tenant_id = principal.tenant_id
    await manager.connect(tenant_id, websocket)

    try:
        while True:
            data = await websocket.receive_json()
            if isinstance(data, dict) and data.get("type") == "auth":
                continue  # ignore re-auth
            await websocket.send_json({"type": "ack", "request": data})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await manager.disconnect(tenant_id, websocket)
