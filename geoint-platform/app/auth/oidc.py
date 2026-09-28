from __future__ import annotations

import base64
import hashlib
import json
import secrets
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx
import redis.asyncio as redis

from app.auth.jwt import JWTService
from app.auth.models import Principal
from app.core.config import settings


class OIDCConfigurationError(RuntimeError):
    pass


class OIDCStateError(ValueError):
    pass


class RedisOIDCStateStore:
    def __init__(self, url: str | None = None):
        self.client = redis.from_url(url or settings.redis_url, decode_responses=True)

    @staticmethod
    def _key(state: str) -> str:
        return f"geoint:oidc:state:{state}"

    async def put(self, state: str, payload: dict[str, Any], ttl_seconds: int) -> None:
        await self.client.set(
            self._key(state),
            json.dumps(payload, separators=(",", ":")),
            ex=max(60, int(ttl_seconds)),
        )

    async def pop(self, state: str) -> dict[str, Any] | None:
        raw = await self.client.getdel(self._key(state))
        if not raw:
            return None
        value = json.loads(raw)
        return value if isinstance(value, dict) else None


class OIDCService:
    def __init__(self, state_store: Any | None = None):
        self.state_store = state_store or RedisOIDCStateStore()

    @staticmethod
    def normalize_return_to(value: str | None) -> str:
        candidate = (value or "/").strip()
        if not candidate.startswith("/") or candidate.startswith("//"):
            return "/"
        parsed = urlparse(candidate)
        if parsed.scheme or parsed.netloc:
            return "/"
        return candidate

    def _require_config(self) -> None:
        if not settings.oidc_client_id:
            raise OIDCConfigurationError("OIDC_CLIENT_ID is required")
        if not settings.oidc_redirect_uri:
            raise OIDCConfigurationError("OIDC_REDIRECT_URI is required")
        if not settings.jwt_jwks_url:
            raise OIDCConfigurationError("JWT_JWKS_URL is required for OIDC token validation")

    async def discovery(self) -> dict[str, Any]:
        self._require_config()
        url = (settings.oidc_discovery_url or "").strip()
        if not url:
            issuer = (settings.jwt_issuer or "").rstrip("/")
            if not issuer.startswith(("https://", "http://localhost")):
                raise OIDCConfigurationError(
                    "OIDC_DISCOVERY_URL is required when JWT_ISSUER is not an HTTP(S) issuer URL"
                )
            url = f"{issuer}/.well-known/openid-configuration"
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise OIDCConfigurationError("OIDC discovery document is not an object")
        for key in ("authorization_endpoint", "token_endpoint"):
            if not payload.get(key):
                raise OIDCConfigurationError(f"OIDC discovery missing {key}")
        return payload

    @staticmethod
    def _pkce() -> tuple[str, str]:
        verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        return verifier, challenge

    async def authorization_url(self, *, return_to: str = "/") -> str:
        self._require_config()
        discovery = await self.discovery()
        state = secrets.token_urlsafe(32)
        verifier, challenge = self._pkce()
        await self.state_store.put(
            state,
            {
                "code_verifier": verifier,
                "return_to": self.normalize_return_to(return_to),
            },
            settings.oidc_state_ttl_seconds,
        )
        query = urlencode(
            {
                "response_type": "code",
                "client_id": settings.oidc_client_id,
                "redirect_uri": settings.oidc_redirect_uri,
                "scope": settings.oidc_scopes,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{discovery['authorization_endpoint']}?{query}"

    async def exchange_callback(
        self,
        *,
        code: str,
        state: str,
    ) -> tuple[str, Principal, str]:
        self._require_config()
        stored = await self.state_store.pop(state)
        if not stored:
            raise OIDCStateError("OIDC state is missing, expired, or already used")
        verifier = str(stored.get("code_verifier") or "")
        if not verifier:
            raise OIDCStateError("OIDC state has no PKCE verifier")

        discovery = await self.discovery()
        form = {
            "grant_type": "authorization_code",
            "client_id": settings.oidc_client_id,
            "code": code,
            "redirect_uri": settings.oidc_redirect_uri,
            "code_verifier": verifier,
        }
        if settings.oidc_client_secret:
            form["client_secret"] = settings.oidc_client_secret

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(discovery["token_endpoint"], data=form)
            response.raise_for_status()
            payload = response.json()
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not token:
            raise OIDCStateError("OIDC token response did not include access_token")

        # Signature, issuer, audience, expiry, tenant claim and roles are all
        # validated by the same production JWT service used by API requests.
        principal = JWTService().decode(str(token))
        return (
            str(token),
            principal,
            self.normalize_return_to(str(stored.get("return_to") or "/")),
        )
