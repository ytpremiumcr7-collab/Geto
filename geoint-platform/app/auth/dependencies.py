"""Dependencias FastAPI: Bearer JWT o X-API-Key (hash SHA-256). tenant_id solo del token/key."""

from __future__ import annotations

import hashlib
import hmac
import logging

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from app.auth.jwt import JWTService
from app.auth.models import Principal
from app.core.config import settings

log = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_principal_from_entry(entry: str, raw_key: str, *, hashed: bool) -> Principal | None:
    """entry formats:
    hashed:   <sha256hex>:<tenant>[:role1,role2]
    plaintext (legacy): <rawkey>:<tenant>[:roles]  — compared via hash of both sides
    """
    parts = entry.split(":")
    if len(parts) < 2:
        return None
    stored, tenant = parts[0].strip(), parts[1].strip()
    roles = parts[2].split(",") if len(parts) > 2 else ["operator"]
    if not stored or not tenant:
        return None

    digest = _hash_key(raw_key)

    if hashed:
        # Normalize hex case; compare digests only (equal length always 64)
        stored_norm = stored.lower()
        if len(stored_norm) != 64:
            return None
        if not hmac.compare_digest(stored_norm, digest):
            return None
    else:
        # Legacy plaintext: hash the stored secret and compare digests
        # so compare_digest always sees equal-length strings (fixes broken auth
        # when key lengths differ and the old len() short-circuit rejected valid keys
        # or raised on compare_digest in edge cases).
        if getattr(settings, "app_env", "development") not in ("development", "dev", "test"):
            log.warning("plaintext API_KEYS used outside development — migrate to API_KEY_HASHES")
        stored_digest = _hash_key(stored)
        if not hmac.compare_digest(stored_digest, digest):
            return None

    return Principal(
        user_id=f"apikey:{digest[:12]}",
        tenant_id=tenant,
        roles=frozenset(r.strip() for r in roles if r.strip()),
    )


def _api_key_principal(raw_key: str) -> Principal | None:
    if not raw_key or not raw_key.strip():
        return None
    raw_key = raw_key.strip()

    hashed_cfg = getattr(settings, "api_key_hashes", None) or ""
    for entry in hashed_cfg.split(";"):
        entry = entry.strip()
        if not entry:
            continue
        p = _parse_principal_from_entry(entry, raw_key, hashed=True)
        if p:
            return p

    configured = settings.api_keys or ""
    for entry in configured.split(";"):
        entry = entry.strip()
        if not entry:
            continue
        p = _parse_principal_from_entry(entry, raw_key, hashed=False)
        if p:
            return p
    return None


async def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
    api_key: str | None = Security(_api_key_header),
) -> Principal:
    if settings.auth_disabled:
        if settings.app_env in ("production", "prod"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AUTH_DISABLED cannot be true in production",
            )
        return Principal(
            user_id="dev",
            tenant_id=settings.dev_tenant_id,
            roles=frozenset({"admin", "operator"}),
        )

    if api_key:
        principal = _api_key_principal(api_key)
        if principal:
            return principal
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    if credentials and credentials.scheme.lower() == "bearer" and credentials.credentials:
        try:
            return JWTService().decode(credentials.credentials)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from None

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_roles(*roles: str):
    async def _checker(
        principal: Principal = Depends(get_current_principal),
    ) -> Principal:
        if not roles:
            return principal
        if principal.has_role("admin"):
            return principal
        if any(principal.has_role(r) for r in roles):
            return principal
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    return _checker
