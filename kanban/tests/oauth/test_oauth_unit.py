# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests targeting helper functions and boundary conditions for kanban.oauth."""

from __future__ import annotations

import base64
import time
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from joserfc import jwt
from starlette.requests import Request

from database.models.oauth import OAuthClient
from kanban.api.deps import PrincipalContext
from kanban.api.problems import format_validation_error
from kanban.api.v1.oauth import oauth_authorize
from kanban.auth.ldap.config import LdapCardConfig
from kanban.auth.oidc.config import OidcCardConfig
from kanban.auth.sessions.csrf import verify_same_origin_request
from kanban.oauth.jwt import (
    OAuthTokenError,
    _get_signing_eckey,
    get_jwks,
    mint_access_token,
    verify_access_token,
)
from kanban.oauth.server import (
    CONSENT_STYLE_SHA256,
    MAX_CODE_VERIFIER_LEN,
    OAuth2Error,
    RegistrationRateLimiter,
    check_registration_rate_limit,
    generate_consent_csrf_token,
    hash_token,
    parse_resource_target,
    parse_surface_from_resource,
    render_consent_screen,
    resolve_public_base_url,
    validate_redirect_uri,
    validate_registration_redirect_uris,
    verify_consent_csrf_token,
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

    # Verify rejection of wildcard in hostname with 422
    with pytest.raises(OAuth2Error) as exc_wild_host:
        validate_registration_redirect_uris(["https://*.evil.example/callback"])
    assert exc_wild_host.value.status_code == 422
    assert "wildcard" in exc_wild_host.value.description

    # Verify rejection of wildcard in path with 422
    with pytest.raises(OAuth2Error) as exc_wild_path:
        validate_registration_redirect_uris(["https://example.com/*/callback"])
    assert exc_wild_path.value.status_code == 422
    assert "wildcard" in exc_wild_path.value.description


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


def test_validate_registration_redirect_uris_fragments_and_userinfo() -> None:
    """Test rejection of fragment and userinfo in redirect URIs and IPv6 loopback acceptance."""
    # Fragment rejection
    with pytest.raises(OAuth2Error) as exc_frag:
        validate_registration_redirect_uris(["https://example.com/cb#fragment"])
    assert exc_frag.value.status_code == 400
    assert "fragment" in exc_frag.value.description

    # Userinfo rejection
    with pytest.raises(OAuth2Error) as exc_user:
        validate_registration_redirect_uris(["http://user:pass@127.0.0.1/cb"])
    assert exc_user.value.status_code == 400
    assert "userinfo" in exc_user.value.description

    # IPv6 loopback acceptance
    validate_registration_redirect_uris(
        [
            "http://[::1]:8080/callback",
            "http://::1:8080/callback",
        ]
    )


def test_parse_resource_target_scenarios() -> None:
    """Test parsing bare /mcp and scoped resource indicators."""
    assert parse_resource_target("https://auth.kanban/mcp") == ("agent", None, None)
    assert parse_resource_target("https://auth.kanban/mcp/w/demo-ws") == ("agent", "demo-ws", None)
    assert parse_resource_target("https://auth.kanban/mcp/w/demo-ws/p/PROJ") == (
        "agent",
        "demo-ws",
        "PROJ",
    )
    assert parse_resource_target("https://auth.kanban/mcp/agent/w/demo-ws/p/PROJ") == (
        "agent",
        "demo-ws",
        "PROJ",
    )
    assert parse_resource_target("https://auth.kanban/mcp/docs/w/demo-ws") == (
        "docs",
        "demo-ws",
        None,
    )
    assert parse_resource_target("https://auth.kanban/mcp/admin") == ("admin", None, None)

    # Invalid target
    with pytest.raises(OAuth2Error) as exc:
        parse_resource_target("https://auth.kanban/not-mcp")
    assert exc.value.status_code == 400
    assert exc.value.error == "invalid_target"


def test_render_consent_screen_with_descriptions_and_principal() -> None:
    """Test consent screen rendering with scope descriptions and signed-in principal display."""
    resp = render_consent_screen(
        client_name="Test Tool",
        redirect_uri="https://example.com/cb",
        surface="agent",
        requested_scopes=["agent:read", "agent:write"],
        state="st123",
        code_challenge="chal",
        code_challenge_method="S256",
        resource="https://auth.kanban/mcp",
        client_id="cid-99",
        csrf_token="csrf-99",  # noqa: S106
        principal_display="alice@test.local",
    )
    assert resp.status_code == 200
    body = bytes(resp.body).decode("utf-8")
    assert "Signed in as <strong>alice@test.local</strong>" in body
    assert "Read-only access to boards" in body
    assert "Read and write access to tickets" in body


def test_auth_card_config_normalizers() -> None:
    """Test alias normalization in OidcCardConfig and LdapCardConfig."""
    # OidcCardConfig
    oidc = OidcCardConfig.model_validate(
        {
            "kind": "OIDC",
            "issuer_url": "https://accounts.google.com",
            "token_auth_method": "private_key_jwt",
            "pkce_method": "S256",
            "client_id": "google-client-id",
        }
    )
    assert oidc.issuer == "https://accounts.google.com"
    assert oidc.client_auth == "private_key_jwt"

    # LdapCardConfig
    ldap = LdapCardConfig.model_validate(
        {
            "kind": "LDAP",
            "server_url": "ldap://ldap.example.com",
            "start_tls": True,
            "bind_dn": "cn=admin,dc=example,dc=com",
            "user_filter": "(&(objectClass=user)(sAMAccountName={username}))",
            "base_dn": "dc=example,dc=com",
            "spki_sha256_pin": "a" * 64,
        }
    )
    assert ldap.url == "ldap://ldap.example.com"
    assert ldap.transport_mode == "starttls"
    assert ldap.service_bind_dn == "cn=admin,dc=example,dc=com"
    assert ldap.user_search_filter == "(&(objectClass=user)(sAMAccountName={username}))"
    assert ldap.spki_sha256_pins == ["a" * 64]


def test_format_validation_error() -> None:
    """Test that format_validation_error strips pydantic documentation URLs."""
    raw = "Value error, extra field not permitted [URL: https://errors.pydantic.dev/2.10/v/extra_forbidden]"
    cleaned = format_validation_error(Exception(raw))
    assert "https://errors.pydantic.dev" not in cleaned
    assert "extra field not permitted" in cleaned


def test_consent_csrf_token_lifecycle() -> None:
    """Test HMAC-SHA256 consent CSRF token issuance, validation, and tampering resistance."""
    hmac_key = b"s" * 32
    session_id = uuid.uuid4()
    client_id = "test-client"
    redirect_uri = "http://127.0.0.1:8080/callback"
    code_challenge = "chal123"
    state = "state123"
    surface = "agent"

    token = generate_consent_csrf_token(
        session_hmac_key=hmac_key,
        session_id=session_id,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        state=state,
        surface=surface,
        ttl_seconds=300,
    )

    # Valid token passes
    assert verify_consent_csrf_token(
        token=token,
        session_hmac_key=hmac_key,
        session_id=session_id,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        state=state,
        surface=surface,
    )

    # Bound parameter mismatch fails
    assert not verify_consent_csrf_token(
        token=token,
        session_hmac_key=hmac_key,
        session_id=uuid.uuid4(),  # Different session
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        state=state,
        surface=surface,
    )
    assert not verify_consent_csrf_token(
        token=token,
        session_hmac_key=hmac_key,
        session_id=session_id,
        client_id="other-client",
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        state=state,
        surface=surface,
    )
    assert not verify_consent_csrf_token(
        token=token,
        session_hmac_key=hmac_key,
        session_id=session_id,
        client_id=client_id,
        redirect_uri="http://127.0.0.1:8080/other",
        code_challenge=code_challenge,
        state=state,
        surface=surface,
    )
    assert not verify_consent_csrf_token(
        token=token,
        session_hmac_key=hmac_key,
        session_id=session_id,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge="different-challenge",
        state=state,
        surface=surface,
    )
    assert not verify_consent_csrf_token(
        token=token,
        session_hmac_key=hmac_key,
        session_id=session_id,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        state="different-state",
        surface=surface,
    )
    assert not verify_consent_csrf_token(
        token=token,
        session_hmac_key=hmac_key,
        session_id=session_id,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        state=state,
        surface="docs",  # Different surface
    )

    # Expired token fails
    assert not verify_consent_csrf_token(
        token=token,
        session_hmac_key=hmac_key,
        session_id=session_id,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        state=state,
        surface=surface,
        now=time.time() + 301,
    )

    # Malformed tokens fail safely
    assert not verify_consent_csrf_token(
        token="",
        session_hmac_key=hmac_key,
        session_id=session_id,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        state=state,
        surface=surface,
    )
    assert not verify_consent_csrf_token(
        token="not-a-valid-token",  # noqa: S106
        session_hmac_key=hmac_key,
        session_id=session_id,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        state=state,
        surface=surface,
    )
    assert not verify_consent_csrf_token(
        token="invalidpayload.invalidsig",  # noqa: S106
        session_hmac_key=hmac_key,
        session_id=session_id,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        state=state,
        surface=surface,
    )


def test_render_consent_screen_security_headers_and_admin_surface() -> None:
    """Test consent screen styles hash CSP and admin surface warning banner."""
    resp_admin = render_consent_screen(
        client_name="Admin Tool",
        redirect_uri="http://127.0.0.1:8080/callback",
        surface="admin",
        requested_scopes=["admin:read", "admin:write"],
        state="st-admin",
        code_challenge="chal",
        code_challenge_method="S256",
        resource="https://auth.kanban/mcp/admin",
        client_id="cid-admin",
        csrf_token="csrf-test",  # noqa: S106
        principal_display="admin@domain.local",
    )
    assert resp_admin.status_code == 200
    csp = resp_admin.headers.get("content-security-policy", "")
    assert f"style-src 'self' 'sha256-{CONSENT_STYLE_SHA256}'" in csp
    assert "'unsafe-inline'" not in csp
    assert "http://[::1]:*" not in csp
    assert (
        "form-action 'self' http://127.0.0.1:* http://localhost:* https: http://127.0.0.1:8080;"
        in csp
    )

    resp_ipv6 = render_consent_screen(
        client_name="IPv6 Client",
        redirect_uri="http://[::1]:9090/cb",
        surface="agent",
        requested_scopes=["agent:read"],
        state="st-ipv6",
        code_challenge="chal",
        code_challenge_method="S256",
        resource="https://auth.kanban/mcp/agent",
        client_id="cid-ipv6",
        csrf_token="csrf-test",  # noqa: S106
    )
    csp_ipv6 = resp_ipv6.headers.get("content-security-policy", "")
    assert "http://[::1]:*" not in csp_ipv6
    assert "http://[::1]:9090" in csp_ipv6

    body = bytes(resp_admin.body).decode("utf-8")
    assert "admin@domain.local" in body
    assert "ADMIN" in body


def test_oauth_server_helpers_coverage() -> None:
    """Test hash_token, verify_pkce edge cases, and CSRF token format checks."""
    # hash_token
    h = hash_token("test-secret-token")
    assert len(h) == 32

    # verify_pkce_s256 length boundaries
    assert verify_pkce_s256("short", "chal") is False
    assert verify_pkce_s256("x" * 129, "chal") is False

    # CSRF format edge cases
    key = b"0" * 32
    assert (
        verify_consent_csrf_token(
            "",
            session_hmac_key=key,
            session_id=None,
            client_id="c",
            redirect_uri="http://127.0.0.1/cb",
            code_challenge="chal",
            state="st",
            surface="agent",
        )
        is False
    )
    assert (
        verify_consent_csrf_token(
            "no_dot_token",
            session_hmac_key=key,
            session_id=None,
            client_id="c",
            redirect_uri="http://127.0.0.1/cb",
            code_challenge="chal",
            state="st",
            surface="agent",
        )
        is False
    )
    assert (
        verify_consent_csrf_token(
            "not_an_int.signature",
            session_hmac_key=key,
            session_id=None,
            client_id="c",
            redirect_uri="http://127.0.0.1/cb",
            code_challenge="chal",
            state="st",
            surface="agent",
        )
        is False
    )

    # render_consent_screen without scheme/netloc in redirect_uri
    resp_noscheme = render_consent_screen(
        client_name="Client NoScheme",
        redirect_uri="relative/path/callback",
        surface="agent",
        requested_scopes=["agent:read"],
        state="st",
        code_challenge="chal",
        code_challenge_method="S256",
        resource="https://auth.kanban/mcp/agent",
        client_id="cid",
        csrf_token="csrf-test",  # noqa: S106
    )
    assert resp_noscheme.status_code == 200


def test_verify_same_origin_request_scenarios() -> None:
    """Test same-origin validation with Sec-Fetch-Site, Origin, and Referer headers."""
    # 1. Sec-Fetch-Site cross-site is rejected
    req_cross = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "server": ("127.0.0.1", 8000),
            "path": "/oauth/authorize/decision",
            "headers": [
                (b"host", b"127.0.0.1:8000"),
                (b"sec-fetch-site", b"cross-site"),
            ],
        }
    )
    assert not verify_same_origin_request(req_cross)

    # 2. Sec-Fetch-Site same-origin with matching origin is accepted
    req_same = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "server": ("127.0.0.1", 8000),
            "path": "/oauth/authorize/decision",
            "headers": [
                (b"host", b"127.0.0.1:8000"),
                (b"sec-fetch-site", b"same-origin"),
                (b"origin", b"http://127.0.0.1:8000"),
            ],
        }
    )
    assert verify_same_origin_request(req_same)

    # 3. Origin mismatch is rejected
    req_bad_origin = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "server": ("127.0.0.1", 8000),
            "path": "/oauth/authorize/decision",
            "headers": [
                (b"host", b"127.0.0.1:8000"),
                (b"sec-fetch-site", b"same-origin"),
                (b"origin", b"https://attacker.evil"),
            ],
        }
    )
    assert not verify_same_origin_request(req_bad_origin)

    # 4. Sec-Fetch-Site none without origin is accepted
    req_none = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "server": ("127.0.0.1", 8000),
            "path": "/oauth/authorize/decision",
            "headers": [
                (b"host", b"127.0.0.1:8000"),
                (b"sec-fetch-site", b"none"),
            ],
        }
    )
    assert verify_same_origin_request(req_none)

    # 5. Matching Referer is accepted when Origin is absent
    req_referer = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "server": ("127.0.0.1", 8000),
            "path": "/oauth/authorize/decision",
            "headers": [
                (b"host", b"127.0.0.1:8000"),
                (b"referer", b"http://127.0.0.1:8000/oauth/authorize"),
            ],
        }
    )
    assert verify_same_origin_request(req_referer)

    # 6. Mismatched Referer is rejected
    req_bad_referer = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "server": ("127.0.0.1", 8000),
            "path": "/oauth/authorize/decision",
            "headers": [
                (b"host", b"127.0.0.1:8000"),
                (b"referer", b"https://evil.attacker/oauth/authorize"),
            ],
        }
    )
    assert not verify_same_origin_request(req_bad_referer)

    # 7. Origin: null with Sec-Fetch-Site: same-origin is accepted (Referrer-Policy: no-referrer)
    req_null_same = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "server": ("127.0.0.1", 8000),
            "path": "/oauth/authorize/decision",
            "headers": [
                (b"host", b"127.0.0.1:8000"),
                (b"sec-fetch-site", b"same-origin"),
                (b"origin", b"null"),
            ],
        }
    )
    assert verify_same_origin_request(req_null_same)

    # 8. Origin: null with Sec-Fetch-Site: cross-site is rejected
    req_null_cross = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "server": ("127.0.0.1", 8000),
            "path": "/oauth/authorize/decision",
            "headers": [
                (b"host", b"127.0.0.1:8000"),
                (b"sec-fetch-site", b"cross-site"),
                (b"origin", b"null"),
            ],
        }
    )
    assert not verify_same_origin_request(req_null_cross)

    # 9. Origin: null with Sec-Fetch-Site: none is rejected
    req_null_none = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "server": ("127.0.0.1", 8000),
            "path": "/oauth/authorize/decision",
            "headers": [
                (b"host", b"127.0.0.1:8000"),
                (b"sec-fetch-site", b"none"),
                (b"origin", b"null"),
            ],
        }
    )
    assert not verify_same_origin_request(req_null_none)

    # 10. Origin: null with missing Sec-Fetch-Site is rejected
    req_null_missing = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "server": ("127.0.0.1", 8000),
            "path": "/oauth/authorize/decision",
            "headers": [
                (b"host", b"127.0.0.1:8000"),
                (b"origin", b"null"),
            ],
        }
    )
    assert not verify_same_origin_request(req_null_missing)


def test_resolve_public_base_url_and_parse_target(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test resolve_public_base_url env, headers, and fallback paths."""
    # 1. KANBAN_PUBLIC_ORIGIN env var
    monkeypatch.setenv("KANBAN_PUBLIC_ORIGIN", "https://custom.kanban.local/")
    assert resolve_public_base_url() == "https://custom.kanban.local"
    monkeypatch.delenv("KANBAN_PUBLIC_ORIGIN", raising=False)

    # 2. X-Forwarded-Proto and X-Forwarded-Host
    req_fwd = Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "server": ("127.0.0.1", 8000),
            "path": "/",
            "headers": [
                (b"x-forwarded-proto", b"https"),
                (b"x-forwarded-host", b"proxy.kanban.local"),
            ],
        }
    )
    assert resolve_public_base_url(req_fwd) == "https://proxy.kanban.local"

    # 3. No request fallback
    assert resolve_public_base_url(None) == "http://localhost:8000"

    # 4. Resource path without leading slash
    surface, ws, proj = parse_resource_target("mcp/agent")
    assert surface == "agent"
    assert ws is None
    assert proj is None


@pytest.mark.asyncio
async def test_oauth_authorize_fail_closed_missing_key_material(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When key_material and session_service are absent and cannot be loaded, raise RuntimeError."""
    monkeypatch.delenv("KANBAN_KEYRING_FILE", raising=False)
    monkeypatch.delenv("KANBAN_MASTER_KEK", raising=False)
    monkeypatch.delenv("KANBAN_SESSION_HMAC_KEY", raising=False)

    app = MagicMock()
    app.state.key_material = None
    app.state.session_service = None

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/oauth/authorize",
        "query_string": b"",
        "headers": [(b"host", b"localhost:8000")],
        "app": app,
    }
    req = Request(scope)
    caller = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        token_scopes=("auth",),
        aal_level=1,
        session_id=uuid.uuid4(),
    )
    resolver = AsyncMock()
    resolver.resolve.return_value = caller
    app.state.principal_resolver = resolver
    mock_session = AsyncMock()
    mock_client = OAuthClient(
        client_id="cid_1",
        client_name="Test App",
        client_type="public",
        redirect_uris=["http://127.0.0.1:8080/cb"],
        status="active",
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = mock_client
    result.all.return_value = []
    mock_session.execute.return_value = result

    with pytest.raises(RuntimeError, match="Session HMAC key material is not configured"):
        await oauth_authorize(
            request=req,
            session=mock_session,
            response_type="code",
            client_id="cid_1",
            redirect_uri="http://127.0.0.1:8080/cb",
            code_challenge="E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
            code_challenge_method="S256",
            state="state123",
        )


@pytest.mark.asyncio
async def test_oauth_authorize_rejects_inactive_client_statuses() -> None:
    """GET /oauth/authorize redirects inactive clients with unauthorized_client."""
    app = MagicMock()
    req = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/oauth/authorize",
            "query_string": b"",
            "headers": [(b"host", b"localhost:8000")],
            "app": app,
        }
    )
    caller = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        token_scopes=("auth",),
        aal_level=1,
        session_id=uuid.uuid4(),
    )
    resolver = AsyncMock()
    resolver.resolve.return_value = caller
    app.state.principal_resolver = resolver

    for inactive_status in ("suspended", "revoked", "pending_admin_approval", "disabled"):
        mock_session = AsyncMock()
        mock_client = OAuthClient(
            client_id="cid_1",
            client_name="Test App",
            client_type="public",
            redirect_uris=["http://127.0.0.1:8080/cb"],
            status=inactive_status,
        )
        result = MagicMock()
        result.scalar_one_or_none.return_value = mock_client
        mock_session.execute.return_value = result

        resp = await oauth_authorize(
            request=req,
            session=mock_session,
            response_type="code",
            client_id="cid_1",
            redirect_uri="http://127.0.0.1:8080/cb",
            code_challenge="E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
            code_challenge_method="S256",
            state="state123",
        )
        assert resp.status_code == 302
        assert f"error_description=client_{inactive_status}" in resp.headers["location"]
