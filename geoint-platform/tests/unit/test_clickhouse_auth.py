from app.analytics.clickhouse import clickhouse_http_auth


def test_clickhouse_http_auth_uses_configured_credentials(monkeypatch):
    from app.analytics import clickhouse as clickhouse_mod

    monkeypatch.setattr(clickhouse_mod.settings, "clickhouse_user", "geoint")
    monkeypatch.setattr(clickhouse_mod.settings, "clickhouse_password", "strong-secret")

    assert clickhouse_http_auth() == ("geoint", "strong-secret")


def test_clickhouse_http_auth_is_none_without_credentials(monkeypatch):
    from app.analytics import clickhouse as clickhouse_mod

    monkeypatch.setattr(clickhouse_mod.settings, "clickhouse_user", None)
    monkeypatch.setattr(clickhouse_mod.settings, "clickhouse_password", None)

    assert clickhouse_http_auth() is None
