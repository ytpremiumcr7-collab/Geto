"""Liveness / readiness with explicit dependency errors (no silent swallow)."""

from __future__ import annotations

import asyncio
import time
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version

import redis.asyncio as redis_async
import structlog
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.analytics.clickhouse import ClickHouseClient
from app.core.config import settings
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
      - ok: all required deps healthy (HTTP 200)
      - degraded: at least one required dep failed (HTTP 503)
    """
    checks: dict[str, bool] = {
        "postgres": False,
        "redis": False,
        "nats": False,
        "s3": False,
    }
    if settings.clickhouse_enabled:
        checks["clickhouse"] = False
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

    # Redis is required by production rate limiting and OIDC state.
    t0 = time.perf_counter()
    redis_client = None
    try:
        redis_client = redis_async.from_url(settings.redis_url, decode_responses=True)
        if not await redis_client.ping():
            raise RuntimeError("Redis PING returned a false value")
        checks["redis"] = True
    except Exception as e:
        log.warning("health_redis_failed", error=str(e))
        errors.append(
            {
                "component": "redis",
                "error_type": type(e).__name__,
                "message": str(e)[:500],
            }
        )
    finally:
        if redis_client is not None:
            try:
                await redis_client.aclose()
            except Exception as e:
                log.warning("health_redis_close_failed", error=str(e))
    timings_ms["redis"] = round((time.perf_counter() - t0) * 1000, 1)

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

    # S3 object storage
    t0 = time.perf_counter()
    try:
        await asyncio.to_thread(ObjectStore().ensure_bucket)
        checks["s3"] = True
    except Exception as e:
        log.warning("health_s3_failed", error=str(e))
        errors.append(
            {
                "component": "s3",
                "error_type": type(e).__name__,
                "message": str(e)[:500],
            }
        )
    timings_ms["s3"] = round((time.perf_counter() - t0) * 1000, 1)

    if settings.clickhouse_enabled:
        t0 = time.perf_counter()
        try:
            if not await ClickHouseClient().ping():
                raise RuntimeError("ClickHouse ping failed")
            checks["clickhouse"] = True
        except Exception as e:
            log.warning("health_clickhouse_failed", error=str(e))
            errors.append(
                {
                    "component": "clickhouse",
                    "error_type": type(e).__name__,
                    "message": str(e)[:500],
                }
            )
        timings_ms["clickhouse"] = round((time.perf_counter() - t0) * 1000, 1)

    all_ok = all(checks.values())
    body = {
        "status": "ok" if all_ok else "degraded",
        **checks,
        "errors": errors,
        "timings_ms": timings_ms,
    }
    if not all_ok:
        return JSONResponse(status_code=503, content=body)
    return body


@router.get("/health/version")
async def version():
    try:
        ver = package_version("geoint-platform")
    except PackageNotFoundError:
        # Source-tree fallback for running without installing the package.
        from pathlib import Path

        root = Path(__file__).resolve().parents[3]
        candidates = (root / "VERSION", root.parent / "VERSION")
        ver = next(
            (path.read_text().strip() for path in candidates if path.exists()),
            "unknown",
        )
    return {"version": ver, "product": "geoint-platform"}
