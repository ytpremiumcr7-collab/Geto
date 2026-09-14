"""API GEOINT — health público; datos protegidos por JWT/API key."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from app.middleware.rate_limit_mw import RateLimitMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.routes.entities import router as entities_router
from app.api.routes.events import router as events_router
from app.api.routes.geofences import router as geofences_router
from app.api.routes.dlq import router as dlq_router
from app.api.routes.websocket import router as websocket_router
from app.api.routes.topography import router as topography_router
from app.api.routes.health import router as health_router
from app.api.routes.observations import router as observations_router
from app.api.routes.sources import router as sources_router
from app.auth.router import router as auth_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.telemetry import setup_opentelemetry

configure_logging(settings.log_level)
setup_opentelemetry(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    bridge = None
    task = None
    if settings.app_env not in ("test",):
        try:
            from app.realtime.nats_bridge import RealtimeNatsBridge
            bridge = RealtimeNatsBridge()
            task = asyncio.create_task(bridge.start())
        except Exception:
            bridge = None
    yield
    if bridge:
        bridge.stop()
        if task:
            task.cancel()
            try:
                await task
            except Exception:
                pass
            await bridge.close()


app = FastAPI(
    title=settings.app_name,
    version="2.1.0",
    lifespan=lifespan,
)
app.add_middleware(RateLimitMiddleware)

if settings.app_env in ("development", "dev", "test"):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(sources_router)
app.include_router(observations_router)
app.include_router(entities_router)
app.include_router(events_router)
app.include_router(geofences_router)
app.include_router(dlq_router)
app.include_router(websocket_router)
app.include_router(topography_router)


@app.get("/metrics")
async def metrics(request: Request):
    if not settings.prometheus_enabled:
        return Response(status_code=404)
    if not getattr(settings, "metrics_public", False):
        auth = request.headers.get("authorization") or request.headers.get("x-api-key")
        if not auth:
            return Response(status_code=401, content=b"Unauthorized")
        # Validate via JWTService / API key when present
        try:
            from app.auth.dependencies import get_current_principal
            from app.auth.jwt import JWTService
            if auth.lower().startswith("bearer "):
                JWTService().decode(auth.split(" ", 1)[1])
            else:
                from app.auth.dependencies import _api_key_principal
                if not _api_key_principal(auth):
                    return Response(status_code=401, content=b"Unauthorized")
        except Exception:
            return Response(status_code=401, content=b"Unauthorized")
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
