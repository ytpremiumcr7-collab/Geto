from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "GEOINT Platform"
    app_env: str = "development"
    log_level: str = "INFO"

    api_host: str = "127.0.0.1"
    api_port: int = 8000

    database_url: str
    database_pool_size: int = 10
    database_max_overflow: int = 20

    redis_url: str = "redis://localhost:6379/0"

    nats_url: str = "nats://localhost:4222"
    nats_stream: str = "GEOINT"
    nats_max_age_seconds: int = 604800

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str
    minio_secret_key: str
    minio_bucket_raw: str = "geoint-raw"
    dem_allowed_key_prefixes: str = "dem/,derived/"  # comma-separated
    minio_secure: bool = False
    minio_create_bucket: bool = True  # False in prod: provision externally

    opensky_client_id: str | None = None
    opensky_client_secret: str | None = None
    opensky_base_url: str = "https://opensky-network.org/api"
    opensky_token_url: str = (
        "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
    )
    opensky_interval_seconds: int = 30
    opensky_timeout_seconds: float = 20
    # Solo true si uso autorizado (investigación / consentimiento comercial)
    opensky_ingestion_enabled: bool = False

    celestrak_base_url: str = "https://celestrak.org/NORAD/elements/gp.php"
    celestrak_interval_seconds: int = 7200
    celestrak_group: str = "STATIONS"

    usgs_url: str = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"
    usgs_interval_seconds: int = 60

    firms_map_key: str | None = None
    firms_tile_hmac_secret: str | None = None  # optional; defaults to jwt_secret
    firms_source: str = "VIIRS_NOAA20_NRT"
    firms_bbox: str = "-180,-90,180,90"
    firms_day_range: int = 1
    firms_interval_seconds: int = 600
    # WMS: https://firms.modaps.eosdis.nasa.gov/mapserver/wms/fires/{MAP_KEY}/
    firms_wms_layer: str = "fires_viirs_24"

    aviation_weather_base_url: str = "https://aviationweather.gov/api/data"
    aviation_weather_user_agent: str = "GEOINT-Platform/2.0 contact@example.com"
    aviation_weather_interval_seconds: int = 300

    copernicus_stac_url: str = "https://stac.dataspace.copernicus.eu/v1/"
    copernicus_collection: str = "sentinel-2-l2a"
    copernicus_interval_seconds: int = 3600

    default_aoi_west: float = -118
    default_aoi_south: float = 14
    default_aoi_east: float = -86
    default_aoi_north: float = 33

    otel_enabled: bool = False
    otel_service_name: str = "geoint-platform"
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"

    prometheus_enabled: bool = True
    metrics_public: bool = False  # if False, /metrics requires auth

    # Edge / CORS — production requires explicit https origins (no *)
    # Example: CORS_ORIGINS=https://app.example.com,https://ops.example.com
    cors_origins: str = ""
    cors_allow_credentials: bool = True
    cors_allow_http: bool = False  # lab only: allow http:// origins when true
    # Trusted hosts for reverse-proxy deployments (comma-separated); empty = skip
    trusted_hosts: str = ""
    trusted_proxy_cidrs: str = ""  # comma-separated CIDRs allowed to set X-Forwarded-For

    # Auth
    auth_disabled: bool = False
    auth_cookie_mode: bool = False  # HttpOnly cookie session (BFF-friendly)
    auth_cookie_name: str = "geoint_access"
    auth_cookie_secure: bool = True  # set False only for local http
    auth_cookie_samesite: str = "lax"  # lax|strict|none
    auth_cookie_max_age: int = 3600

    jwt_secret: str = ""  # HS256 only; rejected if weak. Prefer OIDC in prod.
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "geoint-platform"
    jwt_audience: str = "geoint-api"
    jwt_expires_minutes: int = 60
    auth_bootstrap_secret: str | None = None
    api_keys: str | None = None  # LEGACY plaintext key:tenant:roles (prefer api_key_hashes)
    # Formato: sha256hex:tenant:role1,role2;...  (hash SHA-256 hex del secret en bruto)
    api_key_hashes: str | None = None
    jwt_jwks_url: str | None = None  # REQUIRED in production: OIDC JWKS URL
    jwt_tenant_claim: str = "tenant_id"
    # Emergency only: allow HS256 in production when OIDC is temporarily unavailable
    allow_hs256_in_production: bool = False
    rate_limit_per_minute: int = 120
    rate_limit_enabled: bool = True
    rate_limit_fail_open: bool = False  # prod: fail-closed if Redis down
    dev_tenant_id: str = "default"

    # Retention (days); 0 = disabled
    observations_retention_days: int = 90
    raw_payload_retention_days: int = 30

    minio_bucket_dropzone: str | None = None
    dropzone_prefix_incoming: str = "incoming/"
    dropzone_prefix_processed: str = "processed/"
    dropzone_prefix_failed: str = "failed/"

    readsb_aircraft_json_path: str = "/run/readsb/aircraft.json"
    ais_file_path: str = "/data/ais/latest.csv"
    horizons_base_url: str = "https://ssd.jpl.nasa.gov/api/horizons.api"

    nexrad_default_site: str = "KTLX"
    goes_satellite: str = "goes16"
    goes_product: str = "ABI-L2-CMIPF"

    clickhouse_enabled: bool = False
    clickhouse_url: str = "http://localhost:8123"

    # Alert notifier (SMTP)
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_use_tls: bool = True
    alert_notifier_poll_seconds: float = 2.0
    alert_notifier_batch_size: int = 20
    alert_notifier_lease_seconds: int = 120


@lru_cache
def get_settings() -> Settings:
    # Required values are supplied by pydantic-settings from env/.env at runtime.
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
