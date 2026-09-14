import pytest

from app.alerts.ssrf import UnsafeWebhookURL, validate_webhook_url


def test_blocks_localhost():
    with pytest.raises(UnsafeWebhookURL):
        validate_webhook_url("http://localhost:8080/hook")


def test_blocks_private_ip_literal():
    with pytest.raises(UnsafeWebhookURL):
        validate_webhook_url("http://127.0.0.1/x")
    with pytest.raises(UnsafeWebhookURL):
        validate_webhook_url("http://10.0.0.5/x")
    with pytest.raises(UnsafeWebhookURL):
        validate_webhook_url("http://169.254.169.254/latest/meta-data/")


def test_rejects_bad_scheme():
    with pytest.raises(UnsafeWebhookURL):
        validate_webhook_url("ftp://example.com/x")
