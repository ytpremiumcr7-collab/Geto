"""Origin-based CSRF guard for HttpOnly browser sessions.

Bearer tokens and API keys are explicit request credentials and are not subject to
this browser-cookie guard. Cookie-authenticated unsafe HTTP methods are accepted
only from an explicitly allowed production/staging Origin.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings
from app.core.security_bootstrap import cors_origin_list

_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_PROD_ENVS = frozenset({"production", "prod", "staging"})


def browser_cookie_mutation_allowed(request: Request) -> bool:
    if request.method.upper() not in _UNSAFE_METHODS:
        return True
    if not settings.auth_cookie_mode:
        return True

    # If an explicit credential is supplied, get_current_principal will prefer it
    # over the cookie. This guard is specifically for ambient browser credentials.
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

    origin = (request.headers.get("origin") or "").strip()
    if not origin:
        return False
    return origin in cors_origin_list(settings)


class CookieCsrfMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not browser_cookie_mutation_allowed(request):
            return JSONResponse(
                {
                    "detail": {
                        "error": "csrf_origin_denied",
                        "message": "Cookie-authenticated state changes require an allowed Origin.",
                    }
                },
                status_code=403,
            )
        return await call_next(request)
