"""Middleware rate limit global por IP (Redis, fail-open)."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings
from app.infrastructure.rate_limit import check_rate_limit


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not getattr(settings, "rate_limit_enabled", True):
            return await call_next(request)
        path = request.url.path
        if path.startswith("/health"):
            return await call_next(request)
        client = request.client.host if request.client else "unknown"
        limit = int(getattr(settings, "rate_limit_per_minute", 120) or 120)
        ok = await check_rate_limit(f"api:{client}", limit=limit, window_seconds=60)
        if not ok:
            return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
        return await call_next(request)
