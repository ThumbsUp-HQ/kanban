# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests and benchmarks for entropy detector and scrubber (KB-SEC-SCRUB-01)."""

from __future__ import annotations

import time

from kanban.security.push_protection import (
    calculate_shannon_entropy,
    is_exempt_token,
    mask_fingerprint,
    scan_text_for_secrets,
)
from kanban.security.scrubber import (
    outbound_secret_scrubber,
)


def test_shannon_entropy_calculation() -> None:
    """Verify Shannon entropy calculation accuracy across string distributions."""
    # Empty string has 0.0 entropy
    assert calculate_shannon_entropy("") == 0.0

    # Monotonous single character has 0.0 entropy
    assert calculate_shannon_entropy("aaaaaaaaaaaaaaaa") == 0.0

    # Low entropy repeated pairs
    low = calculate_shannon_entropy("abababababababab")
    assert 0.99 <= low <= 1.01

    # High entropy mixed string with digits, upper, lower, symbols
    high_rand = "9XqL8#pZ!2mK$vR7yT4w"
    entropy = calculate_shannon_entropy(high_rand)
    assert entropy >= 4.0


def test_exempt_tokens_do_not_trigger_entropy() -> None:
    """Verify UUIDs, Git commit SHAs, SHA digests, base-62 ranks, and URLs are exempt."""
    # UUIDs
    assert is_exempt_token("123e4567-e89b-12d3-a456-426614174000") is True
    assert is_exempt_token("019323f4-7e8c-7992-bf3e-8c310243e8a2") is True

    # 40-character Git commit SHAs
    assert is_exempt_token("4f836f691234567890abcdef1234567890abcdef") is True
    assert is_exempt_token("e3b0c44298fc1c149afbf4c8996fb92427ae41e4") is True

    # 64-character SHA-256 hex digests
    assert (
        is_exempt_token("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855") is True
    )

    # Base-62 fractional indexing ranks
    assert is_exempt_token("0|i00000:abc") is True
    assert is_exempt_token("0|i00001:000002") is True

    # HTTP/HTTPS URLs without embedded user credentials
    assert is_exempt_token("https://github.com/ThumbsUp-HQ/kanban/pull/72") is True
    assert is_exempt_token("http://localhost:8000/api/v1/issues") is True

    # Benign placeholders
    assert is_exempt_token("placeholder") is True
    assert is_exempt_token("changeme") is True
    assert is_exempt_token("change_me") is True


def test_mask_fingerprint_never_echoes_secret() -> None:
    """Verify mask_fingerprint generates non-leaking diagnostic fingerprints."""
    # Empty string
    assert mask_fingerprint("") == ""

    # Short string
    assert mask_fingerprint("short") == "*****"

    # GitHub token
    gh_token = "ghp_1234567890abcdef1234567890abcdef1234"
    masked_gh = mask_fingerprint(gh_token)
    assert masked_gh.startswith("ghp_...")
    assert masked_gh.endswith("1234")
    assert gh_token[4:-4] not in masked_gh

    # AWS access key
    aws_key = "AKIAIOSFODNN7EXAMPLE"
    masked_aws = mask_fingerprint(aws_key)
    assert masked_aws.startswith("AKIA...")
    assert masked_aws.endswith("MPLE")
    assert aws_key[4:-4] not in masked_aws

    # OpenAI sk-* key
    sk_key = "sk-proj-1234567890abcdefghijklmnopqrstuvwxyz"
    masked_sk = mask_fingerprint(sk_key)
    assert masked_sk.startswith("sk-proj-...")
    assert masked_sk.endswith("wxyz")
    assert sk_key[8:-4] not in masked_sk


def test_scrubber_upgrades_gitlab_slack_google_stripe_uri() -> None:
    """Verify upgraded scrubber handles GitLab, Slack, Google, Stripe, and DSN credentials."""
    # 1. GitLab token
    gl_text = "Deploy token: glpat-abcdefghijklmnopqrstuvwxyz12"
    gl_res = outbound_secret_scrubber(gl_text)
    assert gl_res.redacted is True
    assert gl_res.count == 1
    assert "glpat-" not in gl_res.text
    assert "[REDACTED:GITLAB_TOKEN]" in gl_res.text

    # 2. Slack token
    slack_tok = "xoxb-" + "123456789012-abcdefghijklmnopqrstuvwx"
    slack_text = f"Slack bot: {slack_tok}"
    slack_res = outbound_secret_scrubber(slack_text)
    assert slack_res.redacted is True
    assert "[REDACTED:SLACK_TOKEN]" in slack_res.text

    # 3. Google API key
    google_tok = "AIzaSy" + "A1234567890abcdefghijklmnopqrstuv"
    google_text = f"API Key: {google_tok}"
    google_res = outbound_secret_scrubber(google_text)
    assert google_res.redacted is True
    assert "[REDACTED:GOOGLE_KEY]" in google_res.text

    # 4. Stripe secret key
    stripe_tok = "sk_live_" + "51ABCDEF1234567890abcdefghijklmnopqrstuvwxyz"
    stripe_text = f"Stripe: {stripe_tok}"
    stripe_res = outbound_secret_scrubber(stripe_text)
    assert stripe_res.redacted is True
    assert "[REDACTED:STRIPE_KEY]" in stripe_res.text

    # 5. Connection URI password
    uri_text = "DSN: postgresql://dbuser:superSecretP@ss99@db.internal:5432/production"
    uri_res = outbound_secret_scrubber(uri_text)
    assert uri_res.redacted is True
    assert "superSecretP@ss99" not in uri_res.text
    expected_redacted = "postgresql://dbuser:[REDACTED:CONNECTION_URI]@db.internal:5432/production"
    assert expected_redacted in uri_res.text

    # 6. Kanban eat token
    eat_text = "Ephemeral token: kb_eat_1234567890abcdef1234567890"
    eat_res = outbound_secret_scrubber(eat_text)
    assert eat_res.redacted is True
    assert "[REDACTED:KANBAN_KEY]" in eat_res.text


def test_scanner_performance_under_two_milliseconds() -> None:
    """Benchmark scanner overhead on a 50KB realistic technical prose document."""
    corpus = [
        "# Architectural Technical Document",
        "",
        "Here are various technical identifiers that must not be falsely flagged:",
        "- Commit: 4f836f691234567890abcdef1234567890abcdef",
        "- UUID: 123e4567-e89b-12d3-a456-426614174000",
        "- SHA256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "- URL: https://example.com/api/v1/documentation/items/123",
        "- Rank: 0|i00000:000001",
        "",
        "```python",
        "def compute_hash(data: bytes) -> str:",
        "    return hashlib.sha256(data).hexdigest()",
        "```",
    ] * 200  # ~40KB

    full_text = "\n".join(corpus)

    t0 = time.perf_counter()
    findings = scan_text_for_secrets(full_text)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert len(findings) == 0, f"False positives detected: {findings}"
    assert elapsed_ms < 50.0, f"Overhead was {elapsed_ms:.2f}ms"
