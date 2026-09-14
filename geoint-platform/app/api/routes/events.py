from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_principal
from app.auth.models import Principal

router = APIRouter(
    prefix="/api/v1/events",
    tags=["events"],
)


@router.get("")
async def list_events(
    principal: Principal = Depends(get_current_principal),
):
    return {
        "tenant_id": principal.tenant_id,
        "events": [],
        "note": "Events are published through NATS JetStream / outbox.",
    }
