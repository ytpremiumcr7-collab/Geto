from app.sources.firms.tile_ticket import issue_ticket, verify_ticket


def test_ticket_roundtrip(monkeypatch):
    monkeypatch.setattr(
        "app.sources.firms.tile_ticket.settings.jwt_secret",
        "unit-test-secret-32-bytes-minimum!!",
        raising=False,
    )
    monkeypatch.setattr(
        "app.sources.firms.tile_ticket.settings.firms_tile_hmac_secret",
        "unit-test-secret-32-bytes-minimum!!",
        raising=False,
    )
    tok, exp = issue_ticket(tenant_id="t1", user_id="u1", ttl_s=120)
    assert exp > 0
    got = verify_ticket(tok)
    assert got == ("t1", "u1")


def test_ticket_rejects_tamper(monkeypatch):
    monkeypatch.setattr(
        "app.sources.firms.tile_ticket.settings.firms_tile_hmac_secret",
        "unit-test-secret-32-bytes-minimum!!",
        raising=False,
    )
    tok, _ = issue_ticket(tenant_id="t1", user_id="u1", ttl_s=120)
    bad = tok[:-4] + "xxxx"
    assert verify_ticket(bad) is None
    assert verify_ticket("") is None
    assert verify_ticket("not-base64") is None
