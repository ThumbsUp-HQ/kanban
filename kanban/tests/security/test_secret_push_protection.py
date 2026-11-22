# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit and integration tests for secret push-protection across write paths."""

from __future__ import annotations

import pytest

from kanban.api.problems import ProblemException
from kanban.security.push_protection import (
    PushProtectionMode,
    enforce_secret_push_protection,
    scan_text_for_secrets,
)
from kanban.security.scrubber import SecretKind, scrub_text
from kanban.services.activity import (
    JSONValue,
    _validate_and_scrub_payload,
)


def test_positive_legitimate_prose_passes() -> None:
    """Verify legitimate technical prose without credentials passes without error."""
    valid_text = (
        "Here is the issue description with commit 4f836f691234567890abcdef1234567890abcdef "
        "and uuid 123e4567-e89b-12d3-a456-426614174000. For details see "
        "https://example.com/docs/api. "
        "ETag is e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855."
    )
    result = enforce_secret_push_protection(valid_text, field="description_markdown")
    assert result == valid_text


def test_positive_allowlist_marker_bypasses_check() -> None:
    """Verify lines containing 'kb-allow-secret' marker are exempt from push protection."""
    allowlisted = (
        "This is a test case with a dummy token:\n"
        "ghp_1234567890abcdef1234567890abcdef1234 kb-allow-secret: placeholder test key\n"
        "Normal trailing text."
    )
    findings = scan_text_for_secrets(allowlisted, allow_markers=True)
    assert len(findings) == 0

    result = enforce_secret_push_protection(
        allowlisted, field="description_markdown", allow_markers=True
    )
    assert result == allowlisted


def test_negative_rejection_pem_private_key() -> None:
    """Verify PEM private keys trigger RFC 7807 422 ProblemException without leaking key."""
    pem_key = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEogIBAAKCAQEA0ABCDEF1234567890abcdefghijklmnopqrstuvwxyzAB==\n"
        "-----END RSA PRIVATE KEY-----"
    )
    text = f"Here is my key:\n{pem_key}\nPlease import it."
    with pytest.raises(ProblemException) as exc_info:
        enforce_secret_push_protection(text, field="description_markdown")

    exc = exc_info.value
    assert exc.status == 422
    assert exc.code == "SECRET_DETECTED_IN_PAYLOAD"
    assert exc.field == "description_markdown"
    assert exc.extra is not None
    assert exc.extra["rule_id"] == "PEM_PRIVATE_KEY"
    assert exc.extra["secret_kind"] == SecretKind.PRIVATE_KEY.value
    assert exc.extra["line"] == 2
    assert "MIIEog" not in exc.extra["fingerprint"]
    assert pem_key not in exc.detail if exc.detail else True


def test_negative_rejection_github_token() -> None:
    """Verify GitHub tokens trigger 422 ProblemException."""
    gh_token = "ghp_1234567890abcdef1234567890abcdef1234"
    text = f"Token is {gh_token}"
    with pytest.raises(ProblemException) as exc_info:
        enforce_secret_push_protection(text, field="summary")

    exc = exc_info.value
    assert exc.status == 422
    assert exc.code == "SECRET_DETECTED_IN_PAYLOAD"
    assert exc.field == "summary"
    assert exc.extra is not None
    assert exc.extra["rule_id"] == "GITHUB_TOKEN"
    assert exc.extra["secret_kind"] == SecretKind.GITHUB_TOKEN.value
    assert exc.extra["fingerprint"].startswith("ghp_...")
    assert gh_token not in exc.extra["fingerprint"]


def test_negative_rejection_google_api_key() -> None:
    """Verify Google API keys trigger 422 ProblemException."""
    key = "AIzaSyA1234567890abcdefghijklmnopqrstuv"
    text = f"Config: {key}"
    with pytest.raises(ProblemException) as exc_info:
        enforce_secret_push_protection(text, field="content")

    exc = exc_info.value
    assert exc.status == 422
    assert exc.extra is not None
    assert exc.extra["rule_id"] == "GOOGLE_API_KEY"
    assert exc.extra["secret_kind"] == SecretKind.GOOGLE_KEY.value


def test_negative_rejection_slack_token() -> None:
    """Verify Slack bot/user tokens trigger 422 ProblemException."""
    token = "xoxb-" + "123456789012-abcdefghijklmnopqrstuvwx"
    text = f"Slack webhook token: {token}"
    with pytest.raises(ProblemException) as exc_info:
        enforce_secret_push_protection(text, field="body_markdown")

    exc = exc_info.value
    assert exc.status == 422
    assert exc.extra is not None
    assert exc.extra["rule_id"] == "SLACK_TOKEN"
    assert exc.extra["secret_kind"] == SecretKind.SLACK_TOKEN.value


def test_negative_rejection_connection_uri_password() -> None:
    """Verify connection URIs containing credentials trigger 422 ProblemException."""
    dsn = "postgresql://admin:s3cr3tP@ssw0rd99!@db.internal:5432/prod"
    text = f"Connect to {dsn}"
    with pytest.raises(ProblemException) as exc_info:
        enforce_secret_push_protection(text, field="body_markdown")

    exc = exc_info.value
    assert exc.status == 422
    assert exc.extra is not None
    assert exc.extra["rule_id"] == "CONNECTION_URI_PASSWORD"
    assert exc.extra["secret_kind"] == SecretKind.CONNECTION_URI.value
    assert "s3cr3tP@ssw0rd99!" not in exc.extra["fingerprint"]


def test_negative_rejection_high_entropy_assignment() -> None:
    """Verify .env style key assignments with high-entropy values trigger 422."""
    stripe_val = "sk_live_" + "51ABCDEF1234567890abcdefghijklmnopqrstuvwxyz"
    assignment = f'STRIPE_SECRET_KEY="{stripe_val}"'
    text = f"Settings:\n{assignment}"
    with pytest.raises(ProblemException) as exc_info:
        enforce_secret_push_protection(text, field="content")

    exc = exc_info.value
    assert exc.status == 422
    assert exc.extra is not None
    assert exc.extra["line"] == 2


def test_redact_on_write_mode() -> None:
    """Verify redact_on_write mode sanitizes text without raising exceptions."""
    token = "ghp_1234567890abcdef1234567890abcdef1234"
    text = f"Auth using {token} now"
    sanitized = enforce_secret_push_protection(
        text, field="description_markdown", mode=PushProtectionMode.REDACT_ON_WRITE
    )
    assert sanitized is not None
    assert token not in sanitized
    assert "[REDACTED:GITHUB_TOKEN]" in sanitized
    assert sanitized == "Auth using [REDACTED:GITHUB_TOKEN] now"


def test_activity_ledger_payload_guard_prose_rejection() -> None:
    """Verify record_activity rejects raw prose keys in payload."""
    # 1. Raw prose body in description_markdown is rejected
    raw_payload = {"description_markdown": "This is raw prose that must not be in payload"}
    with pytest.raises(ValueError, match="must be a 64-char SHA-256 digest"):
        _validate_and_scrub_payload(raw_payload)

    # 2. Raw prose in body_markdown is rejected
    with pytest.raises(ValueError, match="must be a 64-char SHA-256 digest"):
        _validate_and_scrub_payload({"body_markdown": "Comment text"})

    # 3. Valid SHA-256 hex digest is permitted
    valid_digest = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    cleaned = _validate_and_scrub_payload({"description_markdown": valid_digest})
    assert cleaned["description_markdown"] == valid_digest


def test_activity_ledger_payload_scrubs_nested_strings() -> None:
    """Verify record_activity scrubs all string values in payload."""
    secret = "ghp_1234567890abcdef1234567890abcdef1234"
    payload: dict[str, JSONValue] = {
        "field": "summary",
        "old": "old summary",
        "new": f"Updated summary with token {secret}",
        "nested": {"reason": f"Purged due to {secret}"},
        "items": [f"Item with {secret}", 123],
    }
    cleaned = _validate_and_scrub_payload(payload)
    assert secret not in str(cleaned["new"])
    assert "[REDACTED:GITHUB_TOKEN]" in str(cleaned["new"])
    nested = cleaned["nested"]
    assert isinstance(nested, dict)
    assert secret not in str(nested["reason"])
    assert "[REDACTED:GITHUB_TOKEN]" in str(nested["reason"])
    items = cleaned["items"]
    assert isinstance(items, list)
    assert secret not in str(items[0])
    assert "[REDACTED:GITHUB_TOKEN]" in str(items[0])
    assert items[1] == 123


def test_read_path_defense_in_depth_scrub_text() -> None:
    """Verify scrub_text handles read-time redaction."""
    token = "ghp_1234567890abcdef1234567890abcdef1234"
    assert scrub_text(f"Ticket: {token}") == "Ticket: [REDACTED:GITHUB_TOKEN]"
