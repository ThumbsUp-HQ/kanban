# mypy: disable-error-code="method-assign,no-any-return,union-attr"
# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit and boundary tests for kanban.api.v1.oauth coverage expansion."""

from __future__ import annotations

import base64
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request

import kanban.api.v1.oauth as oauth_mod
import kanban.auth.local.hashing as local_hashing
import kanban.auth.oidc.workload as workload_mod
from database.models.oauth import (
    OAuthAuthorizationCode,
    OAuthClient,
    OAuthDeviceCode,
    OAuthGrant,
    OAuthRefreshToken,
)
from database.models.workload_identity import WorkloadIdentityPolicy
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.api.v1.oauth import (
    OAuthClientPatchRequest,
    OAuthClientRegisterRequest,
    _check_no_token_in_query,
    _parse_request_payload,
    _require_admin_aal2,
    _resolve_target_scope,
    admin_delete_oauth_client,
    admin_patch_oauth_client,
    admin_revoke_oauth_grant,
    get_db_session,
    list_user_oauth_grants,
    oauth_authorize,
    oauth_device_authorize,
    oauth_register_client,
    oauth_revoke_endpoint,
    oauth_token_endpoint,
    revoke_user_oauth_grant,
)
from kanban.oauth.device import activate_device_code, poll_device_code
from kanban.oauth.server import OAuth2Error, hash_client_secret


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


def _make_mock_session() -> tuple[AsyncMock, list[Any]]:
    session = AsyncMock()
    mock_nested = MagicMock()
    mock_nested.__aenter__ = AsyncMock(return_value=None)
    mock_nested.__aexit__ = AsyncMock(return_value=None)
    session.begin_nested = MagicMock(return_value=mock_nested)
    session.add = MagicMock()
    queue: list[Any] = []

    def _exec(*_args: object, **_kwargs: object) -> MagicMock:
        if queue:
            return queue.pop(0)
        fallback = MagicMock()
        fallback.scalar_one_or_none.return_value = None
        fallback.scalars.return_value.all.return_value = []
        fallback.scalar_one.return_value = True
        fallback.first.return_value = None
        fallback.all.return_value = []
        return fallback

    session.execute.side_effect = _exec
    return session, queue


def _make_mock_jwt(header: dict[str, Any], claims: dict[str, Any]) -> str:
    h = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    c = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"{h}.{c}.mock_sig"


@pytest.mark.asyncio
async def test_check_no_token_in_query_scenarios() -> None:
    """Test _check_no_token_in_query rejects access_token in URL query parameters."""
    req_bad = Request(
        {
            "type": "http",
            "method": "GET",
            "query_string": b"access_token=secret123&scope=agent:read",
            "headers": [],
        }
    )
    with pytest.raises(OAuth2Error) as exc_info:
        _check_no_token_in_query(req_bad)
    assert exc_info.value.error == "invalid_request"
    assert "query string is strictly forbidden" in exc_info.value.description

    req_ok = Request(
        {
            "type": "http",
            "method": "GET",
            "query_string": b"response_type=code&client_id=myclient",
            "headers": [],
        }
    )
    _check_no_token_in_query(req_ok)


@pytest.mark.asyncio
async def test_get_db_session_unconfigured_factory() -> None:
    """Test get_db_session raises RuntimeError when session_factory is missing on app.state."""
    req = Request({"type": "http", "app": MagicMock(state=MagicMock(session_factory=None))})
    gen = get_db_session(req)
    with pytest.raises(RuntimeError, match="Session factory is not configured"):
        await gen.__anext__()


@pytest.mark.asyncio
async def test_parse_request_payload_scenarios() -> None:
    """Test _parse_request_payload with JSON, empty body, and form-encoded data."""
    req_json = Request(
        {
            "type": "http",
            "method": "POST",
            "headers": [(b"content-type", b"application/json")],
        }
    )
    req_json.json = AsyncMock(return_value={"client_id": "test_app", "scope": "agent:read"})
    res1 = await _parse_request_payload(req_json)
    assert res1 == {"client_id": "test_app", "scope": "agent:read"}

    req_json_err = Request(
        {
            "type": "http",
            "method": "POST",
            "headers": [(b"content-type", b"application/json")],
        }
    )
    req_json_err.json = AsyncMock(side_effect=ValueError("bad json"))
    res2 = await _parse_request_payload(req_json_err)
    assert res2 == {}

    req_empty = Request(
        {
            "type": "http",
            "method": "POST",
            "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
        }
    )
    req_empty.body = AsyncMock(return_value=b"")
    res3 = await _parse_request_payload(req_empty)
    assert res3 == {}

    req_form = Request(
        {
            "type": "http",
            "method": "POST",
            "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
        }
    )
    req_form.body = AsyncMock(return_value=b"client_id=cli1&scopes=read&scopes=write")
    res4 = await _parse_request_payload(req_form)
    assert res4["client_id"] == "cli1"
    assert res4["scopes"] == ["read", "write"]


@pytest.mark.asyncio
async def test_require_admin_aal2_scenarios() -> None:
    """Test _require_admin_aal2 enforces AAL level and workspace admin role."""
    session = AsyncMock()
    mock_res = MagicMock()
    session.execute.return_value = mock_res

    caller_aal1 = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        aal_level=1,
    )
    with pytest.raises(ProblemException) as exc_aal1:
        await _require_admin_aal2(caller_aal1, session)
    assert exc_aal1.value.status == 403
    assert exc_aal1.value.code == "AAL2_REQUIRED"

    caller_aal2 = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        aal_level=2,
    )
    mock_res.scalar_one.return_value = False
    with pytest.raises(ProblemException) as exc_forbid:
        await _require_admin_aal2(caller_aal2, session)
    assert exc_forbid.value.status == 403
    assert exc_forbid.value.code == "FORBIDDEN"

    mock_res.scalar_one.return_value = True
    await _require_admin_aal2(caller_aal2, session)


@pytest.mark.asyncio
async def test_resolve_target_scope_scenarios() -> None:
    """Test _resolve_target_scope workspace and project resolution branches."""
    session = AsyncMock()
    ws_id = uuid.uuid4()
    p_id = uuid.uuid4()
    base_url = "http://127.0.0.1:8080"

    mock_res_ws_none = MagicMock()
    mock_res_ws_none.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_res_ws_none
    with pytest.raises(OAuth2Error) as exc_ws:
        await _resolve_target_scope(
            session=session,
            resource=f"{base_url}/mcp/agent/w/missing-ws",
            base_url=base_url,
            caller_principal_id=p_id,
            caller_workspace_id=ws_id,
        )
    assert exc_ws.value.status_code == 403
    assert "not found" in exc_ws.value.description

    target_ws = uuid.uuid4()
    mock_res_ws = MagicMock()
    mock_res_ws.scalar_one_or_none.return_value = target_ws
    mock_res_switch = MagicMock()
    mock_res_switch.first.return_value = None
    session.execute.side_effect = [mock_res_ws, mock_res_switch]

    with pytest.raises(OAuth2Error) as exc_switch:
        await _resolve_target_scope(
            session=session,
            resource=f"{base_url}/mcp/agent/w/valid-ws",
            base_url=base_url,
            caller_principal_id=p_id,
            caller_workspace_id=ws_id,
        )
    assert exc_switch.value.status_code == 403
    assert "not a member" in exc_switch.value.description

    mock_res_proj = MagicMock()
    mock_res_proj.scalar_one_or_none.return_value = None
    mock_res_switch_ok = MagicMock()
    mock_res_switch_ok.first.return_value = (target_ws, p_id)
    session.execute.side_effect = [mock_res_ws, mock_res_switch_ok, mock_res_proj]

    with pytest.raises(OAuth2Error) as exc_proj:
        await _resolve_target_scope(
            session=session,
            resource=f"{base_url}/mcp/agent/w/valid-ws/p/MISSING",
            base_url=base_url,
            caller_principal_id=p_id,
            caller_workspace_id=ws_id,
        )
    assert exc_proj.value.status_code == 403
    assert "Target project 'MISSING' not found" in exc_proj.value.description


@pytest.mark.asyncio
async def test_register_oauth_client_grant_types_validation() -> None:
    """Test oauth_register_client validates grant_types metadata."""
    req = Request(
        {
            "type": "http",
            "method": "POST",
            "server": ("127.0.0.1", 8080),
            "query_string": b"",
            "headers": [],
        }
    )
    session = AsyncMock()

    empty_payload = OAuthClientRegisterRequest(
        redirect_uris=["https://client.local/cb"],
        client_name="Test App",
        grant_types=[],
    )
    with pytest.raises(OAuth2Error) as exc_empty:
        await oauth_register_client(req, empty_payload, session)
    assert exc_empty.value.error == "invalid_client_metadata"
    assert "grant_types cannot be empty" in exc_empty.value.description

    unsupported_payload = OAuthClientRegisterRequest(
        redirect_uris=["https://client.local/cb"],
        client_name="Test App",
        grant_types=["client_credentials", "password"],
    )
    with pytest.raises(OAuth2Error) as exc_unsupported:
        await oauth_register_client(req, unsupported_payload, session)
    assert exc_unsupported.value.error == "invalid_client_metadata"
    assert "Unsupported grant_types" in exc_unsupported.value.description


@pytest.mark.asyncio
async def test_oauth_token_unsupported_grant_type() -> None:
    """Test oauth_token_endpoint unsupported grant types error out with 400."""
    req = Request(
        {
            "type": "http",
            "method": "POST",
            "server": ("127.0.0.1", 8080),
            "query_string": b"",
            "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
        }
    )
    session = AsyncMock()
    req.body = AsyncMock(return_value=b"grant_type=password&username=u&password=p")
    with pytest.raises(OAuth2Error) as exc_gt:
        await oauth_token_endpoint(req, session)
    assert exc_gt.value.status_code == 400
    assert exc_gt.value.error == "unsupported_grant_type"


@pytest.mark.asyncio
async def test_oauth_token_exchange_invalid_requests() -> None:
    """Test RFC 8693 token exchange parameter validations."""
    req = Request(
        {
            "type": "http",
            "method": "POST",
            "server": ("127.0.0.1", 8080),
            "query_string": b"",
            "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
        }
    )
    session = AsyncMock()

    req.body = AsyncMock(return_value=b"grant_type=urn:ietf:params:oauth:grant-type:token-exchange")
    with pytest.raises(OAuth2Error) as exc_subj:
        await oauth_token_endpoint(req, session)
    assert exc_subj.value.error == "invalid_request"
    assert "subject_token parameter required" in exc_subj.value.description

    req.body = AsyncMock(
        return_value=(
            b"grant_type=urn:ietf:params:oauth:grant-type:token-exchange"
            b"&subject_token=abc.def.ghi"
            b"&subject_token_type=urn:ietf:params:oauth:token-type:saml2"
        )
    )
    with pytest.raises(OAuth2Error) as exc_type:
        await oauth_token_endpoint(req, session)
    assert exc_type.value.error == "invalid_request"
    assert "Unsupported subject_token_type" in exc_type.value.description

    no_iss_jwt = _make_mock_jwt({"alg": "RS256"}, {"sub": "usr_123"})
    req.body = AsyncMock(
        return_value=(
            f"grant_type=urn:ietf:params:oauth:grant-type:token-exchange"
            f"&subject_token={no_iss_jwt}"
            f"&subject_token_type=urn:ietf:params:oauth:token-type:jwt"
        ).encode()
    )
    with pytest.raises(OAuth2Error) as exc_iss:
        await oauth_token_endpoint(req, session)
    assert exc_iss.value.error == "invalid_grant"
    assert "missing iss claim" in exc_iss.value.description


@pytest.mark.asyncio
async def test_oauth_token_exchange_policy_and_cidr_restrictions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test RFC 8693 workload policy resolution, CIDR check, and success exchange."""
    req = Request(
        {
            "type": "http",
            "method": "POST",
            "server": ("127.0.0.1", 8080),
            "query_string": b"",
            "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
        }
    )
    session = AsyncMock()

    with_iss_jwt = _make_mock_jwt(
        {"alg": "RS256"},
        {"iss": "https://unknown.issuer.com", "sub": "usr_1"},
    )
    req.body = AsyncMock(
        return_value=(
            f"grant_type=urn:ietf:params:oauth:grant-type:token-exchange"
            f"&subject_token={with_iss_jwt}"
            f"&subject_token_type=urn:ietf:params:oauth:token-type:jwt"
        ).encode()
    )
    mock_res_pol = MagicMock()
    mock_res_pol.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_res_pol
    with pytest.raises(OAuth2Error) as exc_no_pol:
        await oauth_token_endpoint(req, session)
    assert exc_no_pol.value.error == "invalid_grant"
    assert "No active workload identity policy found" in exc_no_pol.value.description

    mock_policy = MagicMock(spec=WorkloadIdentityPolicy)
    mock_policy.id = uuid.uuid4()
    mock_policy.name = "Test Workload Policy"
    mock_policy.issuer = "https://valid.issuer.com"
    mock_policy.client_id = "workload_client"
    mock_policy.is_enabled = True
    mock_policy.allowed_cidrs = ["10.0.0.0/8"]
    mock_policy.max_ttl_seconds = 3600
    mock_policy.surface = "agent"
    mock_policy.scopes = ["agent:read"]
    mock_policy.workspace_id = uuid.uuid4()
    mock_policy.created_by_id = uuid.uuid4()
    mock_policy.allowed_project_ids = None
    mock_policy.capability_mask = None

    valid_jwt = _make_mock_jwt(
        {"alg": "RS256"},
        {"iss": "https://valid.issuer.com", "sub": "usr_workload"},
    )
    req.body = AsyncMock(
        return_value=(
            f"grant_type=urn:ietf:params:oauth:grant-type:token-exchange"
            f"&subject_token={valid_jwt}"
            f"&subject_token_type=urn:ietf:params:oauth:token-type:jwt"
        ).encode()
    )
    mock_res_pol_found = MagicMock()
    mock_res_pol_found.scalars.return_value.all.return_value = [mock_policy]
    session.execute.return_value = mock_res_pol_found
    with pytest.raises(OAuth2Error) as exc_cidr:
        await oauth_token_endpoint(req, session)
    assert exc_cidr.value.error == "invalid_grant"
    assert "not permitted by workload policy CIDR restrictions" in exc_cidr.value.description

    mock_policy.allowed_cidrs = ["127.0.0.1/32"]
    mock_policy.allowed_project_ids = [uuid.uuid4()]
    monkeypatch.setattr(
        workload_mod,
        "validate_workload_jwt",
        AsyncMock(return_value={"sub": "usr_workload_1"}),
    )
    resp_exchange = await oauth_token_endpoint(req, session)
    assert resp_exchange.status_code == 200
    resp_body = json.loads(resp_exchange.body.decode())
    assert resp_body["token_type"] == "Bearer"
    assert resp_body["issued_token_type"] == "urn:ietf:params:oauth:token-type:access_token"
    assert "access_token" in resp_body


@pytest.mark.asyncio
async def test_user_oauth_grants_endpoints() -> None:
    """Test user OAuth grant listing and user revocation."""
    caller = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        aal_level=2,
    )
    session, queue = _make_mock_session()

    mock_grant = MagicMock(spec=OAuthGrant)
    mock_grant.id = uuid.uuid4()
    mock_grant.surface = "agent"
    mock_grant.scopes = ["agent:read"]
    mock_grant.allowed_projects = None
    mock_grant.created_at = datetime.now(UTC)
    mock_grant.revoked_at = None

    mock_res_list = MagicMock()
    mock_res_list.all.return_value = [(mock_grant, "cli_1", "Test Client")]
    queue.append(mock_res_list)
    grants = await list_user_oauth_grants(caller, session)
    assert len(grants) == 1
    assert grants[0].client_id == "cli_1"

    mock_res_none = MagicMock()
    mock_res_none.scalar_one_or_none.return_value = None
    queue.append(mock_res_none)
    with pytest.raises(ProblemException) as exc_not_found:
        await revoke_user_oauth_grant(uuid.uuid4(), caller, session)
    assert exc_not_found.value.status == 404

    mock_res_grant = MagicMock()
    mock_res_grant.scalar_one_or_none.return_value = mock_grant
    queue.append(mock_res_grant)
    resp_rev = await revoke_user_oauth_grant(mock_grant.id, caller, session)
    assert resp_rev.status_code == 204


@pytest.mark.asyncio
async def test_admin_oauth_grant_revocation() -> None:
    """Test admin revocation of OAuth grant."""
    caller = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        aal_level=2,
    )
    session, queue = _make_mock_session()
    mock_grant = MagicMock(spec=OAuthGrant)
    mock_grant.id = uuid.uuid4()

    mock_res_admin_ok = MagicMock()
    mock_res_admin_ok.scalar_one.return_value = True
    mock_res_none = MagicMock()
    mock_res_none.scalar_one_or_none.return_value = None

    queue.extend([mock_res_admin_ok, mock_res_none])
    with pytest.raises(ProblemException) as exc_not_found:
        await admin_revoke_oauth_grant(uuid.uuid4(), caller, session)
    assert exc_not_found.value.status == 404

    mock_res_grant = MagicMock()
    mock_res_grant.scalar_one_or_none.return_value = mock_grant
    queue.extend([mock_res_admin_ok, mock_res_grant])
    resp_adm_rev = await admin_revoke_oauth_grant(mock_grant.id, caller, session)
    assert resp_adm_rev.status_code == 204


@pytest.mark.asyncio
async def test_admin_patch_oauth_client() -> None:
    """Test admin patching OAuth client status and metadata."""
    caller = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        aal_level=2,
    )
    session, queue = _make_mock_session()

    mock_res_admin_ok = MagicMock()
    mock_res_admin_ok.scalar_one.return_value = True
    mock_res_none = MagicMock()
    mock_res_none.scalar_one_or_none.return_value = None

    queue.extend([mock_res_admin_ok, mock_res_none])
    with pytest.raises(ProblemException) as exc_not_found:
        await admin_patch_oauth_client(
            "unknown_client",
            OAuthClientPatchRequest(client_name="New"),
            caller,
            session,
        )
    assert exc_not_found.value.status == 404

    client_rec = MagicMock(spec=OAuthClient)
    client_rec.id = uuid.uuid4()
    client_rec.client_id = "cli_to_disable"
    client_rec.client_name = "Old Name"
    client_rec.client_type = "public"
    client_rec.client_secret_prefix = None
    client_rec.status = "active"
    client_rec.redirect_uris = ["http://127.0.0.1:8080/cb"]

    mock_grant = MagicMock(spec=OAuthGrant)
    mock_res_cli = MagicMock()
    mock_res_cli.scalar_one_or_none.return_value = client_rec
    mock_res_grants = MagicMock()
    mock_res_grants.scalars.return_value.all.return_value = [mock_grant]

    queue.extend([mock_res_admin_ok, mock_res_cli, mock_res_grants])
    patch_resp = await admin_patch_oauth_client(
        "cli_to_disable",
        OAuthClientPatchRequest(
            client_name="Updated Name",
            status="disabled",
            redirect_uris=["http://127.0.0.1:8080/cb2"],
        ),
        caller,
        session,
    )
    assert patch_resp.status_code == 200


@pytest.mark.asyncio
async def test_admin_delete_oauth_client() -> None:
    """Test admin deletion of OAuth client."""
    caller = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        aal_level=2,
    )
    session, queue = _make_mock_session()

    mock_res_admin_ok = MagicMock()
    mock_res_admin_ok.scalar_one.return_value = True
    mock_res_none = MagicMock()
    mock_res_none.scalar_one_or_none.return_value = None

    client_rec = MagicMock(spec=OAuthClient)
    client_rec.id = uuid.uuid4()
    mock_grant = MagicMock(spec=OAuthGrant)
    mock_res_cli = MagicMock()
    mock_res_cli.scalar_one_or_none.return_value = client_rec
    mock_res_grants = MagicMock()
    mock_res_grants.scalars.return_value.all.return_value = [mock_grant]

    queue.extend([mock_res_admin_ok, mock_res_cli, mock_res_grants])
    del_resp = await admin_delete_oauth_client("cli_to_disable", caller, session)
    assert del_resp.status_code == 204

    queue.extend([mock_res_admin_ok, mock_res_none])
    with pytest.raises(ProblemException) as exc_not_found:
        await admin_delete_oauth_client("nonexistent_client", caller, session)
    assert exc_not_found.value.status == 404


@pytest.mark.asyncio
async def test_device_flow_poll_and_activate_errors() -> None:
    """Test device code poll error branches and expired code activation."""
    session, queue = _make_mock_session()

    with pytest.raises(OAuth2Error) as exc_dev:
        await poll_device_code(session, device_code="", client_id_str="cli1")
    assert exc_dev.value.error == "invalid_request"

    mock_dev_code = MagicMock(spec=OAuthDeviceCode)
    mock_dev_code.expires_at = datetime.now(UTC) + timedelta(minutes=5)
    mock_dev_code.status = "bogus_status"
    mock_dev_code.interval_sec = 5
    mock_dev_code.last_polled_at = None

    mock_client = MagicMock(spec=OAuthClient)
    mock_client.client_id = "cli1"

    mock_res_dev = MagicMock()
    mock_res_dev.first.return_value = (mock_dev_code, mock_client)
    queue.append(mock_res_dev)

    with pytest.raises(OAuth2Error) as exc_bogus:
        await poll_device_code(session, device_code="test_code", client_id_str="cli1")
    assert exc_bogus.value.error == "invalid_grant"
    assert "Invalid device code state" in exc_bogus.value.description

    mock_dev_code.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    mock_dev_code.status = "pending"
    queue.append(mock_res_dev)
    with pytest.raises(ProblemException) as exc_exp:
        await activate_device_code(
            session=session,
            raw_user_code="BCDF-GHJK",
            principal_id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
            approved=True,
            allowed_scopes=["agent:read"],
            allowed_projects=None,
            rate_limit_key=f"unique_key_{uuid.uuid4()}",
        )
    assert exc_exp.value.status == 410
    assert mock_dev_code.status == "expired"


def test_hash_client_secret_pepper_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test hash_client_secret fallback when get_auth_pepper raises exception."""
    monkeypatch.setattr(
        local_hashing,
        "get_auth_pepper",
        MagicMock(side_effect=ValueError("no pepper")),
    )
    h = hash_client_secret("secret123")
    assert isinstance(h, str)
    assert len(h) == 64


@pytest.mark.asyncio
async def test_oauth_token_basic_auth_errors() -> None:
    """Test OAuth token endpoint Basic auth syntax and mismatch errors."""
    session = AsyncMock()

    req_bad_basic = Request(
        {
            "type": "http",
            "method": "POST",
            "server": ("127.0.0.1", 8080),
            "query_string": b"",
            "headers": [
                (b"content-type", b"application/x-www-form-urlencoded"),
                (b"authorization", b"Basic " + base64.b64encode(b"nocolon")),
            ],
        }
    )
    req_bad_basic.body = AsyncMock(return_value=b"grant_type=client_credentials")
    with pytest.raises(OAuth2Error) as exc_basic:
        await oauth_token_endpoint(req_bad_basic, session)
    assert exc_basic.value.error == "invalid_client"
    assert "Malformed Basic" in exc_basic.value.description

    req_inv_b64 = Request(
        {
            "type": "http",
            "method": "POST",
            "server": ("127.0.0.1", 8080),
            "query_string": b"",
            "headers": [
                (b"content-type", b"application/x-www-form-urlencoded"),
                (b"authorization", b"Basic ???notb64???"),
            ],
        }
    )
    req_inv_b64.body = AsyncMock(return_value=b"grant_type=client_credentials")
    with pytest.raises(OAuth2Error) as exc_b64:
        await oauth_token_endpoint(req_inv_b64, session)
    assert exc_b64.value.error == "invalid_client"
    assert "Invalid Basic authorization header encoding" in exc_b64.value.description

    req_multi_auth = Request(
        {
            "type": "http",
            "method": "POST",
            "server": ("127.0.0.1", 8080),
            "query_string": b"",
            "headers": [
                (b"content-type", b"application/x-www-form-urlencoded"),
                (b"authorization", b"Basic " + base64.b64encode(b"cid:csec")),
            ],
        }
    )
    req_multi_auth.body = AsyncMock(
        return_value=b"grant_type=client_credentials&client_secret=sec2"
    )
    with pytest.raises(OAuth2Error) as exc_multi:
        await oauth_token_endpoint(req_multi_auth, session)
    assert exc_multi.value.error == "invalid_client"
    assert "Multiple client authentication methods" in exc_multi.value.description

    req_mismatch = Request(
        {
            "type": "http",
            "method": "POST",
            "server": ("127.0.0.1", 8080),
            "query_string": b"",
            "headers": [
                (b"content-type", b"application/x-www-form-urlencoded"),
                (b"authorization", b"Basic " + base64.b64encode(b"cid1:csec")),
            ],
        }
    )
    req_mismatch.body = AsyncMock(return_value=b"grant_type=client_credentials&client_id=cid2")
    with pytest.raises(OAuth2Error) as exc_mis:
        await oauth_token_endpoint(req_mismatch, session)
    assert exc_mis.value.error == "invalid_client"
    assert "client_id mismatch" in exc_mis.value.description


@pytest.mark.asyncio
async def test_oauth_token_authorization_code_missing_and_expired() -> None:
    """Test OAuth authorization code missing, not found, expired, and reuse errors."""
    session = AsyncMock()
    mock_nested = MagicMock()
    mock_nested.__aenter__ = AsyncMock(return_value=None)
    mock_nested.__aexit__ = AsyncMock(return_value=None)
    session.begin_nested = MagicMock(return_value=mock_nested)
    session.add = MagicMock()

    req_code = Request(
        {
            "type": "http",
            "method": "POST",
            "server": ("127.0.0.1", 8080),
            "query_string": b"",
            "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
        }
    )
    req_code.body = AsyncMock(return_value=b"grant_type=authorization_code&code=testcode")
    with pytest.raises(OAuth2Error) as exc_ac_miss:
        await oauth_token_endpoint(req_code, session)
    assert exc_ac_miss.value.error == "invalid_request"
    assert "code, code_verifier, and redirect_uri required" in exc_ac_miss.value.description

    valid_body = (
        b"grant_type=authorization_code&code=testcode"
        b"&code_verifier=secret_verifier&redirect_uri=http://127.0.0.1/cb"
    )
    req_code.body = AsyncMock(return_value=valid_body)

    mock_res_none = MagicMock()
    mock_res_none.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_res_none
    with pytest.raises(OAuth2Error) as exc_ac_none:
        await oauth_token_endpoint(req_code, session)
    assert exc_ac_none.value.error == "invalid_grant"
    assert "Invalid authorization code" in exc_ac_none.value.description

    mock_code_rec = MagicMock(spec=OAuthAuthorizationCode)
    mock_code_rec.expires_at = datetime.now(UTC) - timedelta(minutes=5)
    mock_code_rec.consumed_at = None
    mock_code_rec.grant_id = uuid.uuid4()
    mock_code_rec.workspace_id = uuid.uuid4()
    mock_res_code = MagicMock()
    mock_res_code.scalar_one_or_none.return_value = mock_code_rec
    session.execute.return_value = mock_res_code
    with pytest.raises(OAuth2Error) as exc_ac_exp:
        await oauth_token_endpoint(req_code, session)
    assert exc_ac_exp.value.error == "invalid_grant"
    assert "Authorization code expired" in exc_ac_exp.value.description

    mock_code_rec.expires_at = datetime.now(UTC) + timedelta(minutes=5)
    mock_code_rec.consumed_at = datetime.now(UTC)
    with pytest.raises(OAuth2Error) as exc_ac_reuse:
        await oauth_token_endpoint(req_code, session)
    assert exc_ac_reuse.value.error == "invalid_grant"
    assert "Authorization code already consumed" in exc_ac_reuse.value.description


@pytest.mark.asyncio
async def test_oauth_token_authorization_code_client_inactive_and_redirect_uri() -> None:
    """Test OAuth authorization code inactive client and redirect_uri mismatch."""
    session = AsyncMock()
    valid_body = (
        b"grant_type=authorization_code&code=testcode"
        b"&code_verifier=secret_verifier&redirect_uri=http://127.0.0.1/cb"
    )
    req_code = Request(
        {
            "type": "http",
            "method": "POST",
            "server": ("127.0.0.1", 8080),
            "query_string": b"",
            "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
        }
    )
    req_code.body = AsyncMock(return_value=valid_body)

    mock_code_rec = MagicMock(spec=OAuthAuthorizationCode)
    mock_code_rec.expires_at = datetime.now(UTC) + timedelta(minutes=5)
    mock_code_rec.consumed_at = None
    mock_code_rec.client_id = uuid.uuid4()
    mock_code_rec.grant_id = uuid.uuid4()
    mock_code_rec.workspace_id = uuid.uuid4()
    mock_code_rec.code_challenge = "correct_challenge"
    mock_res_code = MagicMock()
    mock_res_code.scalar_one_or_none.return_value = mock_code_rec

    mock_client_inactive = MagicMock(spec=OAuthClient)
    mock_client_inactive.id = mock_code_rec.client_id
    mock_client_inactive.client_id = "test_cli"
    mock_client_inactive.status = "disabled"
    mock_res_client_inact = MagicMock()
    mock_res_client_inact.scalar_one_or_none.return_value = mock_client_inactive
    session.execute.side_effect = [mock_res_code, mock_res_client_inact]
    with pytest.raises(OAuth2Error) as exc_inact:
        await oauth_token_endpoint(req_code, session)
    assert exc_inact.value.error == "invalid_client"
    assert "Client is invalid or inactive" in exc_inact.value.description

    mock_client_active = MagicMock(spec=OAuthClient)
    mock_client_active.id = mock_code_rec.client_id
    mock_client_active.client_id = "test_cli"
    mock_client_active.client_type = "public"
    mock_client_active.status = "active"
    mock_res_client_act = MagicMock()
    mock_res_client_act.scalar_one_or_none.return_value = mock_client_active

    mock_code_rec.redirect_uri = "http://127.0.0.1/different_cb"
    session.execute.side_effect = [mock_res_code, mock_res_client_act]
    with pytest.raises(OAuth2Error) as exc_uri:
        await oauth_token_endpoint(req_code, session)
    assert exc_uri.value.error == "invalid_grant"
    assert "redirect_uri mismatch" in exc_uri.value.description


@pytest.mark.asyncio
async def test_oauth_token_authorization_code_pkce_and_resource_mismatch() -> None:
    """Test OAuth authorization code PKCE failure and resource mismatch."""
    session = AsyncMock()
    valid_body = (
        b"grant_type=authorization_code&code=testcode"
        b"&code_verifier=secret_verifier&redirect_uri=http://127.0.0.1/cb"
    )
    req_code = Request(
        {
            "type": "http",
            "method": "POST",
            "server": ("127.0.0.1", 8080),
            "query_string": b"",
            "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
        }
    )
    req_code.body = AsyncMock(return_value=valid_body)

    mock_code_rec = MagicMock(spec=OAuthAuthorizationCode)
    mock_code_rec.expires_at = datetime.now(UTC) + timedelta(minutes=5)
    mock_code_rec.consumed_at = None
    mock_code_rec.client_id = uuid.uuid4()
    mock_code_rec.grant_id = uuid.uuid4()
    mock_code_rec.workspace_id = uuid.uuid4()
    mock_code_rec.code_challenge = "correct_challenge"
    mock_code_rec.redirect_uri = "http://127.0.0.1/cb"
    mock_res_code = MagicMock()
    mock_res_code.scalar_one_or_none.return_value = mock_code_rec

    mock_client_active = MagicMock(spec=OAuthClient)
    mock_client_active.id = mock_code_rec.client_id
    mock_client_active.client_id = "test_cli"
    mock_client_active.client_type = "public"
    mock_client_active.status = "active"
    mock_res_client_act = MagicMock()
    mock_res_client_act.scalar_one_or_none.return_value = mock_client_active

    session.execute.side_effect = [mock_res_code, mock_res_client_act]
    with pytest.raises(OAuth2Error) as exc_pkce:
        await oauth_token_endpoint(req_code, session)
    assert exc_pkce.value.error == "invalid_grant"
    assert "PKCE code_verifier validation failed" in exc_pkce.value.description

    req_code_bad_cli = Request(
        {
            "type": "http",
            "method": "POST",
            "server": ("127.0.0.1", 8080),
            "query_string": b"",
            "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
        }
    )
    req_code_bad_cli.body = AsyncMock(return_value=valid_body + b"&client_id=wrong_cli")
    session.execute.side_effect = [mock_res_code, mock_res_client_act]
    with pytest.raises(OAuth2Error) as exc_ac_cli:
        await oauth_token_endpoint(req_code_bad_cli, session)
    assert exc_ac_cli.value.error == "invalid_grant"
    assert "client_id mismatch with authorization code" in exc_ac_cli.value.description

    mock_code_rec.resource = "http://127.0.0.1:8080/mcp/agent"
    req_code_bad_res = Request(
        {
            "type": "http",
            "method": "POST",
            "server": ("127.0.0.1", 8080),
            "query_string": b"",
            "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
        }
    )
    req_code_bad_res.body = AsyncMock(
        return_value=valid_body + b"&resource=http://127.0.0.1:8080/mcp/docs"
    )
    session.execute.side_effect = [mock_res_code, mock_res_client_act]
    with pytest.raises(OAuth2Error) as exc_ac_res:
        await oauth_token_endpoint(req_code_bad_res, session)
    assert exc_ac_res.value.error == "invalid_grant"
    assert "resource mismatch" in exc_ac_res.value.description


@pytest.mark.asyncio
async def test_oauth_token_refresh_token_missing_and_expired() -> None:
    """Test OAuth refresh token grant missing, reuse, and expired errors."""
    session = AsyncMock()

    req_rf_missing = Request(
        {
            "type": "http",
            "method": "POST",
            "server": ("127.0.0.1", 8080),
            "query_string": b"",
            "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
        }
    )
    req_rf_missing.body = AsyncMock(return_value=b"grant_type=refresh_token")
    with pytest.raises(OAuth2Error) as exc_rf_miss:
        await oauth_token_endpoint(req_rf_missing, session)
    assert exc_rf_miss.value.error == "invalid_request"
    assert "refresh_token parameter required" in exc_rf_miss.value.description

    req_rf_token = Request(
        {
            "type": "http",
            "method": "POST",
            "server": ("127.0.0.1", 8080),
            "query_string": b"",
            "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
        }
    )
    req_rf_token.body = AsyncMock(
        return_value=b"grant_type=refresh_token&refresh_token=rt_reused_123"
    )
    mock_rt_reuse = MagicMock(spec=OAuthRefreshToken)
    mock_rt_reuse.expires_at = datetime.now(UTC) + timedelta(days=1)
    mock_rt_reuse.revoked_at = datetime.now(UTC)
    mock_rt_reuse.grant_id = uuid.uuid4()
    mock_rt_reuse.workspace_id = uuid.uuid4()
    mock_res_rt_reuse = MagicMock()
    mock_res_rt_reuse.scalar_one_or_none.return_value = mock_rt_reuse
    session.execute.return_value = mock_res_rt_reuse
    with pytest.raises(OAuth2Error) as exc_reuse:
        await oauth_token_endpoint(req_rf_token, session)
    assert exc_reuse.value.error == "invalid_grant"
    assert "Refresh token reuse detected" in exc_reuse.value.description

    req_rf_notfound = Request(
        {
            "type": "http",
            "method": "POST",
            "server": ("127.0.0.1", 8080),
            "query_string": b"",
            "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
        }
    )
    req_rf_notfound.body = AsyncMock(
        return_value=b"grant_type=refresh_token&refresh_token=rt_unknown"
    )
    mock_res_none = MagicMock()
    mock_res_none.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_res_none
    with pytest.raises(OAuth2Error) as exc_rf_none:
        await oauth_token_endpoint(req_rf_notfound, session)
    assert exc_rf_none.value.error == "invalid_grant"
    assert "Invalid or expired refresh token" in exc_rf_none.value.description


@pytest.mark.asyncio
async def test_oauth_token_refresh_token_client_mismatch_and_revoked_parent() -> None:
    """Test OAuth refresh token client mismatch and revoked parent errors."""
    session = AsyncMock()

    mock_rt_valid = MagicMock(spec=OAuthRefreshToken)
    mock_rt_valid.expires_at = datetime.now(UTC) + timedelta(days=1)
    mock_rt_valid.revoked_at = None
    mock_rt_valid.client_id = uuid.uuid4()
    mock_rt_valid.grant_id = uuid.uuid4()
    mock_rt_valid.workspace_id = uuid.uuid4()
    mock_res_rt_valid = MagicMock()
    mock_res_rt_valid.scalar_one_or_none.return_value = mock_rt_valid

    req_rf_bad_cli = Request(
        {
            "type": "http",
            "method": "POST",
            "server": ("127.0.0.1", 8080),
            "query_string": b"",
            "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
        }
    )
    req_rf_bad_cli.body = AsyncMock(
        return_value=b"grant_type=refresh_token&refresh_token=rt_valid&client_id=wrong_client"
    )
    mock_cli_rt = MagicMock(spec=OAuthClient)
    mock_cli_rt.id = mock_rt_valid.client_id
    mock_cli_rt.client_id = "real_client"
    mock_cli_rt.client_type = "public"
    mock_res_cli_rt = MagicMock()
    mock_res_cli_rt.scalar_one_or_none.return_value = mock_cli_rt

    session.execute.side_effect = [mock_res_rt_valid, mock_res_cli_rt]
    with pytest.raises(OAuth2Error) as exc_rf_cli:
        await oauth_token_endpoint(req_rf_bad_cli, session)
    assert exc_rf_cli.value.error == "invalid_grant"
    assert "client_id mismatch with refresh token" in exc_rf_cli.value.description

    req_rf_ok = Request(
        {
            "type": "http",
            "method": "POST",
            "server": ("127.0.0.1", 8080),
            "query_string": b"",
            "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
        }
    )
    req_rf_ok.body = AsyncMock(return_value=b"grant_type=refresh_token&refresh_token=rt_valid")
    mock_grant_revoked = MagicMock(spec=OAuthGrant)
    mock_grant_revoked.revoked_at = datetime.now(UTC)
    mock_res_grant_rev = MagicMock()
    mock_res_grant_rev.scalar_one_or_none.return_value = mock_grant_revoked

    session.execute.side_effect = [mock_res_rt_valid, mock_res_cli_rt, mock_res_grant_rev]
    with pytest.raises(OAuth2Error) as exc_p_rev:
        await oauth_token_endpoint(req_rf_ok, session)
    assert exc_p_rev.value.error == "invalid_grant"
    assert "Parent grant is revoked" in exc_p_rev.value.description


@pytest.mark.asyncio
async def test_oauth_token_refresh_token_confidential_client_error() -> None:
    """Test OAuth refresh token requires client_secret for confidential clients."""
    session = AsyncMock()

    mock_rt_valid3 = MagicMock(spec=OAuthRefreshToken)
    mock_rt_valid3.expires_at = datetime.now(UTC) + timedelta(days=1)
    mock_rt_valid3.revoked_at = None
    mock_rt_valid3.client_id = uuid.uuid4()
    mock_rt_valid3.grant_id = uuid.uuid4()
    mock_rt_valid3.workspace_id = uuid.uuid4()
    mock_res_rt_valid3 = MagicMock()
    mock_res_rt_valid3.scalar_one_or_none.return_value = mock_rt_valid3

    mock_cli_conf = MagicMock(spec=OAuthClient)
    mock_cli_conf.id = mock_rt_valid3.client_id
    mock_cli_conf.client_id = "conf_client"
    mock_cli_conf.client_type = "confidential"
    mock_cli_conf.client_secret_hash = "h"
    mock_res_cli_conf = MagicMock()
    mock_res_cli_conf.scalar_one_or_none.return_value = mock_cli_conf

    req_rf_conf_no_sec = Request(
        {
            "type": "http",
            "method": "POST",
            "server": ("127.0.0.1", 8080),
            "query_string": b"",
            "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
        }
    )
    req_rf_conf_no_sec.body = AsyncMock(
        return_value=b"grant_type=refresh_token&refresh_token=rt_conf"
    )
    session.execute.side_effect = [mock_res_rt_valid3, mock_res_cli_conf]
    with pytest.raises(OAuth2Error) as exc_conf_sec:
        await oauth_token_endpoint(req_rf_conf_no_sec, session)
    assert exc_conf_sec.value.error == "invalid_client"
    assert "Confidential client authentication required" in exc_conf_sec.value.description


@pytest.mark.asyncio
async def test_oauth_token_refresh_token_success() -> None:
    """Test OAuth refresh token grant successful issuance."""
    session = AsyncMock()
    mock_nested = MagicMock()
    mock_nested.__aenter__ = AsyncMock(return_value=None)
    mock_nested.__aexit__ = AsyncMock(return_value=None)
    session.begin_nested = MagicMock(return_value=mock_nested)
    session.add = MagicMock()

    mock_rt_valid = MagicMock(spec=OAuthRefreshToken)
    mock_rt_valid.expires_at = datetime.now(UTC) + timedelta(days=1)
    mock_rt_valid.revoked_at = None
    mock_rt_valid.client_id = uuid.uuid4()
    mock_rt_valid.grant_id = uuid.uuid4()
    mock_rt_valid.workspace_id = uuid.uuid4()
    mock_res_rt_valid = MagicMock()
    mock_res_rt_valid.scalar_one_or_none.return_value = mock_rt_valid

    mock_cli_rt = MagicMock(spec=OAuthClient)
    mock_cli_rt.id = mock_rt_valid.client_id
    mock_cli_rt.client_id = "real_client"
    mock_cli_rt.client_type = "public"
    mock_res_cli_rt = MagicMock()
    mock_res_cli_rt.scalar_one_or_none.return_value = mock_cli_rt

    mock_grant_active = MagicMock(spec=OAuthGrant)
    mock_grant_active.id = mock_rt_valid.grant_id
    mock_grant_active.workspace_id = mock_rt_valid.workspace_id
    mock_grant_active.principal_id = uuid.uuid4()
    mock_grant_active.revoked_at = None
    mock_grant_active.surface = "agent"
    mock_grant_active.scopes = ["agent:read"]
    mock_grant_active.allowed_projects = None
    mock_grant_active.capability_mask = None
    mock_res_grant_active = MagicMock()
    mock_res_grant_active.scalar_one_or_none.return_value = mock_grant_active

    req_rf_ok = Request(
        {
            "type": "http",
            "method": "POST",
            "server": ("127.0.0.1", 8080),
            "query_string": b"",
            "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
        }
    )
    req_rf_ok.body = AsyncMock(return_value=b"grant_type=refresh_token&refresh_token=rt_valid")

    session.execute.side_effect = [mock_res_rt_valid, mock_res_cli_rt, mock_res_grant_active]
    resp_rf_success = await oauth_token_endpoint(req_rf_ok, session)
    assert resp_rf_success.status_code == 200
    rf_body = json.loads(resp_rf_success.body.decode())
    assert "access_token" in rf_body
    assert rf_body["token_type"] == "Bearer"


@pytest.mark.asyncio
async def test_oauth_revoke_endpoint_scenarios(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test RFC 7009 revocation endpoint for empty, refresh token, and access token."""
    session = AsyncMock()

    req_rev_empty = Request(
        {
            "type": "http",
            "method": "POST",
            "server": ("127.0.0.1", 8080),
            "query_string": b"",
            "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
        }
    )
    req_rev_empty.body = AsyncMock(return_value=b"token=")
    resp_empty = await oauth_revoke_endpoint(req_rev_empty, session)
    assert resp_empty.status_code == 200

    req_rev_rt = Request(
        {
            "type": "http",
            "method": "POST",
            "server": ("127.0.0.1", 8080),
            "query_string": b"",
            "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
        }
    )
    req_rev_rt.body = AsyncMock(return_value=b"token=rt_test_token_123")
    mock_rt_rec = MagicMock(spec=OAuthRefreshToken)
    mock_rt_rec.grant_id = uuid.uuid4()
    mock_rt_rec.workspace_id = uuid.uuid4()
    mock_res_rt = MagicMock()
    mock_res_rt.scalar_one_or_none.return_value = mock_rt_rec
    session.execute.return_value = mock_res_rt
    resp_rt = await oauth_revoke_endpoint(req_rev_rt, session)
    assert resp_rt.status_code == 200

    monkeypatch.setattr(
        oauth_mod,
        "verify_access_token",
        lambda _tok, _now=0: {
            "jti": str(uuid.uuid4()),
            "grant_id": str(uuid.uuid4()),
            "ws": str(uuid.uuid4()),
            "exp": time.time() + 900,
        },
    )
    req_rev_jwt = Request(
        {
            "type": "http",
            "method": "POST",
            "server": ("127.0.0.1", 8080),
            "query_string": b"",
            "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
        }
    )
    req_rev_jwt.body = AsyncMock(return_value=b"token=eyJhbGciOiJSUzI1NiJ9.abc.def")
    resp_jwt_rev = await oauth_revoke_endpoint(req_rev_jwt, session)
    assert resp_jwt_rev.status_code == 200


@pytest.mark.asyncio
async def test_oauth_device_and_authorize_endpoints() -> None:
    """Test device authorization missing fields and authorize validation error redirects."""
    session = AsyncMock()

    req_dev_miss = Request(
        {
            "type": "http",
            "method": "POST",
            "server": ("127.0.0.1", 8080),
            "query_string": b"",
            "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
        }
    )
    req_dev_miss.body = AsyncMock(return_value=b"client_id=&resource=")
    with pytest.raises(OAuth2Error) as exc_dev_miss:
        await oauth_device_authorize(req_dev_miss, session)
    assert exc_dev_miss.value.error == "invalid_request"
    assert "client_id and resource required" in exc_dev_miss.value.description

    req_auth = Request(
        {
            "type": "http",
            "method": "GET",
            "server": ("127.0.0.1", 8080),
            "query_string": b"",
            "headers": [],
        }
    )
    with pytest.raises(OAuth2Error) as exc_resp_type:
        await oauth_authorize(
            request=req_auth,
            session=session,
            response_type="token",
            client_id="cli1",
            redirect_uri="http://127.0.0.1/cb",
            code_challenge="a" * 45,
            code_challenge_method="S256",
            state="state123",
        )
    assert exc_resp_type.value.error == "unsupported_response_type"

    with pytest.raises(OAuth2Error) as exc_chal_len:
        await oauth_authorize(
            request=req_auth,
            session=session,
            response_type="code",
            client_id="cli1",
            redirect_uri="http://127.0.0.1/cb",
            code_challenge="short",
            code_challenge_method="S256",
            state="state123",
        )
    assert exc_chal_len.value.error == "invalid_request"
    assert "between 43 and 128" in exc_chal_len.value.description

    mock_cli_auth = MagicMock(spec=OAuthClient)
    mock_cli_auth.client_id = "cli1"
    mock_cli_auth.status = "active"
    mock_cli_auth.redirect_uris = ["http://127.0.0.1/cb"]
    mock_res_auth = MagicMock()
    mock_res_auth.scalar_one_or_none.return_value = mock_cli_auth
    session.execute.return_value = mock_res_auth

    resp_bad_scope = await oauth_authorize(
        request=req_auth,
        session=session,
        response_type="code",
        client_id="cli1",
        redirect_uri="http://127.0.0.1/cb",
        code_challenge="a" * 45,
        code_challenge_method="S256",
        state="state123",
        scope="bogus_unknown_scope",
        resource="http://127.0.0.1:8080/mcp/agent",
    )
    assert resp_bad_scope.status_code == 302
    assert "error=invalid_scope" in resp_bad_scope.headers["location"]
