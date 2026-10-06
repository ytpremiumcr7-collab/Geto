from pathlib import Path


def test_frontend_has_production_container_and_compose_service():
    platform = Path(__file__).resolve().parents[2]
    repo = platform.parent
    dockerfile = repo / "geoint-web" / "Dockerfile"
    nginx = repo / "geoint-web" / "nginx.conf"
    compose = (platform / "docker-compose.prod.yml").read_text()

    assert dockerfile.is_file()
    assert nginx.is_file()
    assert "geoint-web:" in compose
    assert "geoint-api:8000" in nginx.read_text()
    assert "proxy_http_version 1.1" in nginx.read_text()
