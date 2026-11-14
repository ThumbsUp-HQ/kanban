# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests targeting helper functions and boundary conditions for kanban.oauth."""

from __future__ import annotations

import base64
import time
import uuid

import pytest
from joserfc import jwt

from kanban.oauth.jwt import (
    OAuthTokenError,
    _get_signing_eckey,
    get_jwks,
    mint_access_token,
    verify_access_token,
)
from kanban.oauth.server import (
    MAX_CODE_VERIFIER_LEN,
    OAuth2Error,
    RegistrationRateLimiter,
    check_registration_rate_limit,
    parse_surface_from_resource,
    render_consent_screen,
    validate_redirect_uri,
    validate_registration_redirect_uris,
    verify_pkce_s256,
)


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


@pytest.fixture(autouse=True)
def setup_test_key_material(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up valid test key material in environment."""
    monkeypatch.delenv("KANBAN_KEYRING_FILE", raising=False)
    monkeypatch.setenv("KANBAN_MASTER_KEK", _b64(b"k" * 32))
    monkeypatch.setenv("KANBAN_AUTH_PEPPER", _b64(b"p" * 32))
    monkeypatch.setenv("KANBAN_SESSION_HMAC_KEY", _b64(b"s" * 32))
    monkeypatch.setenv("KANBAN_MASTER_KEK_KID", "test-kid-1")


def test_verify_pkce_s256_boundaries() -> None:
    """Test PKCE code verifier length and character boundaries."""
    # Under minimum
    assert not verify_pkce_s256("short", "challenge")
    # Over maximum
    assert not verify_pkce_s256("x" * (MAX_CODE_VERIFIER_LEN + 1), "challenge")
    # Non-ascii
    assert not verify_pkce_s256("x" * 43 + "\u2014", "challenge")


def test_validate_redirect_uri() -> None:
    """Exact string match required."""
    assert validate_redirect_uri("https://example.com/cb", ["https://example.com/cb"])
    assert not validate_redirect_uri("https://example.com/other", ["https://example.com/cb"])


def test_validate_registration_redirect_uris_errors() -> None:
    """Test constraints on redirect URIs during dynamic registration."""
    # Valid uris pass without error
    validate_registration_redirect_uris(
        [
            "https://example.com/callback",
            "http://127.0.0.1:8080/callback",
            "http://localhost:3000/callback",
        ]
    )

    # Empty
    with pytest.raises(OAuth2Error) as exc_empty:
        validate_registration_redirect_uris([])
    assert exc_empty.value.status_code == 400
    assert "At least one" in exc_empty.value.description

    # Over 5
    with pytest.raises(OAuth2Error) as exc_max:
        validate_registration_redirect_uris([f"https://example.com/{i}" for i in range(6)])
    assert exc_max.value.status_code == 400
    assert "Maximum 5" in exc_max.value.description

    # Plain HTTP non-loopback
    with pytest.raises(OAuth2Error) as exc_http:
        validate_registration_redirect_uris(["http://example.com/cb"])
    assert exc_http.value.status_code == 400

    # Non-HTTP scheme
    with pytest.raises(OAuth2Error) as exc_ftp:
        validate_registration_redirect_uris(["ftp://127.0.0.1/cb"])
    assert exc_ftp.value.status_code == 400


def test_registration_rate_limiter() -> None:
    """Rate limiter enforces sliding window per IP."""
    limiter = RegistrationRateLimiter(limit=2, window_s=10.0)
    assert limiter.check("1.2.3.4")
    assert limiter.check("1.2.3.4")
    assert not limiter.check("1.2.3.4")

    # Helper function raises 429
    for _ in range(100):
        check_registration_rate_limit("192.168.1.50")
    with pytest.raises(OAuth2Error) as exc:
        check_registration_rate_limit("192.168.1.50")
    assert exc.value.status_code == 429


def test_parse_surface_from_resource() -> None:
    """Test surface extraction and rejection."""
    assert parse_surface_from_resource("https://host/mcp/agent") == "agent"
    assert parse_surface_from_resource("https://host/mcp/docs/") == "docs"
    assert parse_surface_from_resource("https://host/mcp/admin") == "admin"

    with pytest.raises(OAuth2Error) as exc:
        parse_surface_from_resource("https://host/mcp/unknown")
    assert exc.value.status_code == 400
    assert exc.value.error == "invalid_target"


def test_render_consent_screen_with_projects() -> None:
    """Test consent screen rendering with available projects list."""
    p_id = uuid.uuid4()
    resp = render_consent_screen(
        client_name="Test Client",
        redirect_uri="https://example.com/cb",
        surface="agent",
        requested_scopes=["agent:read"],
        state="state-123",
        code_challenge="chal",
        code_challenge_method="S256",
        resource="https://host/mcp/agent",
        client_id="cid-1",
        csrf_token="csrf-1",  # noqa: S106
        available_projects=[(p_id, "Project Alpha")],
    )
    assert resp.status_code == 200
    body_text = bytes(resp.body).decode("utf-8")
    assert "Project Alpha" in body_text
    assert str(p_id) in body_text


def test_verify_access_token_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test error branches in verify_access_token."""
    sub = uuid.uuid4()
    ws = uuid.uuid4()
    grant = uuid.uuid4()
    valid_tok = mint_access_token(
        issuer="https://auth",
        subject=sub,
        audience="https://host/mcp/agent",
        surface="agent",
        scopes=["agent:read"],
        client_id="cid-1",
        grant_id=grant,
        workspace_id=ws,
    )

    # 1. Surface URL match and mismatch
    claims = verify_access_token(valid_tok, expected_surface_url="https://host/mcp/agent")
    assert claims["sub"] == str(sub)

    with pytest.raises(OAuthTokenError) as exc_aud:
        verify_access_token(valid_tok, expected_surface_url="https://host/mcp/docs")
    assert exc_aud.value.code == "SURFACE_KEY_MISMATCH"

    # 2. Expired token
    with pytest.raises(OAuthTokenError) as exc_exp:
        verify_access_token(valid_tok, now=time.time() + 1000)
    assert "expired" in str(exc_exp.value)

    # 3. Missing exp claim
    key, _ = _get_signing_eckey()
    header = {"alg": "ES256", "typ": "JWT", "kid": "test-kid"}
    no_exp_tok = jwt.encode(header, {"sub": str(sub)}, key)
    with pytest.raises(OAuthTokenError) as exc_noexp:
        verify_access_token(no_exp_tok)
    assert "missing valid exp" in str(exc_noexp.value)

    # 4. Non-ES256 algorithm via mocked decode result
    class _MockToken:
        def __init__(self) -> None:
            self.header = {"alg": "ES384", "typ": "JWT"}
            self.claims = {"sub": str(sub), "exp": time.time() + 3600}

    monkeypatch.setattr(jwt, "decode", lambda _t, _k: _MockToken())
    with pytest.raises(OAuthTokenError) as exc_alg:
        verify_access_token(valid_tok)
    assert "Forbidden algorithm" in str(exc_alg.value)


def test_get_jwks_cache() -> None:
    """Test JWKS endpoint caching returns same structure."""
    jwks1 = get_jwks()
    jwks2 = get_jwks()
    assert jwks1 == jwks2
    assert len(jwks1["keys"]) >= 1
