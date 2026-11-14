# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Comprehensive feature tests for OAuth 2.1 authorization server & MCP token flow (KB-P4-02b)."""

from __future__ import annotations

import base64
import hashlib
import importlib
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
from sqlalchemy import update

from database.models.oauth import (
    OAuthAuthorizationCode,
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

    # Switch caller to AAL2 Workspace Admin
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
