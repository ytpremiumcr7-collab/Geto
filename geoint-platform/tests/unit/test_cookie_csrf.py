from types import SimpleNamespace

from app.middleware.cookie_csrf import browser_cookie_mutation_allowed


def _request(
    *,
    method="POST",
    origin=None,
    referer=None,
    sec_fetch_site=None,
    cookie=True,
    bearer=False,
    api_key=False,
):
    headers = {}
    if origin is not None:
        headers["origin"] = origin
    if referer is not None:
        headers["referer"] = referer
    if sec_fetch_site is not None:
        headers["sec-fetch-site"] = sec_fetch_site
    if bearer:
        headers["authorization"] = "Bearer abc"
    if api_key:
        headers["x-api-key"] = "secret"
    cookies = {"geoint_access": "session"} if cookie else {}
    return SimpleNamespace(method=method, headers=headers, cookies=cookies)


def _prod(monkeypatch):
    from app.middleware import cookie_csrf

    monkeypatch.setattr(cookie_csrf.settings, "app_env", "production")
    monkeypatch.setattr(cookie_csrf.settings, "auth_cookie_mode", True)
    monkeypatch.setattr(cookie_csrf.settings, "auth_cookie_name", "geoint_access")
    monkeypatch.setattr(cookie_csrf.settings, "cors_origins", "https://app.example.com")


def test_cross_site_fetch_metadata_is_rejected_before_origin_fallback(monkeypatch):
    _prod(monkeypatch)

    assert not browser_cookie_mutation_allowed(
        _request(
            origin="https://app.example.com",
            sec_fetch_site="cross-site",
        )
    )


def test_same_origin_fetch_metadata_allows_cookie_mutation(monkeypatch):
    _prod(monkeypatch)

    assert browser_cookie_mutation_allowed(
        _request(sec_fetch_site="same-origin")
    )


def test_allowed_origin_is_fallback_for_same_site_cross_origin_bff(monkeypatch):
    _prod(monkeypatch)

    assert browser_cookie_mutation_allowed(
        _request(
            origin="https://app.example.com",
            sec_fetch_site="same-site",
        )
    )
    assert not browser_cookie_mutation_allowed(
        _request(
            origin="https://evil.example",
            sec_fetch_site="same-site",
        )
    )


def test_referer_is_used_when_origin_is_absent(monkeypatch):
    _prod(monkeypatch)

    assert browser_cookie_mutation_allowed(
        _request(referer="https://app.example.com/workspaces/123")
    )
    assert not browser_cookie_mutation_allowed(
        _request(referer="https://app.example.com.attacker.test/x")
    )


def test_missing_browser_provenance_is_fail_closed(monkeypatch):
    _prod(monkeypatch)

    assert not browser_cookie_mutation_allowed(_request())


def test_bearer_or_api_key_mutations_do_not_depend_on_browser_origin(monkeypatch):
    _prod(monkeypatch)

    assert browser_cookie_mutation_allowed(_request(bearer=True))
    assert browser_cookie_mutation_allowed(_request(api_key=True))


def test_safe_methods_are_not_rejected(monkeypatch):
    _prod(monkeypatch)

    assert browser_cookie_mutation_allowed(_request(method="GET"))
