"""JWT HS256 (dev) o RS256/OIDC vía JWKS (prod)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.auth.models import Principal
from app.core.config import settings

_jwks_client = None

# Secrets that must never be accepted for HS256 verify/sign
_FORBIDDEN_SECRETS = frozenset(
    {
        "",
        "change-me",
        "change-me-jwt",
        "change-me-jwt-use-openssl-rand-hex-32",
        "dev-only-not-for-prod",
        "secret",
        "jwt-secret",
        "your-256-bit-secret",
    }
)


def _assert_hs256_secret_usable(secret: str | None) -> str:
    if not secret or secret.strip() in _FORBIDDEN_SECRETS:
        raise RuntimeError(
            "JWT_SECRET is missing or uses a forbidden default value; "
            "set a strong secret (e.g. openssl rand -hex 32)"
        )
    if len(secret.encode("utf-8")) < 32:
        raise RuntimeError("JWT_SECRET must be at least 32 bytes for HS256")
    return secret


def _get_jwks_client():
    global _jwks_client
    if _jwks_client is not None:
        return _jwks_client
    jwks_url = getattr(settings, "jwt_jwks_url", None)
    if not jwks_url:
        return None
    from jwt import PyJWKClient

    _jwks_client = PyJWKClient(jwks_url, cache_keys=True)
    return _jwks_client


class JWTService:
    def __init__(
        self,
        secret: str | None = None,
        algorithm: str | None = None,
        issuer: str | None = None,
        audience: str | None = None,
    ):
        self.secret = secret if secret is not None else settings.jwt_secret
        self.algorithm = algorithm or settings.jwt_algorithm
        self.issuer = issuer or settings.jwt_issuer
        self.audience = audience or settings.jwt_audience

    def encode(
        self,
        *,
        user_id: str,
        tenant_id: str,
        roles: list[str],
        expires_minutes: int | None = None,
    ) -> str:
        """Solo HS256 local (bootstrap/dev). RS256 se emite en el IdP."""
        if self.algorithm.upper().startswith("RS"):
            raise RuntimeError("Local encode not supported for RS256 — use your IdP")
        secret = _assert_hs256_secret_usable(self.secret)

        now = datetime.now(UTC)
        exp = now + timedelta(minutes=expires_minutes or settings.jwt_expires_minutes)
        payload = {
            "sub": user_id,
            "tenant_id": tenant_id,
            "roles": roles,
            "iat": now,
            "exp": exp,
            "iss": self.issuer,
            "aud": self.audience,
        }
        return jwt.encode(payload, secret, algorithm=self.algorithm)

    def decode(self, token: str) -> Principal:
        if self.algorithm.upper().startswith("RS") or getattr(settings, "jwt_jwks_url", None):
            return self._decode_oidc(token)
        return self._decode_hs256(token)

    def _decode_hs256(self, token: str) -> Principal:
        # P0: never verify with weak/default secrets (forged admin tokens)
        secret = _assert_hs256_secret_usable(self.secret)
        options = {"require": ["exp", "sub"]}
        payload = jwt.decode(
            token,
            secret,
            algorithms=[self.algorithm],
            audience=self.audience,
            issuer=self.issuer,
            options=options,
        )
        return self._principal_from_payload(payload)

    def _decode_oidc(self, token: str) -> Principal:
        client = _get_jwks_client()
        if client is None:
            raise RuntimeError("JWT_JWKS_URL required for RS256/OIDC validation")
        signing_key = client.get_signing_key_from_jwt(token)
        # Strict: only the configured algorithm (no silent RS256 append)
        algorithms = [self.algorithm] if self.algorithm else ["RS256"]
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=algorithms,
            audience=self.audience,
            issuer=self.issuer,
            options={"require": ["exp", "sub"]},
        )
        return self._principal_from_payload(payload)

    def _principal_from_payload(self, payload: dict[str, Any]) -> Principal:
        roles = payload.get("roles") or payload.get("realm_access", {}).get("roles") or []
        if isinstance(roles, str):
            roles = [roles]
        tenant_claim = getattr(settings, "jwt_tenant_claim", "tenant_id")
        tenant_id = payload.get(tenant_claim) or payload.get("tenant_id")
        if not tenant_id:
            from app.core.config import settings as _s

            if getattr(_s, "app_env", "development") in ("production", "prod", "staging"):
                raise ValueError("JWT missing required tenant claim")
            tenant_id = "default"
        return Principal(
            user_id=str(payload["sub"]),
            tenant_id=str(tenant_id),
            roles=frozenset(str(r) for r in roles),
        )
