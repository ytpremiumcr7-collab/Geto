from pathlib import Path


def _cmd_up_body() -> str:
    script = (Path(__file__).resolve().parents[2] / "scripts" / "deploy.sh").read_text()
    start = script.index("cmd_up() {")
    end = script.index("\n}\n\ncmd_migrate()", start)
    return script[start:end]


def test_deploy_migrates_before_starting_application_services():
    body = _cmd_up_body()

    dependencies = body.index("compose up -d postgres redis nats minio")
    migrate = body.index("migrate")
    app_start = body.index("compose up -d geoint-api")
    ready = body.index("wait_ready")

    assert dependencies < migrate < app_start < ready
