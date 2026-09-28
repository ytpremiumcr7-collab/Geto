"""P0: production security bootstrap — OIDC required, no change-me, CORS explicit."""

from __future__ import annotations

from types import SimpleNamespace

import pytest


def _settings(**kwargs):
    """Lightweight stand-in for Settings (no pydantic required for unit test)."""
    base = dict(
        database_url="postgresql+asyncpg://geoint:StrongP@ssw0rd!@db:5432/geoint",
        s3_access_key="AKIA_STRONG_EXAMPLE_KEY",
        s3_secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        s3_create_bucket=False,
        app_env="production",
        auth_disabled=False,
        jwt_algorithm="RS256",
        jwt_jwks_url="https://idp.example.com/.well-known/jwks.json",
        cors_origins="https://app.example.com",
        cors_allow_http=False,
        rate_limit_fail_open=False,
        metrics_public=False,
        jwt_secret="",
        allow_hs256_in_production=False,
        auth_bootstrap_secret=None,
        trusted_hosts="api.example.com",
        api_keys="",
        auth_cookie_mode=True,
        auth_cookie_secure=True,
        oidc_client_id="geto-web",
        oidc_redirect_uri="https://app.example.com/api/v1/auth/oidc/callback",
        clickhouse_enabled=False,
        clickhouse_url="http://clickhouse:8123",
        clickhouse_user=None,
        clickhouse_password=None,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_production_ok_with_oidc():
    from app.core.security_bootstrap import validate_settings

    validate_settings(_settings(), role="test")


def test_production_rejects_missing_browser_oidc_client():
    from app.core.security_bootstrap import SecurityBootstrapError, validate_settings

    with pytest.raises(SecurityBootstrapError, match="OIDC_CLIENT_ID"):
        validate_settings(_settings(oidc_client_id=None), role="test")


def test_production_rejects_browser_auth_without_http_only_cookie_mode():
    from app.core.security_bootstrap import SecurityBootstrapError, validate_settings

    with pytest.raises(SecurityBootstrapError, match="AUTH_COOKIE_MODE"):
        validate_settings(_settings(auth_cookie_mode=False), role="test")


def test_production_rejects_insecure_auth_cookie():
    from app.core.security_bootstrap import SecurityBootstrapError, validate_settings

    with pytest.raises(SecurityBootstrapError, match="AUTH_COOKIE_SECURE"):
        validate_settings(_settings(auth_cookie_secure=False), role="test")


def test_production_rejects_missing_jwks():
    from app.core.security_bootstrap import SecurityBootstrapError, validate_settings

    with pytest.raises(SecurityBootstrapError, match="JWT_JWKS_URL"):
        validate_settings(_settings(jwt_jwks_url=None), role="test")


def test_production_rejects_hs256_without_override():
    from app.core.security_bootstrap import SecurityBootstrapError, validate_settings

    with pytest.raises(SecurityBootstrapError, match="JWT_ALGORITHM|HS256"):
        validate_settings(
            _settings(jwt_algorithm="HS256", jwt_jwks_url="https://idp.example.com/jwks"),
            role="test",
        )


def test_production_rejects_auth_disabled():
    from app.core.security_bootstrap import SecurityBootstrapError, validate_settings

    with pytest.raises(SecurityBootstrapError, match="AUTH_DISABLED"):
        validate_settings(_settings(auth_disabled=True), role="test")


def test_production_rejects_change_me_database():
    from app.core.security_bootstrap import SecurityBootstrapError, validate_settings

    with pytest.raises(SecurityBootstrapError, match="DATABASE_URL"):
        validate_settings(
            _settings(database_url="postgresql+asyncpg://geoint:change-me@db:5432/geoint"),
            role="test",
        )


def test_production_rejects_s3_defaults():
    from app.core.security_bootstrap import SecurityBootstrapError, validate_settings

    with pytest.raises(SecurityBootstrapError, match="S3_"):
        validate_settings(
            _settings(s3_access_key="change-me", s3_secret_key="change-me"),
            role="test",
        )


def test_production_rejects_star_cors():
    from app.core.security_bootstrap import SecurityBootstrapError, validate_settings

    with pytest.raises(SecurityBootstrapError, match="CORS"):
        validate_settings(_settings(cors_origins="*"), role="test")


def test_production_rejects_empty_cors():
    from app.core.security_bootstrap import SecurityBootstrapError, validate_settings

    with pytest.raises(SecurityBootstrapError, match="CORS_ORIGINS"):
        validate_settings(_settings(cors_origins=""), role="test")


def test_production_rejects_http_cors_without_flag():
    from app.core.security_bootstrap import SecurityBootstrapError, validate_settings

    with pytest.raises(SecurityBootstrapError, match="https"):
        validate_settings(_settings(cors_origins="http://app.example.com"), role="test")


def test_hs256_break_glass_requires_strong_secret():
    from app.core.security_bootstrap import SecurityBootstrapError, validate_settings

    with pytest.raises(SecurityBootstrapError, match="JWT_SECRET"):
        validate_settings(
            _settings(
                jwt_algorithm="HS256",
                jwt_jwks_url="https://idp.example.com/jwks",
                allow_hs256_in_production=True,
                jwt_secret="change-me",
            ),
            role="test",
        )


def test_hs256_break_glass_ok_with_strong_secret():
    from app.core.security_bootstrap import validate_settings

    validate_settings(
        _settings(
            jwt_algorithm="HS256",
            jwt_jwks_url="https://idp.example.com/jwks",
            allow_hs256_in_production=True,
            jwt_secret="a" * 32,
        ),
        role="test",
    )


def test_development_allows_open_cors():
    from app.core.security_bootstrap import cors_origin_list, validate_settings

    s = _settings(app_env="development", cors_origins="", jwt_jwks_url=None, jwt_algorithm="HS256")
    validate_settings(s, role="test")
    assert cors_origin_list(s) == ["*"]


def test_staging_requires_same_as_production():
    from app.core.security_bootstrap import SecurityBootstrapError, validate_settings

    with pytest.raises(SecurityBootstrapError, match="JWT_JWKS_URL"):
        validate_settings(
            _settings(app_env="staging", jwt_jwks_url=None, jwt_algorithm="RS256"),
            role="test",
        )


def test_production_rejects_missing_trusted_hosts():
    from app.core.security_bootstrap import SecurityBootstrapError, validate_settings

    with pytest.raises(SecurityBootstrapError, match="TRUSTED_HOSTS"):
        validate_settings(_settings(trusted_hosts=""), role="test")


def test_development_does_not_apply_production_plaintext_api_key_gate():
    from app.core.security_bootstrap import validate_settings

    validate_settings(
        _settings(
            app_env="development",
            api_keys="dev-key",
            jwt_jwks_url=None,
            jwt_algorithm="HS256",
        ),
        role="test",
    )


def test_production_rejects_clickhouse_without_credentials():
    from app.core.security_bootstrap import SecurityBootstrapError, validate_settings

    with pytest.raises(SecurityBootstrapError, match="CLICKHOUSE"):
        validate_settings(
            _settings(
                clickhouse_enabled=True,
                clickhouse_user="geoint",
                clickhouse_password="",
            ),
            role="test",
        )


def test_production_accepts_authenticated_clickhouse():
    from app.core.security_bootstrap import validate_settings

    validate_settings(
        _settings(
            clickhouse_enabled=True,
            clickhouse_user="geoint",
            clickhouse_password="a-real-clickhouse-password",
        ),
        role="test",
    )


def test_production_rejects_runtime_bucket_creation():
    from app.core.security_bootstrap import SecurityBootstrapError, validate_settings

    with pytest.raises(SecurityBootstrapError, match="S3_CREATE_BUCKET"):
        validate_settings(_settings(s3_create_bucket=True), role="test")
