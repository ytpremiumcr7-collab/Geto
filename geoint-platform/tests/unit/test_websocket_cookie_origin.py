from types import SimpleNamespace

from app.api.routes import websocket as websocket_routes


def test_cookie_websocket_origin_must_match_production_allowlist(monkeypatch):
    monkeypatch.setattr(websocket_routes.settings, "app_env", "production")
    monkeypatch.setattr(
        websocket_routes.settings,
        "cors_origins",
        "https://app.example.com,https://ops.example.com",
    )

    allowed = SimpleNamespace(headers={"origin": "https://app.example.com"})
    blocked = SimpleNamespace(headers={"origin": "https://evil.example"})

    assert websocket_routes._cookie_origin_allowed(allowed) is True
    assert websocket_routes._cookie_origin_allowed(blocked) is False


def test_cookie_websocket_without_origin_is_denied_in_production(monkeypatch):
    monkeypatch.setattr(websocket_routes.settings, "app_env", "production")
    monkeypatch.setattr(websocket_routes.settings, "cors_origins", "https://app.example.com")
    websocket = SimpleNamespace(headers={})

    assert websocket_routes._cookie_origin_allowed(websocket) is False
