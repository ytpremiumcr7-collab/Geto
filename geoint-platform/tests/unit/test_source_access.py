from app.auth.models import Principal
from app.policies.source_access import (
    can_admin_source,
    can_read_source,
    filter_sources_for_principal,
)


def test_opensky_goodmode_can_read_admin_cannot():
    good = Principal("u1", "t1", frozenset({"goodmode"}))
    admin = Principal("u2", "t1", frozenset({"admin"}))
    operator = Principal("u3", "t1", frozenset({"operator"}))

    assert can_read_source(good, "opensky") is True
    assert can_read_source(admin, "opensky") is False
    assert can_read_source(operator, "opensky") is False

    assert can_admin_source(admin, "opensky") is True
    assert can_admin_source(good, "opensky") is False


def test_operator_reads_usgs_not_opensky():
    op = Principal("u", "t", frozenset({"operator"}))
    assert can_read_source(op, "usgs_earthquake") is True
    assert can_read_source(op, "opensky") is False


def test_filter_hides_opensky_available_for_admin():
    admin = Principal("a", "t", frozenset({"admin"}))
    raw = [
        {
            "source_id": "opensky",
            "source_type": "adsb",
            "description": "x",
            "endpoint": "e",
            "authentication": "oauth2",
            "license": "terms",
            "commercial_allowed": False,
        },
        {
            "source_id": "usgs_earthquake",
            "source_type": "earthquake",
            "description": "x",
            "endpoint": "e",
            "authentication": "none",
            "license": "USGS",
            "commercial_allowed": True,
        },
    ]
    filtered = filter_sources_for_principal(admin, raw)
    by_id = {s["source_id"]: s for s in filtered}
    assert by_id["opensky"]["available"] is False
    assert by_id["opensky"]["can_admin"] is True
    assert by_id["usgs_earthquake"]["available"] is True
