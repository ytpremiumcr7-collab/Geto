from __future__ import annotations

import asyncio
from urllib.parse import parse_qs, urlparse

from app.auth.oidc import OIDCService


class _StateStore:
    def __init__(self):
        self.saved = {}

    async def put(self, state, payload, ttl_seconds):
        self.saved[state] = (payload, ttl_seconds)

    async def pop(self, state):
        item = self.saved.pop(state, None)
        return item[0] if item else None


def test_oidc_start_uses_authorization_code_pkce(monkeypatch):
    from app.core import config as cfg

    monkeypatch.setattr(cfg.settings, "oidc_client_id", "geto-web")
    monkeypatch.setattr(cfg.settings, "oidc_redirect_uri", "https://geto.example/api/v1/auth/oidc/callback")
    monkeypatch.setattr(cfg.settings, "oidc_scopes", "openid profile email")
    monkeypatch.setattr(cfg.settings, "jwt_jwks_url", "https://idp.example/jwks")

    store = _StateStore()
    service = OIDCService(state_store=store)

    async def discovery():
        return {
            "authorization_endpoint": "https://idp.example/authorize",
            "token_endpoint": "https://idp.example/token",
        }

    monkeypatch.setattr(service, "discovery", discovery)
    url = asyncio.run(service.authorization_url(return_to="/map"))

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["geto-web"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["redirect_uri"] == ["https://geto.example/api/v1/auth/oidc/callback"]
    assert query["state"][0] in store.saved
    stored, ttl = store.saved[query["state"][0]]
    assert stored["return_to"] == "/map"
    assert stored["code_verifier"]
    assert ttl > 0


def test_oidc_return_to_rejects_external_redirect():
    service = OIDCService(state_store=_StateStore())
    assert service.normalize_return_to("https://evil.example/steal") == "/"
    assert service.normalize_return_to("//evil.example/steal") == "/"
    assert service.normalize_return_to("/alerts") == "/alerts"
