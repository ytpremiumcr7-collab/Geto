from pathlib import Path


def test_backend_runtime_image_is_multistage_non_root_and_dev_tool_free():
    root = Path(__file__).resolve().parents[2]
    dockerfile = (root / "Dockerfile").read_text()

    assert " AS builder" in dockerfile
    assert dockerfile.count("\nFROM ") >= 1
    runtime = dockerfile.rsplit("\nFROM ", 1)[1]

    assert "USER geoint" in runtime
    assert "gcc" not in runtime
    assert "g++" not in runtime
    assert "libgdal-dev" not in runtime
    assert '".[dev]"' not in dockerfile
    assert "pip uninstall" in dockerfile
    for tool in ("pytest", "ruff", "mypy", "bandit", "pip-audit"):
        assert tool in dockerfile
