from fastapi import APIRouter
from sqlalchemy import text

from app.db.session import engine
from app.infrastructure.nats_bus import EventBus
from app.infrastructure.object_store import ObjectStore

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def liveness():
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness():
    result = {
        "status": "ok",
        "postgres": False,
        "nats": False,
        "minio": False,
    }

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

        result["postgres"] = True
    except Exception:
        pass

    try:
        bus = EventBus()
        await bus.connect()
        result["nats"] = True
        await bus.close()
    except Exception:
        pass

    try:
        ObjectStore().ensure_bucket()
        result["minio"] = True
    except Exception:
        pass

    result["status"] = (
        "ok"
        if all(
            [
                result["postgres"],
                result["nats"],
                result["minio"],
            ]
        )
        else "degraded"
    )

    return result


@router.get("/health/version")
async def version():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    ver = "2.3.0"
    vf = root.parent / "VERSION"
    if not vf.exists():
        vf = root / "VERSION"
    if vf.exists():
        ver = vf.read_text().strip() or ver
    return {"version": ver, "product": "geoint-platform"}
