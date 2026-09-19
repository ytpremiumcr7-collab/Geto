from app.analytics.clickhouse import QUERY_TEMPLATES, observation_identity


def test_observation_identity_is_stable_and_tenant_scoped():
    row = {
        "source_id": "opensky",
        "entity_id": "ABC123",
        "observed_at": "2026-09-19T20:00:00.000+00:00",
    }
    first = observation_identity("tenant-a", row)
    assert first == observation_identity("tenant-a", dict(row))
    assert first != observation_identity("tenant-b", row)


def test_analytics_queries_count_logical_observations():
    assert QUERY_TEMPLATES
    for sql in QUERY_TEMPLATES.values():
        assert "uniqExact(observation_id)" in sql
