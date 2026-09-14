"""Liveness / readiness with explicit dependency errors (no silent swallow)."""

from __future__ import annotations

import time

import structlog
from fastapi import APIRouter
from sqlalchemy import text

from app.db.session import engine
from app.infrastructure.nats_bus import EventBus
from app.infrastructure.object_store import ObjectStore

router = APIRouter(tags=["health"])
log = structlog.get_logger()


@router.get("/health/live")
async def liveness():
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness():
    """Readiness: each dependency checked; failures recorded in errors[].

    status:
      - ok: all required deps healthy
      - degraded: at least one required dep failed (still returns 200 so
        orchestrators can inspect body; use /health/live for pure liveness)
    """
    checks: dict[str, bool] = {
        "postgres": False,
        "nats": False,
        "minio": False,
    }
    errors: list[dict[str, str]] = []
    timings_ms: dict[str, float] = {}

    # Postgres
    t0 = time.perf_counter()
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["postgres"] = True
    except Exception as e:
        log.warning("health_postgres_failed", error=str(e))
        errors.append(
            {
                "component": "postgres",
                "error_type": type(e).__name__,
                "message": str(e)[:500],
            }
        )
    timings_ms["postgres"] = round((time.perf_counter() - t0) * 1000, 1)

    # NATS
    t0 = time.perf_counter()
    bus: EventBus | None = None
    try:
        bus = EventBus()
        await bus.connect()
        checks["nats"] = True
    except Exception as e:
        log.warning("health_nats_failed", error=str(e))
        errors.append(
            {
                "component": "nats",
                "error_type": type(e).__name__,
                "message": str(e)[:500],
            }
        )
    finally:
        if bus is not None:
            try:
                await bus.close()
            except Exception as e:
                log.warning("health_nats_close_failed", error=str(e))
                errors.append(
                    {
                        "component": "nats_close",
                        "error_type": type(e).__name__,
                        "message": str(e)[:300],
                    }
                )
    timings_ms["nats"] = round((time.perf_counter() - t0) * 1000, 1)

    # MinIO
    t0 = time.perf_counter()
    try:
        ObjectStore().ensure_bucket()
        checks["minio"] = True
    except Exception as e:
        log.warning("health_minio_failed", error=str(e))
        errors.append(
            {
                "component": "minio",
                "error_type": type(e).__name__,
                "message": str(e)[:500],
            }
        )
    timings_ms["minio"] = round((time.perf_counter() - t0) * 1000, 1)

    all_ok = all(checks.values())
    return {
        "status": "ok" if all_ok else "degraded",
        **checks,
        "errors": errors,
        "timings_ms": timings_ms,
    }


@router.get("/health/version")
async def version():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    ver = "0.0.0"
    vf = root.parent / "VERSION"
    if not vf.exists():
        vf = root / "VERSION"
    if vf.exists():
        ver = vf.read_text().strip() or ver
    return {"version": ver, "product": "geoint-platform"}
