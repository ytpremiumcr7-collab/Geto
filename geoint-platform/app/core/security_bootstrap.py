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

        # Secrets: database, minio
        if _looks_like_placeholder_dsn(settings.database_url or ""):
            errors.append(
                "DATABASE_URL contains a placeholder password (change-me/geoint/password). "
                "Inject secrets from your secret manager."
            )

        minio_ak = getattr(settings, "minio_access_key", "") or ""
        minio_sk = getattr(settings, "minio_secret_key", "") or ""
        if _is_forbidden(minio_ak) or _is_forbidden(minio_sk):
            errors.append(
                "MINIO_ACCESS_KEY / MINIO_SECRET_KEY are missing or use forbidden defaults. "
                "Inject from secret manager."
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

        # Bootstrap token issuance should not be open without secret
        bootstrap = getattr(settings, "auth_bootstrap_secret", None) or ""
        if bootstrap and _is_forbidden(bootstrap):
            errors.append("AUTH_BOOTSTRAP_SECRET is a forbidden default value")

        # Rate limit must not fail-open in prod
        if getattr(settings, "rate_limit_fail_open", False):
            errors.append("RATE_LIMIT_FAIL_OPEN must be false in production/staging")

    # Legacy plaintext API keys forbidden outside development
    if getattr(settings, "api_keys", None) and str(settings.api_keys).strip():
        errors.append(
            "API_KEYS (plaintext) is forbidden when APP_ENV is production|staging; "
            "use API_KEY_HASHES only"
        )

    # Trusted hosts required in production (staging optional but recommended)
    th = (getattr(settings, "trusted_hosts", None) or "").strip()
    if settings.app_env in ("production", "prod") and not th:
        errors.append("TRUSTED_HOSTS is required in production (comma-separated hostnames)")


        # Metrics should not be public
        if getattr(settings, "metrics_public", False):
            warnings.append("METRICS_PUBLIC=true exposes /metrics without auth")

    else:
        # Dev soft checks
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
