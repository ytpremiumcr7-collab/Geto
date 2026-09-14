"""P0 security: weak JWT rejected on decode; API key hash compare works."""

from __future__ import annotations

import hashlib
import os

import jwt
import pytest

# env before settings load
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("MINIO_ACCESS_KEY", "x")
os.environ.setdefault("MINIO_SECRET_KEY", "y")


def test_jwt_decode_rejects_forbidden_secret(monkeypatch):
    from app.auth import jwt as jwtmod
    from app.core import config as cfg

    monkeypatch.setattr(cfg.settings, "jwt_secret", "change-me-jwt")
    monkeypatch.setattr(cfg.settings, "jwt_algorithm", "HS256")
    monkeypatch.setattr(cfg.settings, "jwt_issuer", "geoint-platform")
    monkeypatch.setattr(cfg.settings, "jwt_audience", "geoint-api")
    monkeypatch.setattr(cfg.settings, "jwt_jwks_url", None)

    # Forge token with weak secret
    token = jwt.encode(
        {
            "sub": "attacker",
            "tenant_id": "victim-tenant",
            "roles": ["admin"],
            "iss": "geoint-platform",
            "aud": "geoint-api",
        },
        "change-me-jwt",
        algorithm="HS256",
    )
    with pytest.raises(RuntimeError, match="JWT_SECRET|forbidden|32 bytes"):
        jwtmod.JWTService(secret="change-me-jwt").decode(token)


def test_jwt_encode_rejects_weak_secret(monkeypatch):
    from app.auth.jwt import JWTService

    with pytest.raises(RuntimeError):
        JWTService(secret="change-me-jwt").encode(user_id="u", tenant_id="t", roles=["admin"])


def test_jwt_roundtrip_strong_secret(monkeypatch):
    from app.auth.jwt import JWTService
    from app.core import config as cfg

    secret = "a" * 32
    monkeypatch.setattr(cfg.settings, "jwt_secret", secret)
    monkeypatch.setattr(cfg.settings, "jwt_jwks_url", None)
    svc = JWTService(secret=secret)
    token = svc.encode(user_id="ops", tenant_id="t1", roles=["operator"])
    principal = svc.decode(token)
    assert principal.user_id == "ops"
    assert principal.tenant_id == "t1"
    assert principal.has_role("operator")


def test_api_key_hashed_match(monkeypatch):
    from app.auth import dependencies as deps
    from app.core import config as cfg

    raw = "super-secret-key-value"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    monkeypatch.setattr(cfg.settings, "api_key_hashes", f"{digest}:tenant-a:operator")
    monkeypatch.setattr(cfg.settings, "api_keys", None)
    p = deps._api_key_principal(raw)
    assert p is not None
    assert p.tenant_id == "tenant-a"
    assert p.has_role("operator")


def test_api_key_hashed_mismatch(monkeypatch):
    from app.auth import dependencies as deps
    from app.core import config as cfg

    digest = hashlib.sha256(b"correct").hexdigest()
    monkeypatch.setattr(cfg.settings, "api_key_hashes", f"{digest}:t:admin")
    monkeypatch.setattr(cfg.settings, "api_keys", None)
    assert deps._api_key_principal("wrong") is None


def test_api_key_plaintext_legacy(monkeypatch):
    from app.auth import dependencies as deps
    from app.core import config as cfg

    monkeypatch.setattr(cfg.settings, "api_key_hashes", "")
    monkeypatch.setattr(cfg.settings, "api_keys", "mykey:tenant-b:admin")
    monkeypatch.setattr(cfg.settings, "app_env", "development")
    p = deps._api_key_principal("mykey")
    assert p is not None
    assert p.tenant_id == "tenant-b"


def test_ingestion_worker_compiles():
    import py_compile
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "app/workers/ingestion.py"
    py_compile.compile(str(path), doraise=True)


def test_topography_service_imports():
    from app.topography.service import TopographyService

    assert TopographyService is not None
