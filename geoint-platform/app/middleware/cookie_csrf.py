"""CSRF guard for HttpOnly browser sessions.

Unsafe cookie-authenticated requests use Fetch Metadata when present and fall
back to exact Origin/Referer verification. Bearer tokens and API keys are
explicit credentials and do not rely on ambient browser cookies.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings
from app.core.security_bootstrap import cors_origin_list

_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_PROD_ENVS = frozenset({"production", "prod", "staging"})


def _origin_from_referer(value: str) -> str | None:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def browser_cookie_mutation_allowed(request: Request) -> bool:
    if request.method.upper() not in _UNSAFE_METHODS:
        return True
    if not settings.auth_cookie_mode:
        return True

    # Explicit request credentials are handled independently by authentication.
    auth = (request.headers.get("authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return True
    if (request.headers.get("x-api-key") or "").strip():
        return True

    cookie_name = settings.auth_cookie_name or "geoint_access"
    if not request.cookies.get(cookie_name):
        return True

    env = (settings.app_env or "development").strip().lower()
    if env not in _PROD_ENVS:
        return True

    fetch_site = (request.headers.get("sec-fetch-site") or "").strip().lower()
    if fetch_site == "cross-site":
        return False
    if fetch_site == "same-origin":
        return True

    allowed_origins = set(cors_origin_list(settings))
    origin = (request.headers.get("origin") or "").strip()
    if origin:
        return origin in allowed_origins

    referer = (request.headers.get("referer") or "").strip()
    referer_origin = _origin_from_referer(referer) if referer else None
    if referer_origin:
        return referer_origin in allowed_origins

    # Production cookie writes fail closed when browser provenance is absent.
    return False


class CookieCsrfMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not browser_cookie_mutation_allowed(request):
            return JSONResponse(
                {
                    "detail": {
                        "error": "csrf_origin_denied",
                        "message": (
                            "Cookie-authenticated state changes require trusted "
                            "browser request provenance."
                        ),
                    }
                },
                status_code=403,
            )
        return await call_next(request)
