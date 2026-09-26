"""Token issuance + optional HttpOnly session cookie (BFF-friendly)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.auth.jwt import JWTService
from app.auth.oidc import OIDCConfigurationError, OIDCService, OIDCStateError
from app.core.config import settings
from app.infrastructure.rate_limit import check_rate_limit

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class TokenRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    tenant_id: str = Field(min_length=1, max_length=128)
    roles: list[str] = Field(default_factory=lambda: ["operator"])
    bootstrap_secret: str | None = None


class TokenResponse(BaseModel):
    access_token: str | None = None
    token_type: str = "bearer"
    cookie_mode: bool = False
    authenticated: bool = True


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        httponly=True,
        secure=bool(settings.auth_cookie_secure),
        samesite=str(settings.auth_cookie_samesite or "lax").lower(),  # type: ignore[arg-type]
        max_age=int(settings.auth_cookie_max_age or 3600),
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.auth_cookie_name,
        path="/",
        secure=bool(settings.auth_cookie_secure),
        httponly=True,
        samesite=str(settings.auth_cookie_samesite or "lax").lower(),  # type: ignore[arg-type]
    )


@router.get("/oidc/status")
async def oidc_status():
    enabled = bool(
        settings.auth_cookie_mode
        and settings.oidc_client_id
        and settings.oidc_redirect_uri
        and settings.jwt_jwks_url
    )
    return {
        "enabled": enabled,
        "development_bootstrap": settings.app_env in ("development", "dev", "test"),
    }


@router.get("/oidc/start")
async def oidc_start(return_to: str = Query("/", max_length=512)):
    if not settings.auth_cookie_mode:
        raise HTTPException(\n            status_code=503,\n            detail="OIDC browser login requires AUTH_COOKIE_MODE=true",\n        )
    try:
        url = await OIDCService().authorization_url(return_to=return_to)
    except OIDCConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    response = RedirectResponse(url=url, status_code=302)
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/oidc/callback")
async def oidc_callback(code: str = Query(...), state: str = Query(...)):
    if not settings.auth_cookie_mode:
        raise HTTPException(status_code=503, detail="OIDC browser login requires AUTH_COOKIE_MODE=true")
    try:
        token, _principal, return_to = await OIDCService().exchange_callback(
            code=code,
            state=state,
        )
    except OIDCStateError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except OIDCConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="OIDC token exchange failed") from exc

    response = RedirectResponse(url=return_to, status_code=303)
    _set_auth_cookie(response, token)
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("/token", response_model=TokenResponse)
async def issue_token(request: Request, response: Response, body: TokenRequest):
    """Issue JWT. Cookie mode keeps the credential exclusively in the HttpOnly cookie."""
    from app.middleware.rate_limit_mw import _client_ip

    client = _client_ip(request)
    if not await check_rate_limit(f"auth:{client}", limit=20, window_seconds=60):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    if settings.app_env not in ("development", "dev", "test"):
        if (
            not settings.auth_bootstrap_secret
            or body.bootstrap_secret != settings.auth_bootstrap_secret
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Token issuance disabled",
            )
    try:
        token = JWTService().encode(
            user_id=body.user_id,
            tenant_id=body.tenant_id,
            roles=body.roles,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    cookie_mode = bool(getattr(settings, "auth_cookie_mode", False))
    if cookie_mode:
        _set_auth_cookie(response, token)
    return TokenResponse(access_token=None if cookie_mode else token, cookie_mode=cookie_mode)


@router.post("/logout")
async def logout(response: Response):
    """Clear HttpOnly auth cookie (no-op for pure Bearer clients)."""
    _clear_auth_cookie(response)
    return {"ok": True, "cookie_cleared": True}
