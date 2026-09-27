from types import SimpleNamespace

from app.api.routes.websocket import _token_from_cookie


def test_websocket_uses_httponly_session_cookie_in_cookie_mode(monkeypatch):
    from app.api.routes import websocket as websocket_routes

    monkeypatch.setattr(websocket_routes.settings, "auth_cookie_mode", True)
    monkeypatch.setattr(websocket_routes.settings, "auth_cookie_name", "geoint_access")
    ws = SimpleNamespace(cookies={"geoint_access": "signed-jwt"})

    assert _token_from_cookie(ws) == "signed-jwt"


def test_websocket_ignores_cookie_when_cookie_mode_disabled(monkeypatch):
    from app.api.routes import websocket as websocket_routes

    monkeypatch.setattr(websocket_routes.settings, "auth_cookie_mode", False)
    ws = SimpleNamespace(cookies={"geoint_access": "signed-jwt"})

    assert _token_from_cookie(ws) is None
