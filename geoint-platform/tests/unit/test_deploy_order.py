from pathlib import Path


def _cmd_up_body() -> str:
    script = (Path(__file__).resolve().parents[2] / "scripts" / "deploy.sh").read_text()
    start = script.index("cmd_up() {")
    end = script.index("\n}\n\ncmd_migrate()", start)
    return script[start:end]


def test_deploy_migrates_before_starting_application_services():
    body = _cmd_up_body()

    quiesce = body.index("quiesce_apps")
    dependencies = body.index("start_dependencies")
    migrate = body.index("migrate")
    app_start = body.index("compose up -d geoint-api")
    ready = body.index("wait_ready")

    assert quiesce < dependencies < migrate < app_start < ready


def test_dependency_start_helper_includes_core_stateful_services():
    script = (Path(__file__).resolve().parents[2] / "scripts" / "deploy.sh").read_text()
    start = script.index("start_dependencies() {")
    end = script.index("\n}\n\nquiesce_apps()", start)
    body = script[start:end]

    assert "compose up -d postgres redis nats minio" in body
    assert "compose up -d clickhouse" in body
