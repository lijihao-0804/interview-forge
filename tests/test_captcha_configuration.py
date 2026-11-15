"""Anonymous email flows fail closed for either partial Turnstile setting."""
from unittest.mock import patch
import os

import pytest
from fastapi.testclient import TestClient

from interview_forge.api.app import app
from interview_forge.services import registration


@pytest.mark.parametrize("site,secret", [("test-site", ""), ("", "test-secret")])
def test_partial_configuration_blocks_config_and_both_send_flows(site, secret):
    with patch.dict(os.environ, {"IF_TURNSTILE_SITE_KEY": site, "IF_TURNSTILE_SECRET": secret}), \
         patch("interview_forge.api.routers.auth.send_registration_code") as send_register, \
         patch("interview_forge.api.routers.auth.send_password_reset_code") as send_reset, \
         patch.object(registration.urllib.request, "urlopen") as verify, \
         TestClient(app, raise_server_exceptions=False) as client:
        config = client.get("/api/register/config")
        assert config.status_code == 503
        assert config.json()["error_category"] == "captcha_unavailable"
        assert "no-store" in config.headers["cache-control"]
        assert "test-secret" not in config.text
        for path in ("/api/register/send-code", "/api/password/forgot/send-code"):
            for token in ("", "forged-token"):
                response = client.post(path, json={"email": "fixture@example.com", "captcha": token})
                assert response.status_code == 503
                assert response.json()["error_category"] == "captcha_unavailable"
        send_register.assert_not_called()
        send_reset.assert_not_called()
        verify.assert_not_called()


def test_explicitly_unconfigured_is_optional_and_whitespace_is_empty():
    with patch.dict(os.environ, {"IF_TURNSTILE_SITE_KEY": "  ", "IF_TURNSTILE_SECRET": ""}), \
         patch.object(registration.urllib.request, "urlopen") as verify:
        assert registration.captcha_config() is None
        registration.verify_captcha("", "127.0.0.1")
        verify.assert_not_called()


@pytest.mark.parametrize("failure", [OSError("offline"), ValueError("invalid response")])
def test_configured_verification_failure_never_sends_mail(failure):
    with patch.dict(os.environ, {"IF_TURNSTILE_SITE_KEY": "test-site", "IF_TURNSTILE_SECRET": "test-secret"}), \
         patch.object(registration.urllib.request, "urlopen", side_effect=failure), \
         patch("interview_forge.api.routers.auth.send_registration_code") as sender, \
         TestClient(app, raise_server_exceptions=False) as client:
        config = client.get("/api/register/config")
        assert config.status_code == 200
        assert config.json() == {"captcha": {"provider": "turnstile", "site_key": "test-site"}}
        response = client.post("/api/register/send-code", json={"email": "fixture@example.com", "captcha": "token"})
        assert response.status_code == 503
        assert response.json()["error_category"] == "captcha_unavailable"
        sender.assert_not_called()
