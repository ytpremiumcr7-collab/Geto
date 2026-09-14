"""Emisión de tokens solo en development o con bootstrap secret (ops)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.auth.jwt import JWTService
from app.core.config import settings
from app.infrastructure.rate_limit import check_rate_limit

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class TokenRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    tenant_id: str = Field(min_length=1, max_length=128)
    roles: list[str] = Field(default_factory=lambda: ["operator"])
    bootstrap_secret: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/token", response_model=TokenResponse)
async def issue_token(request: Request, body: TokenRequest):
    """Solo si AUTH_BOOTSTRAP_SECRET coincide o app_env=development."""
    client = request.client.host if request.client else "unknown"
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
    return TokenResponse(access_token=token)
