from pathlib import Path


def test_backup_restore_and_dr_verification_are_real_scripts():
    root = Path(__file__).resolve().parents[2]
    backup = (root / "scripts" / "backup.sh").read_text()
    restore = (root / "scripts" / "restore.sh").read_text()
    verify = (root / "scripts" / "verify_backup.sh").read_text()

    assert "pg_dump" in backup
    assert "mc mirror" in backup
    assert "sha256sum" in backup
    assert "pg_restore" in restore
    assert "mc mirror" in restore
    assert "RESTORE_CONFIRM" in restore
    assert "sha256sum -c" in verify
