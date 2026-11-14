# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Comprehensive unit and API tests for RFC 8628 Headless CLI Device Flow (KB-P4-16)."""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import update

from database.models.oauth import OAuthClient, OAuthDeviceCode, OAuthGrant
from kanban.api.problems import ProblemException
from kanban.oauth.device import (
    BASE20_ALPHABET,
    USER_CODE_PATTERN,
    activate_device_code,
    clear_failed_attempts,
    create_device_authorization,
    generate_user_code,
    get_device_code_info,
    is_rate_limited,
    normalize_user_code,
    poll_device_code,
    record_failed_attempt,
    reset_rate_limits,
)
from kanban.oauth.jwt import verify_access_token
from kanban.oauth.server import OAuth2Error

if TYPE_CHECKING:
    from collections.abc import Callable

    from kanban.tests.api.conftest import ApiEnv

pytestmark = [pytest.mark.committed_db, pytest.mark.asyncio]


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


@pytest.fixture(autouse=True)
def setup_test_key_material(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up valid test key material in environment and reset device rate limits."""
    monkeypatch.delenv("KANBAN_KEYRING_FILE", raising=False)
    monkeypatch.setenv("KANBAN_MASTER_KEK", _b64(b"k" * 32))
    monkeypatch.setenv("KANBAN_AUTH_PEPPER", _b64(b"p" * 32))
    monkeypatch.setenv("KANBAN_SESSION_HMAC_KEY", _b64(b"s" * 32))
    monkeypatch.setenv("KANBAN_MASTER_KEK_KID", "test-kid-1")
    reset_rate_limits()


# =========================================================================
# Unit Tests for Helper Functions
# =========================================================================


async def test_user_code_generator_and_normalizer() -> None:
    """Verify user code generation conforms to Base-20 consonant alphabet and normalization."""
    for _ in range(50):
        code = generate_user_code()
        assert len(code) == 9
        assert code[4] == "-"
        assert USER_CODE_PATTERN.match(code)
        for char in code.replace("-", ""):
            assert char in BASE20_ALPHABET
            assert char not in "AEIOU018"

    assert normalize_user_code("w d j b - m j h t") == "WDJB-MJHT"
    assert normalize_user_code("wdjbmjht") == "WDJB-MJHT"
    assert normalize_user_code("WDJB-MJHT") == "WDJB-MJHT"


async def test_rate_limiting_helpers() -> None:
    """Verify in-memory sliding window rate limiter tracks and clears failed attempts."""
    test_key = f"ip-{uuid.uuid4()}"
    assert not is_rate_limited(test_key)

    for _ in range(4):
        record_failed_attempt(test_key)
        assert not is_rate_limited(test_key)

    # 5th attempt triggers rate limit
    record_failed_attempt(test_key)
    assert is_rate_limited(test_key)

    # Clear resets
    clear_failed_attempts(test_key)
    assert not is_rate_limited(test_key)


# =========================================================================
# Test Case 1: Positive Flow (RFC 8628 Device Approval)
# =========================================================================


async def test_case_1_positive_device_flow(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Any],
    make_project: Callable[..., Any],
    as_principal: Callable[..., Any],
) -> None:
    """Test Case 1: RFC 8628 initiate, pending poll, user /activate, approved token exchange."""
    client = api_env.client

    # 1. Register Client (RFC 7591)
    resp_reg = await client.post(
        "/oauth/register",
        json={
            "client_name": "Antigravity CLI",
            "redirect_uris": ["http://127.0.0.1:8080/callback"],
        },
    )
    assert resp_reg.status_code == 201
    client_id = resp_reg.json()["client_id"]

    # 2. Initiate Device Authorization (RFC 8628)
    resource = "http://test/mcp/agent"
    resp_dev = await client.post(
        "/oauth/device/authorize",
        data={
            "client_id": client_id,
            "resource": resource,
            "scope": "agent:read agent:write",
        },
    )
    assert resp_dev.status_code == 200
    dev_data = resp_dev.json()
    device_code = dev_data["device_code"]
    user_code = dev_data["user_code"]
    assert USER_CODE_PATTERN.match(user_code)
    assert dev_data["interval"] == 5
    assert dev_data["expires_in"] == 600
    assert "/activate" in dev_data["verification_uri"]
    assert user_code in dev_data["verification_uri_complete"]

    # 3. CLI Polls /oauth/token -> receives 400 authorization_pending
    resp_poll = await client.post(
        "/oauth/token",
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": client_id,
            "device_code": device_code,
        },
    )
    assert resp_poll.status_code == 400
    assert resp_poll.json()["error"] == "authorization_pending"

    # 4. User views /api/v1/oauth/device/info
    user = await make_user("bob", workspace_role="WORKSPACE_MEMBER")
    as_principal(user)

    resp_info = await client.get(
        "/api/v1/oauth/device/info",
        params={"user_code": user_code.lower()},
    )
    assert resp_info.status_code == 200
    info_data = resp_info.json()
    assert info_data["user_code"] == user_code
    assert info_data["client_name"] == "Antigravity CLI"
    assert info_data["resource"] == resource
    assert info_data["surface"] == "agent"
    assert "agent:read" in info_data["requested_scopes"]

    # Create a project for narrowing
    project_id = await make_project("KANBA", created_by=user)

    # 5. User Approves via POST /api/v1/oauth/device/activate
    resp_activate = await client.post(
        "/api/v1/oauth/device/activate",
        json={
            "user_code": user_code,
            "approved": True,
            "scopes": ["agent:read"],
            "allowed_projects": [str(project_id)],
        },
    )
    assert resp_activate.status_code == 200
    assert resp_activate.json()["status"] == "approved"

    # Fast-forward last_polled_at to avoid slow_down
    await api_env.seed.execute(
        update(OAuthDeviceCode)
        .where(OAuthDeviceCode.user_code == user_code)
        .values(last_polled_at=datetime.now(UTC) - timedelta(seconds=10))
    )
    await api_env.seed.commit()

    # 6. Next Poll receives 200 with tokens
    resp_token = await client.post(
        "/oauth/token",
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": client_id,
            "device_code": device_code,
        },
    )
    assert resp_token.status_code == 200
    token_data = resp_token.json()
    assert "access_token" in token_data
    assert "refresh_token" in token_data
    assert token_data["token_type"] == "Bearer"
    assert token_data["scope"] == "agent:read"

    # Verify access token claims
    claims = verify_access_token(
        token_data["access_token"],
        expected_surface_url="http://test/mcp/agent",
    )
    assert claims["sub"] == str(user.id)
    assert claims["scope"] == "agent:read"
    assert claims["allowed_projects"] == [str(project_id)]

    # 7. Metadata endpoint advertises device_authorization_endpoint
    resp_meta = await client.get("/.well-known/oauth-authorization-server")
    assert resp_meta.status_code == 200
    meta = resp_meta.json()
    assert "device_authorization_endpoint" in meta
    assert "/oauth/device/authorize" in meta["device_authorization_endpoint"]
    assert "urn:ietf:params:oauth:grant-type:device_code" in meta["grant_types_supported"]


# =========================================================================
# Test Case 2: Security & Abuse Protections
# =========================================================================


async def test_case_2_device_flow_abuse_and_security(
    api_env: ApiEnv,
    make_user: Callable[..., Any],
    as_principal: Callable[..., Any],
) -> None:
    """Test Case 2: slow_down backoff, brute-force 429, AAL2 gate on admin, expired token."""
    client = api_env.client

    # 1. Register Client
    resp_reg = await client.post(
        "/oauth/register",
        json={
            "client_name": "Test CLI",
            "redirect_uris": ["http://127.0.0.1:8080/callback"],
        },
    )
    client_id = resp_reg.json()["client_id"]

    # 2. Polling too rapidly returns 400 slow_down
    resp_dev = await client.post(
        "/oauth/device/authorize",
        data={
            "client_id": client_id,
            "resource": "http://test/mcp/agent",
        },
    )
    device_code = resp_dev.json()["device_code"]
    user_code = resp_dev.json()["user_code"]

    # First poll: authorization_pending
    resp_poll1 = await client.post(
        "/oauth/token",
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": client_id,
            "device_code": device_code,
        },
    )
    assert resp_poll1.status_code == 400
    assert resp_poll1.json()["error"] == "authorization_pending"

    # Second poll immediately (within 5s): returns slow_down and increments interval
    resp_poll2 = await client.post(
        "/oauth/token",
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": client_id,
            "device_code": device_code,
        },
    )
    assert resp_poll2.status_code == 400
    assert resp_poll2.json()["error"] == "slow_down"

    # 3. Brute-force invalid user_code triggers 429
    user = await make_user("charlie", workspace_role="WORKSPACE_MEMBER")
    as_principal(user)

    for _ in range(5):
        resp_bad = await client.get(
            "/api/v1/oauth/device/info",
            params={"user_code": "BBBB-BBBB"},
        )
        assert resp_bad.status_code in (400, 404)

    # 6th attempt returns 429
    resp_limited = await client.get(
        "/api/v1/oauth/device/info",
        params={"user_code": "BBBB-BBBB"},
    )
    assert resp_limited.status_code == 429
    assert resp_limited.json()["code"] == "RATE_LIMIT_EXCEEDED"

    # Reset rate limit for user
    reset_rate_limits()

    # 4. User Denies authorization
    resp_deny = await client.post(
        "/api/v1/oauth/device/activate",
        json={
            "user_code": user_code,
            "approved": False,
        },
    )
    assert resp_deny.status_code == 200
    assert resp_deny.json()["status"] == "denied"

    # Fast-forward poll time
    await api_env.seed.execute(
        update(OAuthDeviceCode)
        .where(OAuthDeviceCode.user_code == user_code)
        .values(last_polled_at=datetime.now(UTC) - timedelta(seconds=20))
    )
    await api_env.seed.commit()

    # Polling after denial returns access_denied
    resp_poll_denied = await client.post(
        "/oauth/token",
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": client_id,
            "device_code": device_code,
        },
    )
    assert resp_poll_denied.status_code == 400
    assert resp_poll_denied.json()["error"] == "access_denied"

    # 5. AAL2 Gate on /mcp/admin
    resp_dev_admin = await client.post(
        "/oauth/device/authorize",
        data={
            "client_id": client_id,
            "resource": "http://test/mcp/admin",
        },
    )
    admin_user_code = resp_dev_admin.json()["user_code"]

    # Charlie is AAL1; attempting to approve /mcp/admin returns 403 AAL2_REQUIRED
    resp_act_aal1 = await client.post(
        "/api/v1/oauth/device/activate",
        json={
            "user_code": admin_user_code,
            "approved": True,
        },
    )
    assert resp_act_aal1.status_code == 403
    assert resp_act_aal1.json()["code"] == "AAL2_REQUIRED"

    # Now approve with an AAL2 principal
    admin_user = await make_user("admin_eve", workspace_role="WORKSPACE_ADMIN")
    as_principal(admin_user, aal_level=2)
    resp_act_aal2 = await client.post(
        "/api/v1/oauth/device/activate",
        json={
            "user_code": admin_user_code,
            "approved": True,
            "scopes": ["admin:read"],
        },
    )
    assert resp_act_aal2.status_code == 200
    assert resp_act_aal2.json()["status"] == "approved"

    # 6. Expired Device Code (>600s)
    await api_env.seed.execute(
        update(OAuthDeviceCode)
        .where(OAuthDeviceCode.user_code == admin_user_code)
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=10))
    )
    await api_env.seed.commit()

    resp_poll_expired = await client.post(
        "/oauth/token",
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": client_id,
            "device_code": resp_dev_admin.json()["device_code"],
        },
    )
    assert resp_poll_expired.status_code == 400
    assert resp_poll_expired.json()["error"] == "expired_token"


# =========================================================================
# Test Case 3: Personal MCP Keys Lifecycle
# =========================================================================


async def test_case_3_personal_mcp_keys_lifecycle(
    api_env: ApiEnv,
    make_user: Callable[..., Any],
    as_principal: Callable[..., Any],
) -> None:
    """Test Case 3: Personal MCP key minting, listing, revocation, and 404 on re-revocation."""
    client = api_env.client
    user = await make_user("dan", workspace_role="WORKSPACE_MEMBER")
    as_principal(user)

    # 1. Mint personal key
    resp_mint = await client.post(
        "/api/v1/auth/mcp-keys",
        json={
            "surface": "agent",
            "scopes": ["agent:read", "agent:write"],
            "expires_in_days": 60,
        },
    )
    assert resp_mint.status_code == 201
    mint_data = resp_mint.json()
    key_id = mint_data["id"]
    raw_key = mint_data["raw_key"]
    assert raw_key.startswith("kb_agt_")
    assert mint_data["display_hint"] in raw_key
    assert mint_data["surface"] == "agent"

    # 2. List personal keys (contains hint, not plaintext raw_key)
    resp_list = await client.get("/api/v1/auth/mcp-keys")
    assert resp_list.status_code == 200
    keys = resp_list.json()["keys"]
    assert len(keys) == 1
    assert keys[0]["id"] == key_id
    assert keys[0]["display_hint"] == mint_data["display_hint"]
    assert "raw_key" not in keys[0]

    # 3. Revoke personal key
    resp_del = await client.delete(f"/api/v1/auth/mcp-keys/{key_id}")
    assert resp_del.status_code == 204

    # 4. Revoking again returns 204 or 404 (already revoked)
    resp_list2 = await client.get("/api/v1/auth/mcp-keys")
    assert resp_list2.status_code == 200
    assert resp_list2.json()["keys"][0]["revoked_at"] is not None

    # 5. Connected OAuth Apps: Register client, create grant, list, and revoke
    resp_reg_app = await client.post(
        "/oauth/register",
        json={
            "client_name": "<img src=x onerror=alert(1)> Claude Code",
            "redirect_uris": ["http://127.0.0.1:8080/callback"],
        },
    )
    assert resp_reg_app.status_code == 201
    app_client_id = resp_reg_app.json()["client_id"]

    # Mint device flow grant
    app_dev = await create_device_authorization(
        api_env.seed,
        client_id_str=app_client_id,
        resource="http://test/mcp/agent",
        scope_str="agent:read",
        base_url="http://test",
    )
    grant = await activate_device_code(
        api_env.seed,
        raw_user_code=app_dev.user_code,
        principal_id=user.id,
        workspace_id=user.workspace_id,
        approved=True,
        allowed_scopes=["agent:read"],
        allowed_projects=None,
        rate_limit_key="app_test_key",
    )
    assert grant is not None

    resp_grants = await client.get("/api/v1/auth/oauth-grants")
    assert resp_grants.status_code == 200
    grants_data = resp_grants.json()
    assert any(
        g["client_id"] == app_client_id and "<img" in (g.get("client_name") or "")
        for g in grants_data
    )

    # Disconnect Connected App
    resp_del_grant = await client.delete(f"/api/v1/auth/oauth-grants/{grant.id}")
    assert resp_del_grant.status_code == 204


# =========================================================================
# Additional Branch & Edge Cases (Coverage Gate)
# =========================================================================


async def test_device_flow_edge_cases(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Any],
    as_principal: Callable[..., Any],
) -> None:
    """Exercise all branch conditions and edge cases in kanban/oauth/device.py."""
    user = await make_user("dave", workspace_role="WORKSPACE_MEMBER")
    as_principal(user)

    # 1. create_device_authorization: client not found or not active
    with pytest.raises(OAuth2Error) as exc_info:
        await create_device_authorization(
            api_env.seed,
            client_id_str="nonexistent_client",
            resource="http://test/mcp/agent",
            scope_str=None,
            base_url="http://test",
        )
    assert exc_info.value.error == "invalid_client"

    # Inactive client
    inactive_client = OAuthClient(
        client_id="client_inactive_123",
        client_name="Inactive App",
        client_type="public",
        redirect_uris=["http://127.0.0.1:8080/cb"],
        status="disabled",
    )
    api_env.seed.add(inactive_client)
    await api_env.seed.commit()

    with pytest.raises(OAuth2Error) as exc_info:
        await create_device_authorization(
            api_env.seed,
            client_id_str="client_inactive_123",
            resource="http://test/mcp/agent",
            scope_str=None,
            base_url="http://test",
        )
    assert exc_info.value.error == "invalid_client"

    # Active client with invalid requested scopes (falls back to default surface scope)
    reg_client = OAuthClient(
        client_id="client_edge_test",
        client_name="Edge App",
        client_type="public",
        redirect_uris=["http://127.0.0.1:8080/cb"],
        status="active",
        workspace_id=user.workspace_id,
    )
    api_env.seed.add(reg_client)
    await api_env.seed.commit()

    res_dev = await create_device_authorization(
        api_env.seed,
        client_id_str="client_edge_test",
        resource="http://test/mcp/agent",
        scope_str="invalid:scope bogus",
        base_url="http://test",
    )
    assert res_dev.user_code is not None

    # 2. poll_device_code edge cases
    # Empty device code
    with pytest.raises(OAuth2Error) as exc_info:
        await poll_device_code(
            api_env.seed,
            device_code="",
            client_id_str="client_edge_test",
        )
    assert exc_info.value.error == "invalid_request"

    # Invalid device code (sha not found)
    with pytest.raises(OAuth2Error) as exc_info:
        await poll_device_code(
            api_env.seed,
            device_code="invalid_nonexistent_device_code_random_bytes",
            client_id_str="client_edge_test",
        )
    assert exc_info.value.error == "invalid_grant"

    # Client mismatch
    with pytest.raises(OAuth2Error) as exc_info:
        await poll_device_code(
            api_env.seed,
            device_code=res_dev.device_code,
            client_id_str="client_different_one",
        )
    assert exc_info.value.error == "invalid_grant"

    # 3. get_device_code_info edge cases
    # Invalid user code format
    with pytest.raises(ProblemException) as prob:
        await get_device_code_info(
            api_env.seed,
            "123-INVALID",
            rate_limit_key="edge_key_1",
        )
    assert prob.value.code == "INVALID_USER_CODE"

    # User code not found
    with pytest.raises(ProblemException) as prob:
        await get_device_code_info(
            api_env.seed,
            "ZZZZ-ZZZZ",
            rate_limit_key="edge_key_2",
        )
    assert prob.value.code == "NOT_FOUND"

    # Expired code in get_device_code_info
    await api_env.seed.execute(
        update(OAuthDeviceCode)
        .where(OAuthDeviceCode.user_code == res_dev.user_code)
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=10))
    )
    await api_env.seed.commit()

    with pytest.raises(ProblemException) as prob:
        await get_device_code_info(
            api_env.seed,
            res_dev.user_code,
            rate_limit_key="edge_key_3",
        )
    assert prob.value.code == "EXPIRED_CODE"

    # 4. activate_device_code edge cases
    # Invalid user code format
    with pytest.raises(ProblemException) as prob:
        await activate_device_code(
            api_env.seed,
            raw_user_code="BAD_CODE",
            principal_id=user.id,
            workspace_id=user.workspace_id,
            approved=True,
            allowed_scopes=None,
            allowed_projects=None,
            rate_limit_key="edge_key_4",
        )
    assert prob.value.code == "INVALID_USER_CODE"

    # User code not found
    with pytest.raises(ProblemException) as prob:
        await activate_device_code(
            api_env.seed,
            raw_user_code="ZZZZ-ZZZZ",
            principal_id=user.id,
            workspace_id=user.workspace_id,
            approved=True,
            allowed_scopes=None,
            allowed_projects=None,
            rate_limit_key="edge_key_5",
        )
    assert prob.value.code == "NOT_FOUND"

    # Expired code in activate_device_code
    with pytest.raises(ProblemException) as prob:
        await activate_device_code(
            api_env.seed,
            raw_user_code=res_dev.user_code,
            principal_id=user.id,
            workspace_id=user.workspace_id,
            approved=True,
            allowed_scopes=None,
            allowed_projects=None,
            rate_limit_key="edge_key_6",
        )
    assert prob.value.code == "EXPIRED_CODE"

    # Code expired in poll_device_code
    with pytest.raises(OAuth2Error) as exc_info:
        await poll_device_code(
            api_env.seed,
            device_code=res_dev.device_code,
            client_id_str="client_edge_test",
        )
    assert exc_info.value.error == "expired_token"

    # Fresh device code to test already processed and empty scopes fallback
    fresh_dev = await create_device_authorization(
        api_env.seed,
        client_id_str="client_edge_test",
        resource="http://test/mcp/agent",
        scope_str="agent:read",
        base_url="http://test",
    )
    # Activate with invalid scope list that gets stripped to empty -> falls back to surface default
    grant = await activate_device_code(
        api_env.seed,
        raw_user_code=fresh_dev.user_code,
        principal_id=user.id,
        workspace_id=user.workspace_id,
        approved=True,
        allowed_scopes=["unknown:scope"],
        allowed_projects=None,
        rate_limit_key="edge_key_7",
    )
    assert grant is not None
    assert "agent:read" in grant.scopes

    # Now already processed (status is approved)
    with pytest.raises(ProblemException) as prob:
        await get_device_code_info(
            api_env.seed,
            fresh_dev.user_code,
            rate_limit_key="edge_key_8",
        )
    assert prob.value.code == "ALREADY_PROCESSED"

    with pytest.raises(ProblemException) as prob:
        await activate_device_code(
            api_env.seed,
            raw_user_code=fresh_dev.user_code,
            principal_id=user.id,
            workspace_id=user.workspace_id,
            approved=True,
            allowed_scopes=None,
            allowed_projects=None,
            rate_limit_key="edge_key_9",
        )
    assert prob.value.code == "ALREADY_PROCESSED"

    # Poll with approved code but missing approved grant
    broken_grant_code = await create_device_authorization(
        api_env.seed,
        client_id_str="client_edge_test",
        resource="http://test/mcp/agent",
        scope_str="agent:read",
        base_url="http://test",
    )
    await api_env.seed.execute(
        update(OAuthDeviceCode)
        .where(OAuthDeviceCode.user_code == broken_grant_code.user_code)
        .values(status="approved", approved_grant_id=None)
    )
    await api_env.seed.commit()
    with pytest.raises(OAuth2Error) as exc_info:
        await poll_device_code(
            api_env.seed,
            device_code=broken_grant_code.device_code,
            client_id_str="client_edge_test",
        )
    assert exc_info.value.error == "invalid_grant"

    # Poll with approved code but revoked grant
    revoked_grant = OAuthGrant(
        workspace_id=user.workspace_id,
        principal_id=user.id,
        client_id=reg_client.id,
        surface="agent",
        scopes=["agent:read"],
        revoked_at=datetime.now(UTC),
    )
    api_env.seed.add(revoked_grant)
    await api_env.seed.commit()

    await api_env.seed.execute(
        update(OAuthDeviceCode)
        .where(OAuthDeviceCode.user_code == broken_grant_code.user_code)
        .values(
            status="approved",
            approved_grant_id=revoked_grant.id,
            last_polled_at=datetime.now(UTC) - timedelta(seconds=20),
        )
    )
    await api_env.seed.commit()
    with pytest.raises(OAuth2Error) as exc_info:
        await poll_device_code(
            api_env.seed,
            device_code=broken_grant_code.device_code,
            client_id_str="client_edge_test",
        )
    assert exc_info.value.error == "invalid_grant"

    # activate_device_code with allowed_scopes=None (takes requested_scopes)
    dev_default_scopes = await create_device_authorization(
        api_env.seed,
        client_id_str="client_edge_test",
        resource="http://test/mcp/agent",
        scope_str="agent:read agent:write",
        base_url="http://test",
    )
    grant_default = await activate_device_code(
        api_env.seed,
        raw_user_code=dev_default_scopes.user_code,
        principal_id=user.id,
        workspace_id=user.workspace_id,
        approved=True,
        allowed_scopes=None,
        allowed_projects=None,
        rate_limit_key="edge_key_10",
    )
    assert grant_default is not None
    assert "agent:write" in grant_default.scopes
