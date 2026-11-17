# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for Google OAuth client JSON parser & endpoint pinning (KB-AUTH-JSON)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from kanban.api.problems import ProblemException
from kanban.auth.oidc.config import OidcCardConfig
from kanban.auth.oidc.google_json import (
    MAX_GOOGLE_JSON_BYTES,
    parse_google_oauth_client_json,
)


def _valid_google_web_json_dict() -> dict[str, Any]:
    return {
        "web": {
            "client_id": "test-client-id-123.apps.googleusercontent.com",
            "project_id": "kanban-test-project",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_secret": "GOCSPX-super-secret-envelope-key",
            "redirect_uris": [
                "https://kanban.example.com/api/v1/auth/oidc/google-oauth/callback",
                "http://localhost:8000/api/v1/auth/oidc/google-oauth/callback",
            ],
            "javascript_origins": ["https://kanban.example.com"],
        }
    }


def test_positive_parse_google_oauth_client_json() -> None:
    """Verify parsing a valid Google web client JSON correctly normalizes config."""
    data = _valid_google_web_json_dict()
    raw = json.dumps(data)
    parsed = parse_google_oauth_client_json(
        raw,
        expected_redirect_uri="https://kanban.example.com/api/v1/auth/oidc/google-oauth/callback",
    )
    assert parsed.client_id == "test-client-id-123.apps.googleusercontent.com"
    assert parsed.client_secret == "GOCSPX-super-secret-envelope-key"
    assert parsed.project_id == "kanban-test-project"
    assert parsed.issuer == "https://accounts.google.com"
    assert parsed.kind == "OIDC"
    assert parsed.client_auth == "client_secret_basic"
    assert "openid" in parsed.scopes
    assert parsed.callback_uri_matched is True
    assert len(parsed.redirect_uris) == 2


def test_positive_callback_uri_unmatched() -> None:
    """Verify callback_uri_matched is False when expected URI is missing."""
    data = _valid_google_web_json_dict()
    raw = json.dumps(data)
    parsed = parse_google_oauth_client_json(
        raw,
        expected_redirect_uri="https://wrong-domain.example.com/api/v1/auth/oidc/google/callback",
    )
    assert parsed.callback_uri_matched is False


def test_negative_installed_desktop_client_rejected() -> None:
    """Verify installed desktop client configuration is rejected with helpful error."""
    data = {
        "installed": {
            "client_id": "installed-client-id.apps.googleusercontent.com",
            "client_secret": "installed-secret",
        }
    }
    with pytest.raises(ProblemException) as exc_info:
        parse_google_oauth_client_json(json.dumps(data))
    assert exc_info.value.code == "INVALID_GOOGLE_CLIENT_TYPE"
    assert "Installed/Desktop client" in (exc_info.value.detail or "")


def test_negative_untrusted_auth_uri_ssrf() -> None:
    """Verify SSRF/metadata auth_uri is rejected."""
    data = _valid_google_web_json_dict()
    data["web"]["auth_uri"] = "https://169.254.169.254/auth"
    with pytest.raises(ProblemException) as exc_info:
        parse_google_oauth_client_json(json.dumps(data))
    assert exc_info.value.code == "UNTRUSTED_GOOGLE_ENDPOINT"


def test_negative_untrusted_token_uri_ssrf() -> None:
    """Verify SSRF token_uri is rejected."""
    data = _valid_google_web_json_dict()
    data["web"]["token_uri"] = "https://evil.example.com/token"
    with pytest.raises(ProblemException) as exc_info:
        parse_google_oauth_client_json(json.dumps(data))
    assert exc_info.value.code == "UNTRUSTED_GOOGLE_ENDPOINT"


def test_negative_untrusted_cert_url() -> None:
    """Verify untrusted x509 cert URL is rejected."""
    data = _valid_google_web_json_dict()
    data["web"]["auth_provider_x509_cert_url"] = "https://evil.example.com/certs"
    with pytest.raises(ProblemException) as exc_info:
        parse_google_oauth_client_json(json.dumps(data))
    assert exc_info.value.code == "UNTRUSTED_GOOGLE_ENDPOINT"


def test_negative_oversized_payload() -> None:
    """Verify payloads exceeding 32KB are rejected."""
    large_payload = "a" * (MAX_GOOGLE_JSON_BYTES + 10)
    with pytest.raises(ProblemException) as exc_info:
        parse_google_oauth_client_json(large_payload)
    assert exc_info.value.code == "GOOGLE_JSON_TOO_LARGE"


def test_negative_utf16_lone_surrogate_rejected() -> None:
    """Verify UTF-16 lone surrogate is rejected prior to UTF-8 encoding."""
    bad_payload = '{"web": {"client_id": "test\ud800"}}'
    with pytest.raises(ProblemException) as exc_info:
        parse_google_oauth_client_json(bad_payload)
    assert exc_info.value.code == "INVALID_UTF8_SURROGATE"


def test_negative_missing_client_id_or_secret() -> None:
    """Verify missing client_id or client_secret raises validation errors."""
    data = _valid_google_web_json_dict()
    del data["web"]["client_id"]
    with pytest.raises(ProblemException) as exc_info:
        parse_google_oauth_client_json(json.dumps(data))
    assert exc_info.value.code == "INVALID_GOOGLE_CLIENT_ID"

    data2 = _valid_google_web_json_dict()
    del data2["web"]["client_secret"]
    with pytest.raises(ProblemException) as exc_info2:
        parse_google_oauth_client_json(json.dumps(data2))
    assert exc_info2.value.code == "INVALID_GOOGLE_CLIENT_SECRET"


def test_oidc_card_config_rejects_secret_in_public_config() -> None:
    """Verify secret keys in public_config raise SECRET_IN_PUBLIC_CONFIG."""
    bad_config: dict[str, Any] = {
        "kind": "OIDC",
        "issuer": "https://accounts.google.com",
        "client_id": "test-client-id",
        "client_secret": "forbidden-secret-in-public-config",
    }
    with pytest.raises(ProblemException) as exc_info:
        OidcCardConfig(**bad_config)
    assert exc_info.value.code == "SECRET_IN_PUBLIC_CONFIG"

    bad_config2: dict[str, Any] = {
        "kind": "OIDC",
        "issuer": "https://accounts.google.com",
        "client_id": "test-client-id",
        "google_oauth_json": "forbidden-json-in-public-config",
    }
    with pytest.raises(ProblemException) as exc_info2:
        OidcCardConfig(**bad_config2)
    assert exc_info2.value.code == "SECRET_IN_PUBLIC_CONFIG"
