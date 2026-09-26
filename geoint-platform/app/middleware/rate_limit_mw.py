"""Middleware rate limit global por IP (Redis).

Uses the left-most X-Forwarded-For hop when present (behind a trusted proxy).
Also keys by Authorization subject hash when available to reduce shared-NAT collision.
"""

from __future__ import annotations

import hashlib
import ipaddress

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings
from app.infrastructure.rate_limit import check_rate_limit


def _trusted_proxy_networks() -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for raw in (getattr(settings, "trusted_proxy_cidrs", "") or "").split(","):
        value = raw.strip()
        if not value:
            continue
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            continue
    return tuple(networks)


def _client_ip(request: Request) -> str:
    peer = request.client.host if request.client and request.client.host else "unknown"
    try:
        peer_ip = ipaddress.ip_address(peer)
    except ValueError:
        return peer

    trusted = any(peer_ip in network for network in _trusted_proxy_networks())
    if not trusted:
        return peer

    xff = request.headers.get("x-forwarded-for")
    if not xff:
        return peer

    candidate = xff.split(",")[0].strip()
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return peer


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
