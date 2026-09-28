from pathlib import Path
import subprocess


def test_backup_restore_and_dr_verification_are_real_scripts():
    root = Path(__file__).resolve().parents[2]
    backup = (root / "scripts" / "backup.sh").read_text()
    restore = (root / "scripts" / "restore.sh").read_text()
    verify = (root / "scripts" / "verify_backup.sh").read_text()
    recover = (root / "scripts" / "recover_after_restore.sql").read_text()
    reset_transport = (root / "scripts" / "reset_transport.py").read_text()
    rebuild_clickhouse = (root / "scripts" / "rebuild_clickhouse.py").read_text()

    assert "pg_dump" in backup
    assert "mc mirror" in backup
    assert "sha256sum" in backup
    assert "pg_restore" in restore
    assert "mc mirror" in restore
    assert "RESTORE_CONFIRM" in restore
    assert "sha256sum -c" in verify

    assert "reset_transport.py" in restore
    assert "recover_after_restore.sql" in restore
    assert "UPDATE source_jobs" in recover
    assert "UPDATE processed_messages" in recover
    assert "UPDATE outbox_messages" in recover
    assert "UPDATE alert_deliveries" in recover
    assert "flushdb" in reset_transport
    assert "delete_stream" in reset_transport

    assert "rebuild_clickhouse.py" in restore
    assert "clickhouse_bootstrap.py" in restore
    assert "TRUNCATE TABLE IF EXISTS geoint.observations" in rebuild_clickhouse
    assert "system_worker_session" in rebuild_clickhouse


def test_operational_shell_scripts_parse():
    root = Path(__file__).resolve().parents[2]
    scripts = [
        root / "scripts" / "backup.sh",
        root / "scripts" / "restore.sh",
        root / "scripts" / "verify_backup.sh",
        root / "scripts" / "deploy.sh",
        root / "scripts" / "dr_restore_smoke.sh",
    ]

    for script in scripts:
        subprocess.run(
            ["bash", "-n", str(script)],
            check=True,
            capture_output=True,
            text=True,
        )


def test_dr_workflow_executes_real_backup_restore_scripts():
    root = Path(__file__).resolve().parents[3]
    workflow = (root / ".github" / "workflows" / "dr-restore.yml").read_text()

    assert "scripts/dr_restore_smoke.sh" in workflow
    assert "pull_request:" in workflow
    assert "bash -n scripts/restore.sh" in workflow
