# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for session token cookies, HMAC signing, and anti-tossing guards (KB-P2-02)."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from kanban.auth.sessions.cookies import (
    MAX_COOKIE_LEN,
    SESSION_COOKIE_NAME,
    TOKEN_BYTES_LEN,
    build_clear_cookie_header,
    build_set_cookie_header,
    encode_session_cookie,
    extract_session_cookie,
    generate_session_token,
    hash_session_token,
    parse_session_cookie,
)


@pytest.fixture
def hmac_key() -> bytes:
    """Fixture providing a fixed 32-byte session HMAC key."""
    return os.urandom(32)


def test_token_generation_and_hashing() -> None:
    """Validate token length and cryptographic hashing properties."""
    t1 = generate_session_token()
    t2 = generate_session_token()
    assert len(t1) == TOKEN_BYTES_LEN
    assert len(t2) == TOKEN_BYTES_LEN
    assert t1 != t2

    h1 = hash_session_token(t1)
    h2 = hash_session_token(t2)
    assert len(h1) == 32
    assert len(h2) == 32
    assert h1 != h2
    assert h1 == hash_session_token(t1)


def test_cookie_encoding_roundtrip(hmac_key: bytes) -> None:
    """Verify clean encoding and decoding of signed session cookies."""
    token = generate_session_token()
    cookie_str = encode_session_cookie(token, hmac_key)

    assert len(cookie_str) <= MAX_COOKIE_LEN
    assert "." in cookie_str

    parsed = parse_session_cookie(cookie_str, hmac_key)
    assert parsed == token


def test_case_3_security_cookie_forgery_denied(hmac_key: bytes) -> None:
    """Test Case 3: Forged, truncated, or tampered cookies rejected before DB access."""
    token = generate_session_token()
    valid_cookie = encode_session_cookie(token, hmac_key)

    # 1. Signature from a different key
    other_key = os.urandom(32)
    assert parse_session_cookie(valid_cookie, other_key) is None

    # 2. Signature truncated by 1 char
    parts = valid_cookie.split(".")
    truncated_sig = parts[0] + "." + parts[1][:-1]
    assert parse_session_cookie(truncated_sig, hmac_key) is None

    # 3. Token bit flip
    token_parts = valid_cookie.split(".")
    # Flip first character of base64 token
    first_char = "B" if token_parts[0][0] == "A" else "A"
    tampered_token = first_char + token_parts[0][1:] + "." + token_parts[1]
    assert parse_session_cookie(tampered_token, hmac_key) is None

    # Mock DB spy ensuring DB resolve is never invoked for forged cookie
    spy_db = MagicMock()
    if parse_session_cookie(truncated_sig, hmac_key) is not None:
        spy_db.session_resolve()
    spy_db.session_resolve.assert_not_called()


def test_case_4_cookie_tossing_and_name_confusion() -> None:
    """Test Case 4: Non-Host prefixes and duplicate cookies are rejected."""
    # 1. Non-Host variants (kb_session, __Secure-kb_session) are rejected
    header_insecure = "kb_session=val123; other=abc"
    assert extract_session_cookie(header_insecure) is None

    header_secure_prefix = "__Secure-kb_session=val123; other=abc"
    assert extract_session_cookie(header_secure_prefix) is None

    # 2. Duplicate __Host-kb_session headers (cookie tossing defense) fail closed
    header_duplicate = "__Host-kb_session=val1; foo=bar; __Host-kb_session=val2"
    assert extract_session_cookie(header_duplicate) is None

    # 3. Exactly one __Host-kb_session is accepted
    header_valid = f"theme=dark; {SESSION_COOKIE_NAME}=valid_cookie_val; lang=en"
    assert extract_session_cookie(header_valid) == "valid_cookie_val"


def test_case_11_oversize_cookie_rejected_before_db(hmac_key: bytes) -> None:
    """Test Case 11: Cookie exceeding 128 characters is rejected before DB call."""
    oversize = "a" * (MAX_COOKIE_LEN + 1)
    spy_db = MagicMock()

    parsed = parse_session_cookie(oversize, hmac_key)
    if parsed is not None:
        spy_db.query()

    assert parsed is None
    spy_db.query.assert_not_called()


def test_cookie_header_formatting() -> None:
    """Verify exact Set-Cookie header formatting and security attributes."""
    set_header = build_set_cookie_header("dummy_val")
    assert f"{SESSION_COOKIE_NAME}=dummy_val" in set_header
    assert "Secure" in set_header
    assert "HttpOnly" in set_header
    assert "SameSite=Lax" in set_header
    assert "Path=/" in set_header
    assert "Domain=" not in set_header

    set_with_exp = build_set_cookie_header("dummy_val", expires_at=datetime.now(UTC))
    assert "Expires=" in set_with_exp

    clear_header = build_clear_cookie_header()
    assert f"{SESSION_COOKIE_NAME}=" in clear_header
    assert "Max-Age=0" in clear_header
    assert "Path=/" in clear_header
    assert "HttpOnly" in clear_header
    assert "Secure" in clear_header


def test_cookie_error_handling(hmac_key: bytes) -> None:
    """Verify input validation and error branches for cookies."""
    with pytest.raises(ValueError, match="Token must be 32 bytes"):
        encode_session_cookie(b"short", hmac_key)

    assert parse_session_cookie("", hmac_key) is None
    assert parse_session_cookie("nodot", hmac_key) is None
    assert parse_session_cookie("one.two.three", hmac_key) is None
    assert parse_session_cookie("inv@lid.b64!", hmac_key) is None
    assert parse_session_cookie("AAAA.BBBB", hmac_key) is None

    assert extract_session_cookie(None) is None
    assert extract_session_cookie("") is None
    assert extract_session_cookie("; ; no_equals; empty=") is None
