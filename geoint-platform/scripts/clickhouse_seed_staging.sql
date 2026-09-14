INSERT INTO geoint.observations
(tenant_id, source_id, entity_id, entity_type, observed_at, lon, lat, alt_m, properties)
VALUES
('default', 'opensky', 'STG-ACFT-1', 'aircraft', now64(3), -99.1332, 19.4326, 10500, '{}'),
('default', 'opensky', 'STG-ACFT-2', 'aircraft', now64(3) - INTERVAL 1 HOUR, -99.20, 19.40, 9000, '{}'),
('default', 'firms', 'STG-FIRE-1', 'fire', now64(3) - INTERVAL 2 HOUR, -98.5, 19.1, NULL, '{}'),
('default', 'usgs', 'STG-EQ-1', 'earthquake', now64(3) - INTERVAL 3 HOUR, -99.0, 18.9, NULL, '{}'),
('default', 'ais', 'STG-VESS-1', 'vessel', now64(3) - INTERVAL 30 MINUTE, -96.1, 19.2, 0, '{}');
