"""Middleware rate limit global por IP (Redis).

Uses the left-most X-Forwarded-For hop when present (behind a trusted proxy).
Also keys by Authorization subject hash when available to reduce shared-NAT collision.
"""

from __future__ import annotations

import hashlib

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings
from app.infrastructure.rate_limit import check_rate_limit


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
    if xff:
        # leftmost = original client when proxy appends
        return xff.split(",")[0].strip() or "unknown"
    if request.client:
        return request.client.host or "unknown"
    return "unknown"


def _identity_suffix(request: Request) -> str:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer ") and len(auth) > 20:
        return hashlib.sha256(auth.encode()).hexdigest()[:16]
    api_key = request.headers.get("x-api-key") or ""
    if api_key:
        return hashlib.sha256(api_key.encode()).hexdigest()[:16]
    return "anon"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not getattr(settings, "rate_limit_enabled", True):
            return await call_next(request)
        path = request.url.path
        if path.startswith("/health"):
            return await call_next(request)
        client = _client_ip(request)
        ident = _identity_suffix(request)
        limit = int(getattr(settings, "rate_limit_per_minute", 120) or 120)
        ok = await check_rate_limit(
            f"api:{client}:{ident}",
            limit=limit,
            window_seconds=60,
        )
        if not ok:
            return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
        return await call_next(request)
