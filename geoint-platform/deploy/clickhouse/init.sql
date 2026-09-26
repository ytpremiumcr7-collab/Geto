-- GEOINT analytics schema (ClickHouse). Applied by clickhouse entrypoint or
-- scripts/clickhouse_bootstrap.sh

CREATE DATABASE IF NOT EXISTS geoint;

CREATE TABLE IF NOT EXISTS geoint.observations
(
    tenant_id   String,
    source_id   String,
    entity_id   String,
    entity_type LowCardinality(String),
    observed_at DateTime64(3, 'UTC'),
    observation_id String DEFAULT hex(SHA256(concat(
        tenant_id, '\\x1F', source_id, '\\x1F', entity_id, '\\x1F',
        toString(toUnixTimestamp64Milli(observed_at))
    ))),
    lon         Float64,
    lat         Float64,
    alt_m       Nullable(Float64),
    properties  String DEFAULT '{}'
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(observed_at)
ORDER BY (tenant_id, source_id, observed_at, entity_id)
TTL toDateTime(observed_at) + INTERVAL 180 DAY;

-- Upgrade existing installations created before observation_id existed.
-- The DEFAULT is evaluated for historical rows that do not yet have a stored value.
ALTER TABLE geoint.observations
    ADD COLUMN IF NOT EXISTS observation_id String DEFAULT hex(SHA256(concat(
        tenant_id, '\\x1F', source_id, '\\x1F', entity_id, '\\x1F',
        toString(toUnixTimestamp64Milli(observed_at))
    )))
    AFTER observed_at;

CREATE TABLE IF NOT EXISTS geoint.alert_events
(
    tenant_id   String,
    alert_id    UUID,
    geofence_id UUID,
    entity_id   String,
    event_type  LowCardinality(String),
    severity    LowCardinality(String),
    occurred_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(occurred_at)
ORDER BY (tenant_id, occurred_at, alert_id)
TTL toDateTime(occurred_at) + INTERVAL 365 DAY;
