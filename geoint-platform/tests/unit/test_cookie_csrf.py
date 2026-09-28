from types import SimpleNamespace

from app.middleware.cookie_csrf import browser_cookie_mutation_allowed


def _request(*, method="POST", origin=None, cookie=True, bearer=False, api_key=False):
    headers = {}
    if origin is not None:
        headers["origin"] = origin
    if bearer:
        headers["authorization"] = "Bearer abc"
    if api_key:
        headers["x-api-key"] = "secret"
    cookies = {"geoint_access": "session"} if cookie else {}
    return SimpleNamespace(method=method, headers=headers, cookies=cookies)


def test_cookie_mutation_requires_allowed_origin_in_production(monkeypatch):
    from app.middleware import cookie_csrf

    monkeypatch.setattr(cookie_csrf.settings, "app_env", "production")
    monkeypatch.setattr(cookie_csrf.settings, "auth_cookie_mode", True)
    monkeypatch.setattr(cookie_csrf.settings, "auth_cookie_name", "geoint_access")
    monkeypatch.setattr(cookie_csrf.settings, "cors_origins", "https://app.example.com")

    assert browser_cookie_mutation_allowed(
        _request(origin="https://app.example.com")
    )
    assert not browser_cookie_mutation_allowed(
        _request(origin="https://evil.example")
    )
    assert not browser_cookie_mutation_allowed(_request(origin=None))


def test_bearer_or_api_key_mutations_do_not_depend_on_browser_origin(monkeypatch):
    from app.middleware import cookie_csrf

    monkeypatch.setattr(cookie_csrf.settings, "app_env", "production")
    monkeypatch.setattr(cookie_csrf.settings, "auth_cookie_mode", True)
    monkeypatch.setattr(cookie_csrf.settings, "cors_origins", "https://app.example.com")

    assert browser_cookie_mutation_allowed(_request(origin=None, bearer=True))
    assert browser_cookie_mutation_allowed(_request(origin=None, api_key=True))


def test_safe_methods_are_not_rejected(monkeypatch):
    from app.middleware import cookie_csrf

    monkeypatch.setattr(cookie_csrf.settings, "app_env", "production")
    monkeypatch.setattr(cookie_csrf.settings, "auth_cookie_mode", True)
    monkeypatch.setattr(cookie_csrf.settings, "cors_origins", "https://app.example.com")

    assert browser_cookie_mutation_allowed(_request(method="GET", origin=None))
