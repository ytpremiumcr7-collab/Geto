"""Production workers must enter RLS through the centralized session helpers."""

from pathlib import Path


def _read(relative: str) -> str:
    root = Path(__file__).resolve().parents[2]
    return (root / relative).read_text(encoding="utf-8")


def test_outbox_dispatcher_uses_system_worker_session():
    source = _read("app/outbox/dispatcher.py")
    assert "system_worker_session" in source
    assert "SessionLocal" not in source
    assert 'GEOINT_SYSTEM_WORKER", "1"' in source


def test_retention_worker_enables_system_worker_mode():
    source = _read("app/retention/purge.py")
    assert "system_worker_session" in source
    assert 'GEOINT_SYSTEM_WORKER", "1"' in source


def test_outbox_rls_migration_has_tenant_and_system_policies():
    source = _read("migrations/versions/0015_outbox_rls.py")
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "outbox_messages_tenant_isolation" in source
    assert "outbox_messages_system_worker" in source
    assert "app.worker_mode" in source
