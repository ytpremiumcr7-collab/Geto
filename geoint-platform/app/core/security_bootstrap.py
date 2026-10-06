"""Fail-fast production security checks.

Called once at process startup (API and workers). Refuses to run if
production/staging is misconfigured: weak secrets, AUTH_DISABLED, HS256
without explicit override, missing OIDC/JWKS, open CORS, etc.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.config import Settings

log = logging.getLogger(__name__)

# Values that must never appear as production secrets
_FORBIDDEN_SECRET_VALUES = frozenset(
    {
        "",
        "change-me",
        "change-me-jwt",
        "change-me-jwt-use-openssl-rand-hex-32",
        "dev-only-not-for-prod",
        "secret",
        "jwt-secret",
        "your-256-bit-secret",
        "password",
        "admin",
        "geoint",
        "minioadmin",
        "minioadmin123",
    }
)

_PROD_ENVS = frozenset({"production", "prod", "staging"})


class SecurityBootstrapError(RuntimeError):
    """Raised when the process must not start."""


def _is_forbidden(value: str | None) -> bool:
    if value is None:
        return True
    v = value.strip()
    if not v:
        return True
    if v.lower() in _FORBIDDEN_SECRET_VALUES:
        return True
    if v.lower().startswith("change-me"):
        return True
    return False


def _looks_like_placeholder_dsn(database_url: str) -> bool:
    lower = database_url.lower()
    return any(
        x in lower
        for x in (
            ":change-me@",
            ":password@",
            ":geoint@",
            "://geoint:geoint@",
        )
    )


def validate_settings(settings: Settings, *, role: str = "api") -> None:
    """Validate settings for the current environment.

    - development/test: only soft warnings for weak secrets
    - production/prod/staging: hard fail on insecure configuration
    """
    env = (settings.app_env or "development").strip().lower()
    errors: list[str] = []
    warnings: list[str] = []

    if settings.auth_disabled:
        if env in _PROD_ENVS:
            errors.append("AUTH_DISABLED=true is forbidden when APP_ENV is production/staging")
        else:
            warnings.append("AUTH_DISABLED=true — all requests are privileged (dev only)")

    # --- Production / staging hard requirements ---
    if env in _PROD_ENVS:
        # OIDC / JWKS mandatory in production (P0)
        jwks = (getattr(settings, "jwt_jwks_url", None) or "").strip()
        algo = (settings.jwt_algorithm or "HS256").upper()
        allow_hs256 = bool(getattr(settings, "allow_hs256_in_production", False))

        if not jwks:
            errors.append(
                "JWT_JWKS_URL is required when APP_ENV=production|staging "
                "(OIDC/JWKS). Set ALLOW_HS256_IN_PRODUCTION=true only for "
                "emergency break-glass (not recommended)."
            )
        if algo.startswith("HS") and not allow_hs256:
            errors.append(
                f"JWT_ALGORITHM={algo} is not allowed in production without "
                "ALLOW_HS256_IN_PRODUCTION=true. Use RS256 (or similar) with JWT_JWKS_URL."
            )
        if algo.startswith("HS") and allow_hs256:
            secret = settings.jwt_secret or ""
            if _is_forbidden(secret) or len(secret.encode("utf-8")) < 32:
                errors.append(
                    "ALLOW_HS256_IN_PRODUCTION requires a strong JWT_SECRET "
                    "(>= 32 random bytes, not a default/placeholder)"
                )
            warnings.append(
                "ALLOW_HS256_IN_PRODUCTION=true — using local HS256 instead of OIDC; "
                "migrate to JWT_JWKS_URL as soon as possible"
            )

        if jwks and not (jwks.startswith("https://") or jwks.startswith("http://localhost")):
            # Allow http only for local IdP in staging lab; prefer https
            if env == "production" and not jwks.startswith("https://"):
                errors.append("JWT_JWKS_URL must use https:// in production")

        # Secrets: database and S3 object storage
        if _looks_like_placeholder_dsn(settings.database_url or ""):
            errors.append(
                "DATABASE_URL contains a placeholder password (change-me/geoint/password). "
                "Inject secrets from your secret manager."
            )

        s3_ak = getattr(settings, "s3_access_key", "") or ""
        s3_sk = getattr(settings, "s3_secret_key", "") or ""
        if _is_forbidden(s3_ak) or _is_forbidden(s3_sk):
            errors.append(
                "S3_ACCESS_KEY / S3_SECRET_KEY are missing or use forbidden defaults. "
                "Inject from secret manager."
            )

        if getattr(settings, "s3_create_bucket", True):
            errors.append(
                "S3_CREATE_BUCKET must be false in production/staging; "
                "provision object-storage buckets out-of-band before deploy"
            )

        # CORS: must be explicit, never *
        origins = _parse_cors_origins(getattr(settings, "cors_origins", "") or "")
        if not origins:
            errors.append(
                "CORS_ORIGINS is required in production/staging "
                "(comma-separated https origins, e.g. https://app.example.com)"
            )
        if "*" in origins:
            errors.append("CORS_ORIGINS must not contain '*' in production/staging")
        for o in origins:
            if o != "null" and not re.match(r"^https://[a-zA-Z0-9._:-]+$", o):
                # allow http only for explicit staging lab hosts if cors_allow_http
                if o.startswith("http://") and getattr(settings, "cors_allow_http", False):
                    warnings.append(f"CORS origin uses http:// (lab only): {o}")
                elif not o.startswith("https://"):
                    errors.append(f"CORS origin must be https://… in production: {o}")

        # Browser product auth is a BFF OIDC Authorization Code + PKCE flow.
        # Production must not fall back to the bootstrap role form or expose the
        # IdP token to browser storage.
        oidc_client_id = (getattr(settings, "oidc_client_id", None) or "").strip()
        oidc_redirect_uri = (getattr(settings, "oidc_redirect_uri", None) or "").strip()
        if not oidc_client_id:
            errors.append("OIDC_CLIENT_ID is required in production/staging for browser login")
        if not oidc_redirect_uri:
            errors.append("OIDC_REDIRECT_URI is required in production/staging for browser login")
        elif not oidc_redirect_uri.startswith("https://"):
            errors.append("OIDC_REDIRECT_URI must use https:// in production/staging")
        if not getattr(settings, "auth_cookie_mode", False):
            errors.append("AUTH_COOKIE_MODE=true is required in production/staging browser login")
        if not getattr(settings, "auth_cookie_secure", False):
            errors.append("AUTH_COOKIE_SECURE=true is required in production/staging")

        # Bootstrap token issuance should not be open without secret
        bootstrap = getattr(settings, "auth_bootstrap_secret", None) or ""
        if bootstrap and _is_forbidden(bootstrap):
            errors.append("AUTH_BOOTSTRAP_SECRET is a forbidden default value")

        # Rate limit must not fail-open in prod
        if getattr(settings, "rate_limit_fail_open", False):
            errors.append("RATE_LIMIT_FAIL_OPEN must be false in production/staging")

    if env in _PROD_ENVS:
        # Legacy plaintext API keys are forbidden outside development/test.
        if getattr(settings, "api_keys", None) and str(settings.api_keys).strip():
            errors.append(
                "API_KEYS (plaintext) is forbidden when APP_ENV is production|staging; "
                "use API_KEY_HASHES only"
            )

        # Trusted hosts are mandatory in production; staging may run behind an
        # ephemeral hostname but should still set this when the hostname is stable.
        th = (getattr(settings, "trusted_hosts", None) or "").strip()
        if env in ("production", "prod") and not th:
            errors.append("TRUSTED_HOSTS is required in production (comma-separated hostnames)")

        if getattr(settings, "clickhouse_enabled", False):
            ch_user = (getattr(settings, "clickhouse_user", None) or "").strip()
            ch_password = getattr(settings, "clickhouse_password", None) or ""
            if not ch_user or not ch_password:
                errors.append(
                    "CLICKHOUSE_USER and CLICKHOUSE_PASSWORD are required when "
                    "CLICKHOUSE_ENABLED=true in production/staging"
                )
            elif _is_forbidden(ch_password):
                errors.append("CLICKHOUSE_PASSWORD uses a forbidden default/placeholder value")

        if getattr(settings, "metrics_public", False):
            warnings.append("METRICS_PUBLIC=true exposes /metrics without auth")
    else:
        # Dev/test soft checks
        if settings.jwt_secret and _is_forbidden(settings.jwt_secret):
            warnings.append(
                "JWT_SECRET is empty or a known-weak default; encode/decode will reject it"
            )

    for w in warnings:
        log.warning("security_bootstrap_warning role=%s detail=%s", role, w)

    if errors:
        msg = (
            f"Security bootstrap failed for APP_ENV={env!r} (role={role}). "
            "Fix the following before starting:\n  - " + "\n  - ".join(errors)
        )
        log.error(msg)
        raise SecurityBootstrapError(msg)

    log.info(
        "security_bootstrap_ok env=%s role=%s jwks=%s algo=%s",
        env,
        role,
        bool((getattr(settings, "jwt_jwks_url", None) or "").strip()),
        settings.jwt_algorithm,
    )


def _parse_cors_origins(raw: str) -> list[str]:
    if not raw or not raw.strip():
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


def cors_origin_list(settings: Settings) -> list[str]:
    """Origins for CORSMiddleware.

    - production/staging: only CORS_ORIGINS (validated non-empty, no *)
    - development/test: CORS_ORIGINS if set, else ['*'] for local DX
    """
    env = (settings.app_env or "development").strip().lower()
    origins = _parse_cors_origins(getattr(settings, "cors_origins", "") or "")
    if env in _PROD_ENVS:
        return origins
    return origins if origins else ["*"]
