from pathlib import Path

from app.analytics.clickhouse import QUERY_TEMPLATES, observation_identity


def test_observation_identity_is_stable_and_tenant_scoped():
    row = {
        "source_id": "opensky",
        "entity_id": "ABC123",
        "observed_at": "2026-09-19T20:00:00.000+00:00",
    }
    first = observation_identity("tenant-a", row)
    assert first == "569CE13C4970221D7668610A0932AC514FC645AFAB51FE10383B5E124109CED6"
    assert first == observation_identity("tenant-a", dict(row))
    assert first != observation_identity("tenant-b", row)


def test_analytics_queries_count_logical_observations():
    assert QUERY_TEMPLATES
    for sql in QUERY_TEMPLATES.values():
        assert "uniqExact(observation_id)" in sql


def test_clickhouse_schema_upgrades_existing_tables_with_same_identity_material():
    sql = (Path(__file__).resolve().parents[2] / "deploy" / "clickhouse" / "init.sql").read_text()
    assert "ADD COLUMN IF NOT EXISTS observation_id String DEFAULT" in sql
    assert "toUnixTimestamp64Milli(observed_at)" in sql
    assert "hex(SHA256(concat(" in sql
