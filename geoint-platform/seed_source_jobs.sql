-- Seed SourceJobs — OpenSky deshabilitado por defecto (goodmode / consentimiento)
INSERT INTO source_jobs (id, tenant_id, name, source_id, job_type, status, interval_seconds, next_run_at, config, enabled)
VALUES
  (gen_random_uuid(), 'default', 'opensky-default', 'opensky', 'poll', 'pending', 30, NOW(),
   '{"lamin": 14, "lomin": -118, "lamax": 33, "lomax": -86}'::jsonb, false),
  (gen_random_uuid(), 'default', 'readsb-local', 'readsb_local', 'poll', 'pending', 2, NOW(),
   '{}'::jsonb, true),
  (gen_random_uuid(), 'default', 'ais-file', 'ais_file', 'poll', 'pending', 300, NOW(),
   '{}'::jsonb, true),
  (gen_random_uuid(), 'default', 'celestrak-stations', 'celestrak', 'poll', 'pending', 7200, NOW(),
   '{"group": "STATIONS"}'::jsonb, true),
  (gen_random_uuid(), 'default', 'usgs-all-day', 'usgs_earthquake', 'poll', 'pending', 60, NOW(),
   '{}'::jsonb, true),
  (gen_random_uuid(), 'default', 'firms-nrt', 'nasa_firms', 'poll', 'pending', 600, NOW(),
   '{}'::jsonb, false),  -- enable only with FIRMS_MAP_KEY
  (gen_random_uuid(), 'default', 'metar-kmci', 'aviation_weather', 'poll', 'pending', 300, NOW(),
   '{"station_ids": "KMCI"}'::jsonb, true),
  (gen_random_uuid(), 'default', 'copernicus-s2', 'copernicus', 'poll', 'pending', 3600, NOW(),
   '{"limit": 20}'::jsonb, true),
  (gen_random_uuid(), 'default', 'minio-dropzone', 'minio_dropzone', 'poll', 'pending', 60, NOW(),
   '{"max_objects": 50}'::jsonb, true),
  (gen_random_uuid(), 'default', 'nexrad-ktlx', 'nexrad', 'poll', 'pending', 300, NOW(),
   '{"site": "KTLX", "max_keys": 10}'::jsonb, true),
  (gen_random_uuid(), 'default', 'goes16-cmipf', 'goes', 'poll', 'pending', 600, NOW(),
   '{"max_keys": 10}'::jsonb, true),
  (gen_random_uuid(), 'default', 'jpl-horizons-earth', 'jpl_horizons', 'poll', 'pending', 86400, NOW(),
   '{"command": "399", "step": "1 d"}'::jsonb, true)
ON CONFLICT DO NOTHING;
