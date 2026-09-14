"""Fine-grained RBAC: Principal.permissions from ROLE_PERMISSIONS."""

from __future__ import annotations

from app.auth.models import Principal


def test_operator_permissions_exclude_opensky_read():
    p = Principal(user_id="u", tenant_id="t", roles=frozenset({"operator"}))
    perms = p.permissions()
    assert "geoint.source.usgs.read" in perms
    assert "geoint.source.opensky.read" not in perms


def test_goodmode_has_opensky_read():
    p = Principal(user_id="u", tenant_id="t", roles=frozenset({"goodmode"}))
    assert p.has_permission("geoint.source.opensky.read")


def test_admin_has_jobs_not_opensky_read_by_default():
    p = Principal(user_id="u", tenant_id="t", roles=frozenset({"admin"}))
    assert p.has_permission("geoint.admin.jobs")
    assert not p.has_permission("geoint.source.opensky.read")


def test_union_roles():
    p = Principal(user_id="u", tenant_id="t", roles=frozenset({"admin", "goodmode"}))
    assert p.has_permission("geoint.source.opensky.read")
    assert p.has_permission("geoint.admin.dlq")
