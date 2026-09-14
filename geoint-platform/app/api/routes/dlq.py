from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_roles
from app.auth.models import Principal
from app.db.models_dlq import DlqMessage
from app.db.session import get_db
from app.db.tenant import set_tenant
from app.messaging.jetstream import JetStreamClient
from app.messaging.subjects import JOBS_PREFIX

router = APIRouter(prefix="/api/v1/admin/dlq", tags=["dlq"])


@router.get("")
async def list_dlq(
    status: str = Query("open"),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_roles("admin")),
):
    await set_tenant(db, principal.tenant_id)
    stmt = (
        select(DlqMessage)
        .where(
            DlqMessage.tenant_id == principal.tenant_id,
            DlqMessage.status == status,
        )
        .order_by(DlqMessage.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return {
        "items": [
            {
                "id": str(r.id),
                "source_id": r.source_id,
                "error": r.error,
                "delivery_count": r.delivery_count,
                "status": r.status,
                "created_at": r.created_at.isoformat(),
                "payload": r.payload,
            }
            for r in rows
        ]
    }


@router.post("/{message_id}/requeue")
async def requeue_dlq(
    message_id: UUID,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_roles("admin")),
):
    await set_tenant(db, principal.tenant_id)
    msg = await db.get(DlqMessage, message_id)
    if not msg or msg.tenant_id != principal.tenant_id:
        raise HTTPException(status_code=404, detail="DLQ message not found")
    if msg.status != "open":
        raise HTTPException(status_code=400, detail="Message not open")

    js = JetStreamClient()
    await js.connect()
    try:
        payload = msg.payload if isinstance(msg.payload, dict) else {}
        source_id = msg.source_id
        # Re-publicar como job si tiene job_id
        if payload.get("job_id"):
            await js.publish_job(
                job_id=UUID(str(payload["job_id"])),
                source_id=source_id,
                job_type=payload.get("job_type", "poll"),
                config=payload.get("config") or {},
            )
        else:
            assert js.js is not None
            import json

            await js.js.publish(
                f"{JOBS_PREFIX}.{source_id}",
                json.dumps(payload, default=str).encode(),
            )
    finally:
        await js.close()

    msg.status = "requeued"
    msg.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    return {"id": str(message_id), "status": "requeued"}


@router.post("/{message_id}/resolve")
async def resolve_dlq(
    message_id: UUID,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_roles("admin")),
):
    await set_tenant(db, principal.tenant_id)
    msg = await db.get(DlqMessage, message_id)
    if not msg or msg.tenant_id != principal.tenant_id:
        raise HTTPException(status_code=404, detail="DLQ message not found")
    msg.status = "resolved"
    msg.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    return {"id": str(message_id), "status": "resolved"}
