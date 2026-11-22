# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Comprehensive unit test suite for push_protection module (KB-SEC-SCRUB-01)."""

from __future__ import annotations

import pytest

from kanban.api.problems import ProblemException
from kanban.security.push_protection import (
    PUSH_PROTECTION_CODE_ALIAS,
    enforce_secret_push_protection,
    is_exempt_token,
    mask_fingerprint,
    redact_text_findings,
    scan_text_for_secrets,
)
from kanban.security.scrubber import SecretKind


def test_push_protection_empty_inputs() -> None:
    """Verify empty or None inputs pass cleanly."""
    assert enforce_secret_push_protection(None, field="summary") is None
    assert enforce_secret_push_protection("", field="summary") == ""
    assert scan_text_for_secrets("") == []


def test_push_protection_deterministic_rules() -> None:
    """Verify each deterministic rule detects the secret and provides correct metadata."""
    cases = [
        ("kb_pat_1234567890abcdef1234567890", "KANBAN_TOKEN", SecretKind.KANBAN_KEY),
        ("kb_eat_1234567890abcdef1234567890", "KANBAN_TOKEN", SecretKind.KANBAN_KEY),
        ("ghp_1234567890abcdef1234567890abcdef1234", "GITHUB_TOKEN", SecretKind.GITHUB_TOKEN),
        ("glpat-1234567890abcdefghij", "GITLAB_TOKEN", SecretKind.GITLAB_TOKEN),
        ("AKIAIOSFODNN7EXAMPLE", "AWS_ACCESS_KEY", SecretKind.AWS_ACCESS_KEY),
        ("xoxb-" + "123456789012-abcdefghijklmnopqrstuvwx", "SLACK_TOKEN", SecretKind.SLACK_TOKEN),
        ("AIzaSy" + "A1234567890abcdefghijklmnopqrstuv", "GOOGLE_API_KEY", SecretKind.GOOGLE_KEY),
        (
            "sk_live_" + "51ABCDEF1234567890abcdefghijklmnopqrstuvwxyz",
            "STRIPE_KEY",
            SecretKind.STRIPE_KEY,
        ),
        (
            (
                "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0."
                "doNotLeakThisSignature12345"
            ),
            "BEARER_TOKEN",
            SecretKind.BEARER_TOKEN,
        ),
    ]

    for secret_val, expected_rule, expected_kind in cases:
        findings = scan_text_for_secrets(f"Prefix {secret_val} suffix")
        assert len(findings) >= 1, f"Failed to detect {secret_val}"
        match = next(f for f in findings if f.rule_id == expected_rule)
        assert match.kind == expected_kind
        assert match.fingerprint != secret_val


def test_push_protection_custom_code_alias() -> None:
    """Verify custom error code alias can be passed."""
    secret = "ghp_1234567890abcdef1234567890abcdef1234"
    with pytest.raises(ProblemException) as exc_info:
        enforce_secret_push_protection(secret, field="summary", code=PUSH_PROTECTION_CODE_ALIAS)
    assert exc_info.value.code == PUSH_PROTECTION_CODE_ALIAS


def test_redact_text_findings_multiple_findings() -> None:
    """Verify redact_text_findings correctly replaces multiple findings in one text."""
    secret1 = "ghp_1234567890abcdef1234567890abcdef1234"
    secret2 = "AKIAIOSFODNN7EXAMPLE"
    text = f"First: {secret1}, Second: {secret2}."
    findings = scan_text_for_secrets(text)
    assert len(findings) == 2

    redacted = redact_text_findings(text, findings)
    assert secret1 not in redacted
    assert secret2 not in redacted
    assert redacted == "First: [REDACTED:GITHUB_TOKEN], Second: [REDACTED:AWS_ACCESS_KEY]."


def test_mask_fingerprint_short_secrets() -> None:
    """Verify mask_fingerprint handles short secrets gracefully."""
    # <= 8 characters gets fully masked with asterisks
    very_short = "secret1"
    masked_very_short = mask_fingerprint(very_short)
    assert masked_very_short == "*******"

    # > 8 characters with known prefix longer than remaining space
    long_prefix_short_secret = "github_pat_12"
    masked = mask_fingerprint(long_prefix_short_secret)
    assert masked.startswith("gith")
    assert masked.endswith("12")
    assert "..." in masked


def test_is_exempt_token_edge_cases() -> None:
    """Verify is_exempt_token edge cases for empty and short tokens."""
    assert is_exempt_token("") is True
    assert is_exempt_token("short") is True
    assert is_exempt_token("1234567") is True
    assert is_exempt_token("placeholder") is True
    assert is_exempt_token("https://example.com/api") is True


def test_push_protection_openai_anthropic_gemini_rules() -> None:
    """Verify OpenAI, Anthropic, and Gemini/Vertex keys are correctly detected."""
    anthropic_key = "sk-ant-api03-abcdef1234567890abcdef1234567890"
    findings_anthropic = scan_text_for_secrets(f"Header: {anthropic_key}")
    assert any(f.rule_id == "OPENAI_ANTHROPIC_KEY" for f in findings_anthropic)

    openai_key = "sk-proj-abcdef1234567890abcdef1234567890"
    findings_openai = scan_text_for_secrets(f"Key: {openai_key}")
    assert any(f.rule_id == "OPENAI_ANTHROPIC_KEY" for f in findings_openai)

    # sk- prefix with only lowercase and no digits or mixed case is ignored
    plain_sk = "sk-abcdefghijklmnopqrstuvwxyz"
    findings_plain = scan_text_for_secrets(f"Plain: {plain_sk}")
    assert not any(f.rule_id == "OPENAI_ANTHROPIC_KEY" for f in findings_plain)

    gemini_key = "AQ.1234567890abcdef1234567890"
    findings_gemini = scan_text_for_secrets(f"Key: {gemini_key}")
    assert any(f.rule_id == "GEMINI_VERTEX_KEY" for f in findings_gemini)


def test_connection_uri_exempt_and_redis() -> None:
    """Verify connection URIs with exempt passwords pass, and redis URIs are detected."""
    # Exempt password in connection URI
    exempt_uri = "postgresql://user:example@localhost:5432/db"
    assert scan_text_for_secrets(exempt_uri) == []

    # Redis URI with exempt password
    redis_exempt = "redis://:example@localhost:6379/0"
    assert scan_text_for_secrets(redis_exempt) == []

    # Redis URI with secret password
    redis_uri = "redis://:s3cr3tP@ssw0rd99!@localhost:6379/0"
    redis_findings = scan_text_for_secrets(redis_uri)
    assert any(f.rule_id == "CONNECTION_URI_PASSWORD" for f in redis_findings)

    # Rediss URI with secret password
    rediss_uri = "rediss://:s3cr3tP@ssw0rd99!@localhost:6379/0"
    rediss_findings = scan_text_for_secrets(rediss_uri)
    assert any(f.rule_id == "CONNECTION_URI_PASSWORD" for f in rediss_findings)


def test_candidate_entropy_token_without_alpha() -> None:
    """Verify high entropy tokens without both digits and letters are skipped."""
    # High entropy token with symbols and digits only (no letters)
    symbol_digit_token = "+=-_!@#$1234567890+=-_!@#$"
    assert scan_text_for_secrets(f"Val: {symbol_digit_token}") == []


def test_key_value_assignment_low_entropy() -> None:
    """Verify low entropy assignments without mixed classes or punctuation are skipped."""
    low_entropy = 'PASSWORD = "alllowercase"'
    assert scan_text_for_secrets(low_entropy) == []


def test_scan_text_allow_markers_false() -> None:
    """Verify scan_text_for_secrets respects allow_markers=False."""
    secret = "ghp_1234567890abcdef1234567890abcdef1234"
    text = f"{secret}  # kb-allow-secret: verified-test"
    # With allow_markers=True, findings are suppressed
    assert scan_text_for_secrets(text, allow_markers=True) == []
    # With allow_markers=False, findings are not suppressed
    findings = scan_text_for_secrets(text, allow_markers=False)
    assert len(findings) >= 1
    assert findings[0].rule_id == "GITHUB_TOKEN"


def test_redact_text_findings_empty() -> None:
    """Verify redact_text_findings returns original text when findings is empty."""
    assert redact_text_findings("clean text", []) == "clean text"
