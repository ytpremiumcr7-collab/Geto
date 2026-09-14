"""WebSocket multi-tenant.

Auth (in order):
1. Header Authorization: Bearer <jwt>
2. First JSON message {"type":"auth","token":"..."}
3. Query ?token= (deprecated; proxy logs may retain it)
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.auth.jwt import JWTService
from app.realtime.manager import manager

router = APIRouter(tags=["realtime"])
log = structlog.get_logger()


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
    client = websocket.client.host if websocket.client else "unknown"
    auth_mode = "none"

    if token:
        auth_mode = "header_or_query"
        try:
            principal = JWTService().decode(token)
        except Exception as e:
            log.warning(
                "ws_auth_failed",
                mode=auth_mode,
                client=client,
                error_type=type(e).__name__,
                error=str(e)[:200],
            )
            await websocket.close(code=4401)
            return
        await websocket.accept()
    else:
        auth_mode = "first_message"
        await websocket.accept()
        try:
            first = await websocket.receive_json()
        except Exception as e:
            log.warning(
                "ws_auth_first_message_failed",
                client=client,
                error_type=type(e).__name__,
                error=str(e)[:200],
            )
            await websocket.close(code=4401)
            return
        if not isinstance(first, dict) or first.get("type") != "auth" or not first.get("token"):
            log.warning("ws_auth_missing_token_message", client=client)
            await websocket.close(code=4401)
            return
        try:
            principal = JWTService().decode(str(first["token"]))
        except Exception as e:
            log.warning(
                "ws_auth_token_invalid",
                client=client,
                error_type=type(e).__name__,
                error=str(e)[:200],
            )
            await websocket.close(code=4401)
            return
        await websocket.send_json({"type": "auth_ok", "tenant_id": principal.tenant_id})

    tenant_id = principal.tenant_id
    user_id = principal.user_id
    await manager.connect(tenant_id, websocket)
    log.info(
        "ws_connected",
        tenant_id=tenant_id,
        user_id=user_id,
        client=client,
        auth_mode=auth_mode,
    )

    try:
        while True:
            data = await websocket.receive_json()
            if isinstance(data, dict) and data.get("type") == "auth":
                continue
            await websocket.send_json({"type": "ack", "request": data})
    except WebSocketDisconnect as e:
        log.info(
            "ws_disconnected",
            tenant_id=tenant_id,
            user_id=user_id,
            client=client,
            code=getattr(e, "code", None),
            reason=(getattr(e, "reason", None) or "")[:200] or None,
        )
    except Exception as e:
        log.exception(
            "ws_error",
            tenant_id=tenant_id,
            user_id=user_id,
            client=client,
            error_type=type(e).__name__,
            error=str(e)[:300],
        )
    finally:
        await manager.disconnect(tenant_id, websocket)
        log.info("ws_cleaned_up", tenant_id=tenant_id, user_id=user_id, client=client)
