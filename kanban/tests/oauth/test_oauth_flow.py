# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Comprehensive feature tests for OAuth 2.1 authorization server & MCP token flow (KB-P4-02b)."""

from __future__ import annotations

import base64
import hashlib
import importlib
import re
import secrets
import time
import urllib.parse
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from joserfc import jwt
from joserfc.jwk import OctKey
from sqlalchemy import text, update

from database.models.oauth import (
    OAuthAuthorizationCode,
    OAuthClient,
)
from kanban.api.deps import PrincipalContext
from kanban.oauth.jwt import (
    get_jwks,
    mint_access_token,
    verify_access_token,
)
from kanban.security.mcp_keys import create_internal_mcp_auth_header

if TYPE_CHECKING:
    from collections.abc import Callable

    from kanban.tests.api.conftest import ApiEnv

pytestmark = [pytest.mark.committed_db, pytest.mark.asyncio]


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def _extract_csrf(html_text: str) -> str:
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html_text)
    assert m is not None, "csrf_token input field not found in HTML"
    return m.group(1)


@pytest.fixture(autouse=True)
def setup_test_key_material(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up valid test key material in environment."""
    monkeypatch.delenv("KANBAN_KEYRING_FILE", raising=False)
    monkeypatch.setenv("KANBAN_MASTER_KEK", _b64(b"k" * 32))
    monkeypatch.setenv("KANBAN_AUTH_PEPPER", _b64(b"p" * 32))
    monkeypatch.setenv("KANBAN_SESSION_HMAC_KEY", _b64(b"s" * 32))
    monkeypatch.setenv("KANBAN_MASTER_KEK_KID", "test-kid-1")


class _InternalAuthTransport(httpx.AsyncBaseTransport):
    """Transport wrapping kanban app and injecting X-KB-Internal-Auth header."""

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        self.inner = inner

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        request.headers["x-kb-internal-auth"] = create_internal_mcp_auth_header()
        return await self.inner.handle_async_request(request)


def _setup_mcp_app(
    kanban_transport: httpx.AsyncBaseTransport,
    surface: str = "agent",
) -> tuple[httpx.AsyncClient, Any]:
    """Build in-process MCP server with McpAuthMiddleware wired to kanban app."""
    mcp_app_mod = importlib.import_module("mcp.app")
    mcp_auth_mod = importlib.import_module("mcp.auth")
    mcp_client_mod = importlib.import_module("mcp.internal_client")
    mcp_registry_mod = importlib.import_module("mcp.registry")
    mcp_settings_mod = importlib.import_module("mcp.settings")

    surf_enum = getattr(mcp_registry_mod.Surface, surface.upper())
    tool_registry_cls = mcp_registry_mod.ToolRegistry
    tool_spec_cls = mcp_registry_mod.ToolSpec
    create_placeholder_tool = mcp_registry_mod.create_placeholder_tool
    settings_cls = mcp_settings_mod.McpSettings
    kanban_client_cls = mcp_client_mod.KanbanApiClient
    create_mcp_app = mcp_app_mod.create_mcp_app
    mcp_auth_mw = mcp_auth_mod.McpAuthMiddleware
    set_tool_scope_requirements = mcp_auth_mod.set_tool_scope_requirements

    settings_inner = settings_cls(mode="standalone_inprocess", auth_enabled=False)
    settings_outer = settings_cls(mode="standalone_inprocess", auth_enabled=True)
    wrapped_transport = _InternalAuthTransport(kanban_transport)
    client_upstream = kanban_client_cls(settings_outer, transport=wrapped_transport)

    reg = tool_registry_cls(surf_enum)
    reg.register(create_placeholder_tool(surf_enum))

    async def _write_handler(_args: dict[str, Any]) -> dict[str, str]:
        return {"status": "created"}

    reg.register(
        tool_spec_cls(
            name="test_agent_write",
            description="Write tool requiring agent:write scope",
            surface=surf_enum,
            input_schema={"type": "object"},
            handler=_write_handler,
        )
    )
    set_tool_scope_requirements("test_agent_write", {"agent:write"})

    kwargs: dict[str, Any] = {"settings": settings_inner}
    if surface == "agent":
        kwargs["agent_registry"] = reg
    elif surface == "docs":
        kwargs["docs_registry"] = reg
    elif surface == "admin":
        kwargs["admin_registry"] = reg

    base_app = create_mcp_app(**kwargs)
    mw = mcp_auth_mw(
        base_app,
        surface=surf_enum,
        internal_client=client_upstream,
        settings=settings_outer,
    )
    mcp_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=mw),
        base_url="http://test",
    )
    return mcp_client, reg


def _generate_pkce() -> tuple[str, str]:
    """Generate PKCE verifier and S256 code challenge."""
    verifier = secrets.token_urlsafe(32)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


# =========================================================================
# Test Case 1: Positive Flow
# =========================================================================


async def test_case_1_positive_oauth_flow(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Any],
    as_principal: Callable[..., Any],
) -> None:
    """Test Case 1: Dynamic registration, authorize with S256, token exchange, MCP tools/list."""
    client = api_env.client
    redirect_uri = "http://127.0.0.1:8080/callback"
    resource = "http://test/mcp/agent"

    # 1. Dynamic Client Registration (RFC 7591)
    resp_reg = await client.post(
        "/oauth/register",
        json={
            "client_name": "Claude Code",
            "redirect_uris": [redirect_uri],
        },
    )
    assert resp_reg.status_code == 201
    reg_data = resp_reg.json()
    client_id = reg_data["client_id"]
    assert reg_data["client_name"] == "Claude Code"
    assert reg_data["status"] == "active"
    assert reg_data["client_type"] == "public"

    # 2. Setup user session and PKCE
    user = await make_user("alice", workspace_role="WORKSPACE_MEMBER")
    as_principal(user)
    verifier, challenge = _generate_pkce()
    state = "state-nonce-12345"

    # 3. GET /oauth/authorize -> Render consent screen
    resp_auth = await client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "resource": resource,
            "scope": "agent:read agent:write",
        },
    )
    assert resp_auth.status_code == 200
    assert "Authorize Claude Code" in resp_auth.text
    assert "Target MCP Surface" in resp_auth.text
    assert "AGENT" in resp_auth.text
    csrf_token = _extract_csrf(resp_auth.text)

    # 4. POST /oauth/authorize/decision -> Approve
    resp_decision = await client.post(
        "/oauth/authorize/decision",
        data={
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "resource": resource,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "action": "approve",
            "csrf_token": csrf_token,
            "scopes": ["agent:read", "agent:write"],
            "allowed_project_id": "__ALL__",
        },
        follow_redirects=False,
    )
    assert resp_decision.status_code == 302
    location = resp_decision.headers["location"]
    parsed_loc = urllib.parse.urlparse(location)
    qs = urllib.parse.parse_qs(parsed_loc.query)
    code = qs["code"][0]
    assert qs["state"][0] == state

    # 5. POST /oauth/token -> Authorization code exchange (unauthenticated machine request)
    api_env.resolver.principal = None
    resp_token = await client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
            "resource": resource,
        },
    )
    assert resp_token.status_code == 200
    token_data = resp_token.json()
    access_token = token_data["access_token"]
    assert "refresh_token" in token_data
    assert token_data["token_type"] == "Bearer"
    assert token_data["expires_in"] == 900
    assert "agent:read" in token_data["scope"]
    assert "agent:write" in token_data["scope"]

    # Verify JWT claims
    claims = verify_access_token(access_token)
    assert claims["aud"] == resource
    assert claims["sub"] == str(user.id)
    assert claims["ws"] == str(user.workspace_id)

    # Introspect directly to check active state
    resp_intro = await client.post(
        "/internal/v1/mcp/introspect",
        headers={"X-KB-Internal-Auth": create_internal_mcp_auth_header()},
        json={"token": access_token, "surface": "agent"},
    )
    assert resp_intro.json()["active"] is True

    # 6. Call MCP /mcp/agent with Bearer token -> tools/list succeeds
    raw_app = getattr(client._transport, "app", None)  # noqa: SLF001
    assert raw_app is not None
    mcp_client, _ = _setup_mcp_app(httpx.ASGITransport(app=raw_app), surface="agent")
    try:
        init_resp = await mcp_client.post(
            "/mcp/agent",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        )
        assert init_resp.status_code == 200
        session_id = init_resp.headers.get("mcp-session-id")
        assert session_id is not None

        resp_tools = await mcp_client.post(
            "/mcp/agent",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Mcp-Session-Id": session_id,
            },
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        assert resp_tools.status_code == 200
        tools_body = resp_tools.json()
        assert "result" in tools_body
        assert "tools" in tools_body["result"]
    finally:
        await mcp_client.aclose()


# =========================================================================
# Test Case 2: PKCE Security
# =========================================================================


async def test_case_2_pkce_security(
    api_env: ApiEnv,
    make_user: Callable[..., Any],
    as_principal: Callable[..., Any],
) -> None:
    """Test Case 2: plain method rejected with 400; wrong verifier -> 400; reuse -> 400."""
    client = api_env.client
    redirect_uri = "http://127.0.0.1:8080/callback"
    resource = "http://test/mcp/agent"

    # Register client
    resp_reg = await client.post(
        "/oauth/register",
        json={"client_name": "PKCE Test App", "redirect_uris": [redirect_uri]},
    )
    client_id = resp_reg.json()["client_id"]

    user = await make_user("bob", workspace_role="WORKSPACE_MEMBER")
    as_principal(user)
    verifier, challenge = _generate_pkce()

    # 2a. code_challenge_method=plain is rejected with 400 invalid_request
    resp_plain = await client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "plain",
            "state": "state1",
            "resource": resource,
        },
    )
    assert resp_plain.status_code == 400
    assert resp_plain.json()["error"] == "invalid_request"
    assert "S256" in resp_plain.json()["error_description"]

    # 2b. Authorize valid code
    resp_auth2 = await client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "state2",
            "resource": resource,
        },
    )
    assert resp_auth2.status_code == 200
    csrf_token2 = _extract_csrf(resp_auth2.text)

    resp_decision = await client.post(
        "/oauth/authorize/decision",
        data={
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "resource": resource,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "state2",
            "action": "approve",
            "csrf_token": csrf_token2,
            "scopes": ["agent:read"],
        },
        follow_redirects=False,
    )
    loc_query = urllib.parse.urlparse(resp_decision.headers["location"]).query
    code = urllib.parse.parse_qs(loc_query)["code"][0]

    # 2c. Wrong code_verifier returns 400 invalid_grant
    api_env.resolver.principal = None
    resp_wrong = await client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "code_verifier": "wrong-verifier-" + "x" * 32,
            "redirect_uri": redirect_uri,
            "resource": resource,
        },
    )
    assert resp_wrong.status_code == 400
    assert resp_wrong.json()["error"] == "invalid_grant"

    # 2d. Successful redemption with correct verifier
    resp_ok = await client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
            "resource": resource,
        },
    )
    assert resp_ok.status_code == 200
    first_token = resp_ok.json()["access_token"]

    # 2e. Code reuse returns 400 invalid_grant AND revokes entire grant family
    resp_reuse = await client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
            "resource": resource,
        },
    )
    assert resp_reuse.status_code == 400
    assert resp_reuse.json()["error"] == "invalid_grant"
    assert "already consumed" in resp_reuse.json()["error_description"]

    # Verify first token is now revoked via introspection
    resp_intro = await client.post(
        "/internal/v1/mcp/introspect",
        headers={"X-KB-Internal-Auth": create_internal_mcp_auth_header()},
        json={"token": first_token, "surface": "agent"},
    )
    assert resp_intro.status_code == 200
    assert resp_intro.json()["active"] is False


# =========================================================================
# Test Case 3: Audience Binding & Alg Confusion
# =========================================================================


async def test_case_3_audience_binding_and_alg_confusion(
    api_env: ApiEnv,
    make_user: Callable[..., Any],
    as_principal: Callable[..., Any],
) -> None:
    """Test Case 3: Agent JWT presented to admin -> 403; forged HS256 JWT -> rejected."""
    client = api_env.client
    redirect_uri = "http://127.0.0.1:8080/callback"
    resource = "http://test/mcp/agent"

    # Register client
    resp_reg = await client.post(
        "/oauth/register",
        json={"client_name": "Audience Test App", "redirect_uris": [redirect_uri]},
    )
    client_id = resp_reg.json()["client_id"]

    user = await make_user("carol", workspace_role="WORKSPACE_MEMBER")
    as_principal(user)
    verifier, challenge = _generate_pkce()

    # Authorize & mint token with resource=agent
    resp_auth3 = await client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "state3",
            "resource": resource,
        },
    )
    assert resp_auth3.status_code == 200
    csrf_token3 = _extract_csrf(resp_auth3.text)

    resp_decision = await client.post(
        "/oauth/authorize/decision",
        data={
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "resource": resource,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "state3",
            "action": "approve",
            "csrf_token": csrf_token3,
            "scopes": ["agent:read"],
        },
        follow_redirects=False,
    )
    loc_query = urllib.parse.urlparse(resp_decision.headers["location"]).query
    code = urllib.parse.parse_qs(loc_query)["code"][0]

    api_env.resolver.principal = None
    resp_token = await client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
            "resource": resource,
        },
    )
    agent_jwt = resp_token.json()["access_token"]

    # 3a. Present agent JWT to admin introspection -> active: false, reason: SURFACE_KEY_MISMATCH
    resp_intro_admin = await client.post(
        "/internal/v1/mcp/introspect",
        headers={"X-KB-Internal-Auth": create_internal_mcp_auth_header()},
        json={"token": agent_jwt, "surface": "admin"},
    )
    assert resp_intro_admin.status_code == 200
    assert resp_intro_admin.json()["active"] is False
    assert resp_intro_admin.json()["reason"] == "SURFACE_KEY_MISMATCH"

    # 3b. Present agent JWT to MCP admin server -> 403 SURFACE_KEY_MISMATCH
    raw_app = getattr(client._transport, "app", None)  # noqa: SLF001
    assert raw_app is not None
    mcp_admin_client, _ = _setup_mcp_app(httpx.ASGITransport(app=raw_app), surface="admin")
    try:
        resp_mcp = await mcp_admin_client.post(
            "/mcp/admin",
            headers={"Authorization": f"Bearer {agent_jwt}"},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
        assert resp_mcp.status_code == 403
        assert resp_mcp.json()["error"] == "SURFACE_KEY_MISMATCH"
    finally:
        await mcp_admin_client.aclose()

    # 3c. Alg confusion: Construct HS256 token using public key bytes
    jwks = get_jwks()
    pub_key_dict = jwks["keys"][0]
    pub_bytes = f"{pub_key_dict['x']}{pub_key_dict['y']}".encode("ascii")
    hs_key = OctKey.import_key(pub_bytes)

    header = {"alg": "HS256", "typ": "JWT", "kid": pub_key_dict["kid"]}
    now = int(time.time())
    payload = {
        "iss": "http://test",
        "sub": str(user.id),
        "aud": resource,
        "surface": "agent",
        "scope": "agent:read",
        "client_id": client_id,
        "grant_id": str(uuid.uuid4()),
        "jti": str(uuid.uuid4()),
        "ws": str(user.workspace_id),
        "iat": now,
        "exp": now + 900,
    }
    forged_jwt = jwt.encode(header, payload, hs_key)

    resp_forged_intro = await client.post(
        "/internal/v1/mcp/introspect",
        headers={"X-KB-Internal-Auth": create_internal_mcp_auth_header()},
        json={"token": forged_jwt, "surface": "agent"},
    )
    assert resp_forged_intro.status_code == 200
    assert resp_forged_intro.json()["active"] is False


# =========================================================================
# Test Case 4: Boundary Conditions
# =========================================================================


async def test_case_4_boundary_conditions(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Any],
    as_principal: Callable[..., Any],
) -> None:
    """Test Case 4: Expired code -> 400; expired token -> 401; RT reuse -> revoke; URI checks."""
    client = api_env.client
    redirect_uri = "http://127.0.0.1:8080/callback"
    resource = "http://test/mcp/agent"

    # 4a. 6 redirect URIs during registration -> 400
    resp_reg_invalid = await client.post(
        "/oauth/register",
        json={
            "client_name": "Too Many URIs",
            "redirect_uris": [f"http://127.0.0.1:808{i}/callback" for i in range(6)],
        },
    )
    assert resp_reg_invalid.status_code == 400
    assert "redirect" in resp_reg_invalid.json()["error_description"].lower()

    # Register valid client
    resp_reg = await client.post(
        "/oauth/register",
        json={"client_name": "Boundary Test App", "redirect_uris": [redirect_uri]},
    )
    client_id = resp_reg.json()["client_id"]

    user = await make_user("dave", workspace_role="WORKSPACE_MEMBER")
    as_principal(user)
    verifier, challenge = _generate_pkce()

    # 4b. redirect_uri with trailing slash difference -> rejected with 400 invalid_request
    resp_uri_diff = await client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri + "/",  # Trailing slash difference
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "state4",
            "resource": resource,
        },
    )
    assert resp_uri_diff.status_code == 400
    assert resp_uri_diff.json()["error"] == "invalid_request"

    # Authorize valid code
    resp_auth4 = await client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "state4",
            "resource": resource,
        },
    )
    assert resp_auth4.status_code == 200
    csrf_token4 = _extract_csrf(resp_auth4.text)

    resp_decision = await client.post(
        "/oauth/authorize/decision",
        data={
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "resource": resource,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "state4",
            "action": "approve",
            "csrf_token": csrf_token4,
            "scopes": ["agent:read"],
        },
        follow_redirects=False,
    )
    loc_q = urllib.parse.urlparse(resp_decision.headers["location"]).query
    code = urllib.parse.parse_qs(loc_q)["code"][0]

    # 4c. Code redeemed at 300s + 1 (expired) -> invalid_grant
    # Manipulate expires_at in DB
    code_sha = hashlib.sha256(code.encode("ascii")).digest()
    await api_env.seed.execute(
        update(OAuthAuthorizationCode)
        .where(OAuthAuthorizationCode.code_sha256 == code_sha)
        .values(expires_at=datetime.fromtimestamp(time.time() - 10, tz=UTC))
    )
    await api_env.seed.commit()

    api_env.resolver.principal = None
    resp_expired_code = await client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
            "resource": resource,
        },
    )
    assert resp_expired_code.status_code == 400
    assert resp_expired_code.json()["error"] == "invalid_grant"
    assert "expired" in resp_expired_code.json()["error_description"]

    # 4d. Access token at 900s + 1 -> expired
    expired_token = mint_access_token(
        issuer="http://test",
        subject=user.id,
        audience=resource,
        surface="agent",
        scopes=["agent:read"],
        client_id=client_id,
        grant_id=uuid.uuid4(),
        workspace_id=user.workspace_id,
        ttl_seconds=-10,  # Already expired
    )
    resp_expired_intro = await client.post(
        "/internal/v1/mcp/introspect",
        headers={"X-KB-Internal-Auth": create_internal_mcp_auth_header()},
        json={"token": expired_token, "surface": "agent"},
    )
    assert resp_expired_intro.status_code == 200
    assert resp_expired_intro.json()["active"] is False

    # 4e. Refresh token single-use rotation and reuse detection
    as_principal(user)
    v2, c2 = _generate_pkce()
    resp_auth2 = await client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": c2,
            "code_challenge_method": "S256",
            "state": "state4b",
            "resource": resource,
        },
    )
    assert resp_auth2.status_code == 200
    csrf_token2 = _extract_csrf(resp_auth2.text)

    resp_dec2 = await client.post(
        "/oauth/authorize/decision",
        data={
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "resource": resource,
            "code_challenge": c2,
            "code_challenge_method": "S256",
            "state": "state4b",
            "action": "approve",
            "csrf_token": csrf_token2,
            "scopes": ["agent:read"],
        },
        follow_redirects=False,
    )
    loc_query2 = urllib.parse.urlparse(resp_dec2.headers["location"]).query
    code2 = urllib.parse.parse_qs(loc_query2)["code"][0]

    api_env.resolver.principal = None
    resp_tok2 = await client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code2,
            "code_verifier": v2,
            "redirect_uri": redirect_uri,
            "resource": resource,
        },
    )
    rt1 = resp_tok2.json()["refresh_token"]

    # Redeem RT1 -> yields RT2 and token T2
    resp_refresh1 = await client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": rt1,
        },
    )
    assert resp_refresh1.status_code == 200
    rt2 = resp_refresh1.json()["refresh_token"]
    t2 = resp_refresh1.json()["access_token"]
    assert rt2 != rt1

    # Present old RT1 again -> reuse detection triggers!
    resp_reuse_rt = await client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": rt1,
        },
    )
    assert resp_reuse_rt.status_code == 400
    assert resp_reuse_rt.json()["error"] == "invalid_grant"
    assert "reuse detected" in resp_reuse_rt.json()["error_description"]

    # Verify entire family revoked: T2 and RT2 are now useless
    resp_t2_intro = await client.post(
        "/internal/v1/mcp/introspect",
        headers={"X-KB-Internal-Auth": create_internal_mcp_auth_header()},
        json={"token": t2, "surface": "agent"},
    )
    assert resp_t2_intro.status_code == 200
    assert resp_t2_intro.json()["active"] is False

    resp_rt2_retry = await client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": rt2,
        },
    )
    assert resp_rt2_retry.status_code == 400


# =========================================================================
# Test Case 5: Admin AAL & Client Approval Gate
# =========================================================================


async def test_case_5_admin_aal_and_approval_gate(
    api_env: ApiEnv,
    make_user: Callable[..., Any],
    as_principal: Callable[..., Any],
) -> None:
    """Test Case 5: AAL1 session for admin surface rejected; approval gate."""
    client = api_env.client
    redirect_uri = "http://127.0.0.1:8080/callback"
    admin_resource = "http://test/mcp/admin"

    # Register client
    resp_reg = await client.post(
        "/oauth/register",
        json={"client_name": "AAL Test App", "redirect_uris": [redirect_uri]},
    )
    client_id = resp_reg.json()["client_id"]

    # 5a. User at AAL1 requests /mcp/admin -> access_denied with aal2_required
    user_aal1 = await make_user("eve_aal1", workspace_role="WORKSPACE_ADMIN")
    as_principal(user_aal1)  # Default aal_level is 1
    _verifier, challenge = _generate_pkce()

    resp_admin_aal1 = await client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "state-aal1",
            "resource": admin_resource,
        },
        follow_redirects=False,
    )
    assert resp_admin_aal1.status_code == 302
    parsed_loc = urllib.parse.urlparse(resp_admin_aal1.headers["location"])
    qs = urllib.parse.parse_qs(parsed_loc.query)
    assert qs["error"][0] == "access_denied"
    assert qs["error_description"][0] == "aal2_required"

    # 5b. Client approval gate: require_admin_oauth_client_approval policy
    resp_reg_pending = await client.post(
        "/oauth/register",
        headers={"x-require-admin-oauth-client-approval": "true"},
        json={"client_name": "Pending App", "redirect_uris": [redirect_uri]},
    )
    assert resp_reg_pending.status_code == 201
    pending_client_id = resp_reg_pending.json()["client_id"]
    assert resp_reg_pending.json()["status"] == "pending_admin_approval"

    # Authorize with pending client -> rejected
    resp_auth_pending = await client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": pending_client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "state-pending",
            "resource": "http://test/mcp/agent",
        },
        follow_redirects=False,
    )
    assert resp_auth_pending.status_code == 302
    pending_loc_q = urllib.parse.urlparse(resp_auth_pending.headers["location"]).query
    qs_pending = urllib.parse.parse_qs(pending_loc_q)
    assert qs_pending["error"][0] == "unauthorized_client"
    assert qs_pending["error_description"][0] == "client_pending_admin_approval"

    # Attempt to approve with non-admin / AAL1 caller -> 403
    resp_patch_aal1 = await client.patch(
        f"/api/v1/admin/oauth-clients/{pending_client_id}",
        json={"status": "active"},
    )
    assert resp_patch_aal1.status_code == 403

    # Switch caller to AAL2 Workspace Admin (with confirmed TOTP factor for require_admin_aal2)
    await api_env.seed.execute(
        text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'test-kid-1')"),
        {
            "p_id": user_aal1.id,
            "blob": b"\x01" + b"\x00" * 28,
            "dek": b"\x01" + b"\x00" * 44,
        },
    )
    res_mfa = await api_env.seed.execute(
        text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
        {"p_id": user_aal1.id},
    )
    p_row = res_mfa.mappings().first()
    if p_row:
        await api_env.seed.execute(
            text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
            {"p_fid": p_row["id"]},
        )
    await api_env.seed.commit()

    api_env.resolver.principal = PrincipalContext(
        principal_id=user_aal1.id,
        workspace_id=user_aal1.workspace_id,
        token_scopes=("session",),
        aal_level=2,
    )

    resp_approve = await client.patch(
        f"/api/v1/admin/oauth-clients/{pending_client_id}",
        json={"status": "active"},
    )
    assert resp_approve.status_code == 200
    assert resp_approve.json()["status"] == "active"

    # Now authorize succeeds!
    resp_auth_approved = await client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": pending_client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "state-now-active",
            "resource": "http://test/mcp/agent",
        },
    )
    assert resp_auth_approved.status_code == 200
    assert "Authorize Pending App" in resp_auth_approved.text


# =========================================================================
# Test Case 6: Consent Narrowing & Deauthorization
# =========================================================================


async def test_case_6_consent_narrowing_and_deauthorization(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Any],
    make_project: Callable[..., Any],
    as_principal: Callable[..., Any],
) -> None:
    """Test Case 6: Narrow scope/project -> write tool rejected; RFC 7009 revoke -> 401."""
    client = api_env.client
    redirect_uri = "http://127.0.0.1:8080/callback"
    resource = "http://test/mcp/agent"

    user = await make_user("frank", workspace_role="WORKSPACE_MEMBER")
    project_kan = await make_project("KAN", created_by=user)
    as_principal(user)

    resp_reg = await client.post(
        "/oauth/register",
        json={"client_name": "Narrow App", "redirect_uris": [redirect_uri]},
    )
    client_id = resp_reg.json()["client_id"]
    verifier, challenge = _generate_pkce()

    # 6a. User approves decision with NARROWED scope (only agent:read) and project KAN
    resp_auth6 = await client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "state6",
            "resource": resource,
        },
    )
    assert resp_auth6.status_code == 200
    csrf_token6 = _extract_csrf(resp_auth6.text)

    resp_decision = await client.post(
        "/oauth/authorize/decision",
        data={
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "resource": resource,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "state6",
            "action": "approve",
            "csrf_token": csrf_token6,
            "scopes": ["agent:read"],  # Narrowed from requested read+write
            "allowed_project_id": str(project_kan),
        },
        follow_redirects=False,
    )
    loc_query = urllib.parse.urlparse(resp_decision.headers["location"]).query
    code = urllib.parse.parse_qs(loc_query)["code"][0]

    api_env.resolver.principal = None
    resp_token = await client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
            "resource": resource,
        },
    )
    access_token = resp_token.json()["access_token"]
    refresh_token = resp_token.json()["refresh_token"]

    # Verify introspection shows narrowed scopes and allowed projects
    resp_intro = await client.post(
        "/internal/v1/mcp/introspect",
        headers={"X-KB-Internal-Auth": create_internal_mcp_auth_header()},
        json={"token": access_token, "surface": "agent"},
    )
    intro_data = resp_intro.json()
    assert intro_data["scopes"] == ["agent:read"]
    assert intro_data["allowed_projects"] == [str(project_kan)]

    # 6b. Present token to MCP write tool -> rejected with INSUFFICIENT_SCOPE
    raw_app = getattr(client._transport, "app", None)  # noqa: SLF001
    assert raw_app is not None
    mcp_client, _ = _setup_mcp_app(httpx.ASGITransport(app=raw_app), surface="agent")
    try:
        # 1. MCP initialize
        init_resp = await mcp_client.post(
            "/mcp/agent",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        )
        assert init_resp.status_code == 200
        session_id = init_resp.headers.get("mcp-session-id")

        headers = {"Authorization": f"Bearer {access_token}"}
        if session_id:
            headers["Mcp-Session-Id"] = session_id

        resp_tool_write = await mcp_client.post(
            "/mcp/agent",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "test_agent_write", "arguments": {}},
            },
        )
        assert resp_tool_write.status_code == 200
        tool_res = resp_tool_write.json()["result"]
        assert tool_res["isError"] is True
        assert "INSUFFICIENT_SCOPE" in tool_res["content"][0]["text"]
    finally:
        await mcp_client.aclose()

    # 6c. User self-service listing: GET /api/v1/auth/oauth-grants
    as_principal(user)
    resp_grants = await client.get("/api/v1/auth/oauth-grants")
    assert resp_grants.status_code == 200
    grants_list = resp_grants.json()
    assert len(grants_list) >= 1
    assert isinstance(uuid.UUID(grants_list[0]["id"]), uuid.UUID)

    # 6d. RFC 7009 revocation via POST /oauth/revoke
    api_env.resolver.principal = None
    resp_revoke = await client.post(
        "/oauth/revoke",
        data={"token": access_token, "token_type_hint": "access_token"},
    )
    assert resp_revoke.status_code == 200

    # Introspection is now inactive
    resp_intro_revoked = await client.post(
        "/internal/v1/mcp/introspect",
        headers={"X-KB-Internal-Auth": create_internal_mcp_auth_header()},
        json={"token": access_token, "surface": "agent"},
    )
    assert resp_intro_revoked.json()["active"] is False

    # Calling /oauth/token with the refresh token is now rejected
    resp_rt_revoked = await client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": refresh_token,
        },
    )
    assert resp_rt_revoked.status_code == 400

    # 6e. Verify self-service DELETE /api/v1/auth/oauth-grants/{grant_id}
    # Create another grant
    as_principal(user)
    v3, c3 = _generate_pkce()
    resp_auth3 = await client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": c3,
            "code_challenge_method": "S256",
            "state": "state6c",
            "resource": resource,
        },
    )
    assert resp_auth3.status_code == 200
    csrf_token3 = _extract_csrf(resp_auth3.text)

    resp_dec3 = await client.post(
        "/oauth/authorize/decision",
        data={
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "resource": resource,
            "code_challenge": c3,
            "code_challenge_method": "S256",
            "state": "state6c",
            "action": "approve",
            "csrf_token": csrf_token3,
            "scopes": ["agent:read"],
        },
        follow_redirects=False,
    )
    loc_q3 = urllib.parse.urlparse(resp_dec3.headers["location"]).query
    code3 = urllib.parse.parse_qs(loc_q3)["code"][0]
    api_env.resolver.principal = None
    resp_tok3 = await client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code3,
            "code_verifier": v3,
            "redirect_uri": redirect_uri,
            "resource": resource,
        },
    )
    tok3 = resp_tok3.json()["access_token"]

    as_principal(user)
    grants_after = (await client.get("/api/v1/auth/oauth-grants")).json()
    new_grant_id = grants_after[0]["id"]

    resp_del_grant = await client.delete(f"/api/v1/auth/oauth-grants/{new_grant_id}")
    assert resp_del_grant.status_code == 204

    # Introspect tok3 -> inactive
    resp_tok3_intro = await client.post(
        "/internal/v1/mcp/introspect",
        headers={"X-KB-Internal-Auth": create_internal_mcp_auth_header()},
        json={"token": tok3, "surface": "agent"},
    )
    assert resp_tok3_intro.json()["active"] is False


# =========================================================================
# Test Case 7: Metadata & Security Invariants
# =========================================================================


async def test_case_7_metadata_and_security_invariants(
    api_env: ApiEnv,
) -> None:
    """Test Case 7: RFC 8414 AS metadata, JWKS, and query parameter ban on access_token."""
    client = api_env.client

    # 7a. RFC 8414 Authorization Server Metadata
    resp_meta = await client.get("/.well-known/oauth-authorization-server")
    assert resp_meta.status_code == 200
    meta = resp_meta.json()
    assert meta["issuer"] == "http://test"
    assert meta["authorization_endpoint"] == "http://test/oauth/authorize"
    assert meta["token_endpoint"] == "http://test/oauth/token"
    assert meta["revocation_endpoint"] == "http://test/oauth/revoke"
    assert meta["registration_endpoint"] == "http://test/oauth/register"
    assert meta["jwks_uri"] == "http://test/oauth/jwks.json"
    assert meta["code_challenge_methods_supported"] == ["S256"]
    assert "authorization_code" in meta["grant_types_supported"]
    assert "refresh_token" in meta["grant_types_supported"]

    # 7b. JWKS Endpoint
    resp_jwks = await client.get("/oauth/jwks.json")
    assert resp_jwks.status_code == 200
    jwks = resp_jwks.json()
    assert "keys" in jwks
    assert len(jwks["keys"]) >= 1
    key_entry = jwks["keys"][0]
    assert key_entry["kty"] == "EC"
    assert key_entry["crv"] == "P-256"
    assert key_entry["use"] == "sig"
    assert key_entry["alg"] == "ES256"

    # 7c. Query parameter prohibition: ?access_token=... must return 400 on all OAuth endpoints
    endpoints_to_test = [
        ("GET", "/.well-known/oauth-authorization-server"),
        ("GET", "/oauth/jwks.json"),
        ("POST", "/oauth/register"),
        ("GET", "/oauth/authorize"),
        ("POST", "/oauth/token"),
        ("POST", "/oauth/revoke"),
    ]
    for method, path in endpoints_to_test:
        if method == "GET":
            resp = await client.get(f"{path}?access_token=leak123")
        else:
            resp = await client.post(f"{path}?access_token=leak123")
        assert resp.status_code == 400
        assert resp.json()["error"] == "invalid_request"
        err_desc = resp.json()["error_description"]
        assert "access_token parameter in query string is strictly forbidden" in err_desc


async def test_case_8_rfc7591_dynamic_registration_metadata_and_validation(
    api_env: ApiEnv,
) -> None:
    """Test Case 8: RFC 7591 dynamic client registration fields, defaults & validation."""
    client = api_env.client
    redirect_uri = "http://127.0.0.1:8080/cb"

    # 1. Extra fields ignored cleanly without 422 error
    resp_extra = await client.post(
        "/oauth/register",
        json={
            "client_name": "Test Extra App",
            "redirect_uris": [redirect_uri],
            "arbitrary_client_field": "some_extra_metadata",
            "software_id": "test-client-1.0",
        },
    )
    assert resp_extra.status_code == 201
    data_extra = resp_extra.json()
    assert data_extra["client_name"] == "Test Extra App"
    assert data_extra["token_endpoint_auth_method"] == "none"
    assert "authorization_code" in data_extra["grant_types"]

    # 2. Blank or omitted client_name defaults to 'MCP Client'
    resp_blank = await client.post(
        "/oauth/register",
        json={"redirect_uris": [redirect_uri]},
    )
    assert resp_blank.status_code == 201
    assert resp_blank.json()["client_name"] == "MCP Client"

    # 3. Valid grant_types accepted
    resp_grants = await client.post(
        "/oauth/register",
        json={
            "client_name": "Grants App",
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
        },
    )
    assert resp_grants.status_code == 201
    assert resp_grants.json()["grant_types"] == ["authorization_code", "refresh_token"]

    # 4. Invalid grant_types rejected with 400 invalid_client_metadata
    resp_bad_grant = await client.post(
        "/oauth/register",
        json={
            "client_name": "Bad Grant App",
            "redirect_uris": [redirect_uri],
            "grant_types": ["password", "implicit"],
        },
    )
    assert resp_bad_grant.status_code == 400
    assert resp_bad_grant.json()["error"] == "invalid_client_metadata"

    # 5. Invalid token_endpoint_auth_method rejected
    resp_bad_auth = await client.post(
        "/oauth/register",
        json={
            "client_name": "Bad Auth App",
            "redirect_uris": [redirect_uri],
            "token_endpoint_auth_method": "client_secret_post",
        },
    )
    assert resp_bad_auth.status_code == 400
    assert resp_bad_auth.json()["error"] == "invalid_client_metadata"


async def test_case_9_unauthenticated_authorize_browser_redirect_vs_json_api(
    api_env: ApiEnv,
) -> None:
    """Test Case 9: Unauthenticated /oauth/authorize redirects browser or returns 401 for JSON."""
    client = api_env.client
    redirect_uri = "http://127.0.0.1:8080/callback"
    _verifier, challenge = _generate_pkce()

    # Register client
    resp_reg = await client.post(
        "/oauth/register",
        json={"client_name": "Login Test App", "redirect_uris": [redirect_uri]},
    )
    client_id = resp_reg.json()["client_id"]

    # Ensure unauthenticated caller
    api_env.resolver.principal = None

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": "state-login-test",
        "resource": "http://test/mcp/agent",
    }

    # 1. Browser request (Accept: text/html) -> Redirects 302 to /login?next=...
    resp_browser = await client.get(
        "/oauth/authorize",
        params=params,
        headers={"Accept": "text/html,application/xhtml+xml"},
        follow_redirects=False,
    )
    assert resp_browser.status_code == 302
    assert resp_browser.headers["location"].startswith("/login?next=")

    # 2. JSON API request (Accept: application/json) -> Returns 401 ProblemException
    resp_json = await client.get(
        "/oauth/authorize",
        params=params,
        headers={"Accept": "application/json"},
    )
    assert resp_json.status_code == 401
    assert resp_json.json()["code"] == "AUTHENTICATION_REQUIRED"

    # 3. Invalid parameter unauthenticated -> Still returns OAuth error (checked before auth)
    bad_params = dict(params)
    bad_params["code_challenge_method"] = "plain"
    resp_bad = await client.get(
        "/oauth/authorize",
        params=bad_params,
        headers={"Accept": "text/html"},
    )
    assert resp_bad.status_code == 400
    assert resp_bad.json()["error"] == "invalid_request"


async def test_case_10_scoped_resource_indicators_and_bare_mcp(
    api_env: ApiEnv,
    make_user: Callable[..., Any],
    as_principal: Callable[..., Any],
) -> None:
    """Test Case 10: Scoped resource indicators (/mcp, /mcp/w/..., /mcp/agent/w/.../p/...)."""
    client = api_env.client
    redirect_uri = "http://127.0.0.1:8080/callback"
    resource = "http://test/mcp"

    user = await make_user("george", workspace_role="WORKSPACE_MEMBER")
    as_principal(user)
    _verifier, challenge = _generate_pkce()

    resp_reg = await client.post(
        "/oauth/register",
        json={"client_name": "Bare MCP App", "redirect_uris": [redirect_uri]},
    )
    client_id = resp_reg.json()["client_id"]

    # 1. Authorize with bare /mcp resource (defaults to agent surface)
    resp_auth = await client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "state-bare",
            "resource": resource,
        },
    )
    assert resp_auth.status_code == 200
    assert "AGENT" in resp_auth.text
    assert "Signed in as" in resp_auth.text

    # 2. RFC 9728 metadata at /.well-known/oauth-protected-resource
    resp_meta = await client.get("/.well-known/oauth-protected-resource")
    assert resp_meta.status_code == 200
    meta = resp_meta.json()
    assert meta["resource"].endswith("/mcp/agent")
    assert "agent:read" in meta["scopes_supported"]

    # 3. Authorize without resource parameter defaults to /mcp/agent and emits consent CSP
    resp_no_res = await client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "state-no-res",
        },
    )
    assert resp_no_res.status_code == 200
    assert "AGENT" in resp_no_res.text
    csp = resp_no_res.headers.get("content-security-policy", "")
    assert "sha256-" in csp
    assert "'unsafe-inline'" not in csp
    assert "http://127.0.0.1:*" in csp

    # 4. Unauthenticated browser request to /oauth/authorize redirects to relative /login?next=...
    api_env.resolver.principal = None
    resp_unauth = await client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "state-unauth",
        },
        headers={"Accept": "text/html"},
        follow_redirects=False,
    )
    assert resp_unauth.status_code == 302
    loc = resp_unauth.headers["location"]
    assert loc.startswith("/login?next=%2Foauth%2Fauthorize%3F")


async def test_case_11_mcp_api_key_label_and_project_scoping(
    api_env: ApiEnv,
    make_user: Callable[..., Any],
    make_project: Callable[..., Any],
    as_principal: Callable[..., Any],
) -> None:
    """Test Case 11: Personal MCP key minting with label and allowed_projects."""
    client = api_env.client
    user = await make_user("helen", workspace_role="WORKSPACE_ADMIN")
    _project = await make_project("HEL", created_by=user)
    as_principal(user)

    # 1. Mint personal key with label and project key
    resp_mint = await client.post(
        "/api/v1/auth/mcp-keys",
        json={
            "surface": "agent",
            "scopes": ["agent:read", "agent:write"],
            "label": "My Personal Assistant Key",
            "allowed_projects": ["HEL"],
        },
    )
    assert resp_mint.status_code == 201
    mint_data = resp_mint.json()
    assert mint_data["label"] == "My Personal Assistant Key"
    assert "HEL" in (mint_data["allowed_projects"] or [])

    # 2. List personal keys
    resp_list = await client.get("/api/v1/auth/mcp-keys")
    assert resp_list.status_code == 200
    keys = resp_list.json()["keys"]
    target_key = next((k for k in keys if k["id"] == mint_data["id"]), None)
    assert target_key is not None
    assert target_key["label"] == "My Personal Assistant Key"


# =========================================================================
# Test Case 12: Decision CSRF and Policy Hardening (KAN-28)
# =========================================================================


async def test_case_12_decision_csrf_and_policy_hardening(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Any],
    as_principal: Callable[..., Any],
) -> None:
    """Test Case 12: Validate CSRF tokens, origin enforcement, client status, and AAL2 policy."""
    client = api_env.client
    redirect_uri = "http://127.0.0.1:8080/callback"
    resource = "http://test/mcp/agent"

    user = await make_user("ian", workspace_role="WORKSPACE_ADMIN")
    as_principal(user)
    _v, challenge = _generate_pkce()

    resp_reg = await client.post(
        "/oauth/register",
        json={"client_name": "Hardened Policy Client", "redirect_uris": [redirect_uri]},
    )
    client_id = resp_reg.json()["client_id"]

    # 1. GET /oauth/authorize to get genuine CSRF token
    resp_auth = await client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "state12",
            "resource": resource,
        },
    )
    assert resp_auth.status_code == 200
    csrf_token = _extract_csrf(resp_auth.text)

    # 2. Decision with missing CSRF token -> 403 CSRF_INVALID
    resp_no_csrf = await client.post(
        "/oauth/authorize/decision",
        data={
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "resource": resource,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "state12",
            "action": "approve",
            "scopes": ["agent:read"],
        },
        follow_redirects=False,
    )
    assert resp_no_csrf.status_code == 403
    assert resp_no_csrf.json()["code"] == "CSRF_INVALID"

    # 3. Decision with tampered CSRF token -> 403 CSRF_INVALID
    resp_bad_csrf = await client.post(
        "/oauth/authorize/decision",
        data={
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "resource": resource,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "state12",
            "action": "approve",
            "csrf_token": csrf_token + "tampered",
            "scopes": ["agent:read"],
        },
        follow_redirects=False,
    )
    assert resp_bad_csrf.status_code == 403
    assert resp_bad_csrf.json()["code"] == "CSRF_INVALID"

    # 4. Decision with cross-site Sec-Fetch-Site -> 403 CSRF_INVALID
    resp_cross = await client.post(
        "/oauth/authorize/decision",
        data={
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "resource": resource,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "state12",
            "action": "approve",
            "csrf_token": csrf_token,
            "scopes": ["agent:read"],
        },
        headers={"Sec-Fetch-Site": "cross-site"},
        follow_redirects=False,
    )
    assert resp_cross.status_code == 403
    assert resp_cross.json()["code"] == "CSRF_INVALID"

    # 5. Empty scopes approved -> 302 redirect with invalid_scope
    resp_empty_scopes = await client.post(
        "/oauth/authorize/decision",
        data={
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "resource": resource,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "state12",
            "action": "approve",
            "csrf_token": csrf_token,
            "scopes": [],
        },
        follow_redirects=False,
    )
    assert resp_empty_scopes.status_code == 302
    loc_empty = urllib.parse.urlparse(resp_empty_scopes.headers["location"])
    params_empty = urllib.parse.parse_qs(loc_empty.query)
    assert params_empty["error"][0] == "invalid_scope"

    # 6. Surface is admin, caller has AAL1 -> GET /oauth/authorize redirects
    # with access_denied and error_description=aal2_required
    admin_resource = "http://test/mcp/admin"
    resp_auth_admin_aal1 = await client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "state-admin",
            "resource": admin_resource,
        },
        follow_redirects=False,
    )
    assert resp_auth_admin_aal1.status_code == 302
    loc_admin_aal1 = urllib.parse.urlparse(resp_auth_admin_aal1.headers["location"])
    params_admin_aal1 = urllib.parse.parse_qs(loc_admin_aal1.query)
    assert params_admin_aal1["error"][0] == "access_denied"
    assert "aal2" in params_admin_aal1.get("error_description", [""])[0].lower()

    # Elevate ian to AAL2 to obtain consent page and token
    api_env.resolver.principal = PrincipalContext(
        principal_id=user.id,
        workspace_id=user.workspace_id,
        token_scopes=("session",),
        aal_level=2,
    )
    resp_auth_admin_aal2 = await client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "state-admin",
            "resource": admin_resource,
        },
    )
    assert resp_auth_admin_aal2.status_code == 200
    csrf_token_admin = _extract_csrf(resp_auth_admin_aal2.text)

    # Now step caller back down to AAL1 -> decision route enforces AAL2
    # and rejects with 302 access_denied
    api_env.resolver.principal = PrincipalContext(
        principal_id=user.id,
        workspace_id=user.workspace_id,
        token_scopes=("session",),
        aal_level=1,
    )
    resp_admin_aal1 = await client.post(
        "/oauth/authorize/decision",
        data={
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "resource": admin_resource,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "state-admin",
            "action": "approve",
            "csrf_token": csrf_token_admin,
            "scopes": ["admin:read"],
        },
        follow_redirects=False,
    )
    assert resp_admin_aal1.status_code == 302
    loc_aal = urllib.parse.urlparse(resp_admin_aal1.headers["location"])
    params_aal = urllib.parse.parse_qs(loc_aal.query)
    assert params_aal["error"][0] == "access_denied"
    assert "aal2" in params_aal.get("error_description", [""])[0].lower()

    # 7. Action deny -> 302 redirect with access_denied
    resp_deny = await client.post(
        "/oauth/authorize/decision",
        data={
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "resource": resource,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "state12",
            "action": "deny",
            "csrf_token": csrf_token,
            "scopes": ["agent:read"],
        },
        follow_redirects=False,
    )
    assert resp_deny.status_code == 302
    loc_deny = urllib.parse.urlparse(resp_deny.headers["location"])
    params_deny = urllib.parse.parse_qs(loc_deny.query)
    assert params_deny["error"][0] == "access_denied"

    # 8. Client disabled status -> 302 redirect with unauthorized_client
    await api_env.seed.execute(
        update(OAuthClient).where(OAuthClient.client_id == client_id).values(status="disabled")
    )
    await api_env.seed.commit()

    resp_disabled = await client.post(
        "/oauth/authorize/decision",
        data={
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "resource": resource,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "state12",
            "action": "approve",
            "csrf_token": csrf_token,
            "scopes": "agent:read",
        },
        follow_redirects=False,
    )
    assert resp_disabled.status_code == 302
    loc_dis = urllib.parse.urlparse(resp_disabled.headers["location"])
    params_dis = urllib.parse.parse_qs(loc_dis.query)
    assert params_dis["error"][0] == "unauthorized_client"


# =========================================================================
# Test Case 13: Admin OAuth Client Registration (KAN-28)
# =========================================================================


async def test_case_13_admin_register_oauth_client(
    api_env: ApiEnv,
    make_user: Callable[..., Any],
    as_principal: Callable[..., Any],
) -> None:
    """Test Case 13: Admin registration of OAuth client with AAL2, auditing, and validations."""
    client = api_env.client
    user = await make_user("admin_user", workspace_role="WORKSPACE_ADMIN")
    as_principal(user)

    # 1. Non-AAL2 caller is rejected with 403
    resp_non_aal2 = await client.post(
        "/api/v1/admin/oauth-clients",
        json={
            "client_name": "Audited Enterprise App",
            "redirect_uris": ["https://app.enterprise.internal/callback"],
            "token_endpoint_auth_method": "none",
        },
    )
    assert resp_non_aal2.status_code == 403

    # 2. Enroll TOTP MFA factor and elevate to AAL2
    await api_env.seed.execute(
        text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'test-kid-1')"),
        {
            "p_id": user.id,
            "blob": b"\x01" + b"\x00" * 28,
            "dek": b"\x01" + b"\x00" * 44,
        },
    )
    res_mfa = await api_env.seed.execute(
        text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
        {"p_id": user.id},
    )
    p_row = res_mfa.mappings().first()
    if p_row:
        await api_env.seed.execute(
            text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
            {"p_fid": p_row["id"]},
        )
    await api_env.seed.commit()

    api_env.resolver.principal = PrincipalContext(
        principal_id=user.id,
        workspace_id=user.workspace_id,
        token_scopes=("session",),
        aal_level=2,
    )

    # 3. Successful admin registration
    resp_create = await client.post(
        "/api/v1/admin/oauth-clients",
        json={
            "client_name": "Audited Enterprise App",
            "redirect_uris": [
                "https://app.enterprise.internal/callback",
                "http://127.0.0.1:9000/callback",
            ],
            "token_endpoint_auth_method": "none",
        },
    )
    assert resp_create.status_code == 201
    created_data = resp_create.json()
    assert created_data["client_name"] == "Audited Enterprise App"
    assert created_data["status"] == "active"
    assert created_data["client_type"] == "public"
    assert created_data["token_endpoint_auth_method"] == "none"
    assert len(created_data["redirect_uris"]) == 2
    assert "client_id" in created_data
    registered_client_id = created_data["client_id"]

    # 4. Verify client exists and is active in admin list
    resp_list = await client.get("/api/v1/admin/oauth-clients")
    assert resp_list.status_code == 200
    clients = resp_list.json()
    matching = next((c for c in clients if c["client_id"] == registered_client_id), None)
    assert matching is not None
    assert matching["status"] == "active"

    # 5. Invalid redirect URI (non-loopback plain HTTP) is rejected with 400
    resp_bad_uri = await client.post(
        "/api/v1/admin/oauth-clients",
        json={
            "client_name": "Insecure App",
            "redirect_uris": ["http://insecure.example.com/callback"],
        },
    )
    assert resp_bad_uri.status_code == 400

    # 6. Invalid token_endpoint_auth_method is rejected with 400
    resp_bad_auth = await client.post(
        "/api/v1/admin/oauth-clients",
        json={
            "client_name": "Bad Auth App",
            "redirect_uris": ["https://app.example.com/callback"],
            "token_endpoint_auth_method": "client_secret_post",
        },
    )
    assert resp_bad_auth.status_code == 400

    # 7. Invalid client_type is rejected with 400
    resp_bad_type = await client.post(
        "/api/v1/admin/oauth-clients",
        json={
            "client_name": "Confidential App",
            "redirect_uris": ["https://app.example.com/callback"],
            "client_type": "confidential",
        },
    )
    assert resp_bad_type.status_code == 400


# =========================================================================
# Test Case 14: Decision Security with Origin: null under Referrer-Policy
# =========================================================================


async def test_oauth_authorize_decision_origin_null_referrer_policy_security(
    api_env: ApiEnv,
    make_user: Callable[..., Any],
    as_principal: Callable[..., Any],
) -> None:
    """Security test: Prove POST /oauth/authorize/decision under Origin: null.

    Under WHATWG Fetch spec with Referrer-Policy: no-referrer, Chromium form POST sends
    Origin: null and Sec-Fetch-Site: same-origin. Verify:
    a) Origin: null + Sec-Fetch-Site: same-origin + valid HMAC csrf_token -> 302 redirect with code
    b) Origin: null + Sec-Fetch-Site: cross-site -> 403 CSRF_INVALID
    c) Origin: null + Sec-Fetch-Site: none or missing -> 403 CSRF_INVALID
    d) Origin: null + Sec-Fetch-Site: same-origin + forged csrf_token -> 403 CSRF_INVALID
    """
    client = api_env.client
    redirect_uri = "http://127.0.0.1:8080/callback"
    resource = "http://test/mcp/agent"

    user = await make_user("origin_null_user", workspace_role="WORKSPACE_ADMIN")
    as_principal(user)
    _v, challenge = _generate_pkce()

    resp_reg = await client.post(
        "/oauth/register",
        json={"client_name": "Origin Null Test Client", "redirect_uris": [redirect_uri]},
    )
    assert resp_reg.status_code == 201
    client_id = resp_reg.json()["client_id"]

    resp_auth = await client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "state-null-origin",
            "resource": resource,
        },
    )
    assert resp_auth.status_code == 200
    csrf_token = _extract_csrf(resp_auth.text)

    decision_data = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "resource": resource,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": "state-null-origin",
        "action": "approve",
        "csrf_token": csrf_token,
        "scopes": ["agent:read"],
    }

    # b) Origin: null + Sec-Fetch-Site: cross-site -> 403 CSRF_INVALID
    resp_b = await client.post(
        "/oauth/authorize/decision",
        data=decision_data,
        headers={"Origin": "null", "Sec-Fetch-Site": "cross-site"},
        follow_redirects=False,
    )
    assert resp_b.status_code == 403
    assert resp_b.json()["code"] == "CSRF_INVALID"

    # c1) Origin: null + Sec-Fetch-Site: none -> 403 CSRF_INVALID
    resp_c1 = await client.post(
        "/oauth/authorize/decision",
        data=decision_data,
        headers={"Origin": "null", "Sec-Fetch-Site": "none"},
        follow_redirects=False,
    )
    assert resp_c1.status_code == 403
    assert resp_c1.json()["code"] == "CSRF_INVALID"

    # c2) Origin: null + missing Sec-Fetch-Site -> 403 CSRF_INVALID
    resp_c2 = await client.post(
        "/oauth/authorize/decision",
        data=decision_data,
        headers={"Origin": "null"},
        follow_redirects=False,
    )
    assert resp_c2.status_code == 403
    assert resp_c2.json()["code"] == "CSRF_INVALID"

    # d) Origin: null + Sec-Fetch-Site: same-origin + forged csrf_token -> 403 CSRF_INVALID
    forged_data = dict(decision_data)
    forged_data["csrf_token"] = csrf_token + "forged"
    resp_d = await client.post(
        "/oauth/authorize/decision",
        data=forged_data,
        headers={"Origin": "null", "Sec-Fetch-Site": "same-origin"},
        follow_redirects=False,
    )
    assert resp_d.status_code == 403
    assert resp_d.json()["code"] == "CSRF_INVALID"

    # a) Origin: null + Sec-Fetch-Site: same-origin + valid HMAC csrf_token -> 302 code redirect
    resp_a = await client.post(
        "/oauth/authorize/decision",
        data=decision_data,
        headers={"Origin": "null", "Sec-Fetch-Site": "same-origin"},
        follow_redirects=False,
    )
    assert resp_a.status_code == 302
    loc = urllib.parse.urlparse(resp_a.headers["location"])
    params = urllib.parse.parse_qs(loc.query)
    assert "code" in params
    assert len(params["code"][0]) > 10
    assert params["state"][0] == "state-null-origin"
