# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Comprehensive unit and integration tests for Workload Identity Federation.

RFC 8693 Token Exchange (KAN-74).
"""

from __future__ import annotations

import base64
import time
import uuid
from collections.abc import Iterator  # noqa: TC003
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from joserfc import jwt
from joserfc.jwk import KeySet, OctKey
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

import kanban.auth.oidc.workload as workload_module
from database.models.workload_identity import WorkloadIdentityPolicy
from kanban.api.deps import PrincipalContext
from kanban.auth.oidc.discovery import JwksCache, OidcError
from kanban.auth.oidc.workload import (
    _extract_unverified_header_and_claims,
    validate_workload_jwt,
)
from kanban.oauth.jwt import verify_access_token
from kanban.oauth.server import OAuth2Error
from kanban.tests.fixtures.fake_idp import FakeIdP
from kanban.tests.security.helpers import create_user, create_workspace

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


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


@pytest.fixture
def fake_idp() -> FakeIdP:
    """Provide in-memory fake OIDC IdP."""
    return FakeIdP(
        issuer="https://token.actions.githubusercontent.com",
        client_id="https://kanban.example.com",
    )


@pytest.fixture
def idp_client(fake_idp: FakeIdP) -> Iterator[httpx.AsyncClient]:
    """Provide AsyncClient routed to FakeIdP."""
    client = httpx.AsyncClient(transport=fake_idp.as_transport(), base_url=fake_idp.issuer)
    workload_module._test_workload_client = client  # noqa: SLF001
    yield client
    workload_module._test_workload_client = None  # noqa: SLF001


async def _as_admin_aal2(api_env: ApiEnv, user: SeededUser) -> None:
    """Enroll confirmed TOTP factor and elevate test client to AAL2 session."""
    await api_env.seed.execute(
        text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'test-kid-1')"),
        {
            "p_id": user.id,
            "blob": b"\x01" + b"\x00" * 28,
            "dek": b"\x01" + b"\x00" * 44,
        },
    )
    res = await api_env.seed.execute(
        text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
        {"p_id": user.id},
    )
    p_row = res.mappings().first()
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
        is_server_admin=True,
    )


@pytest.mark.asyncio
async def test_validate_workload_jwt_valid_rs256(
    db_session: AsyncSession,
    fake_idp: FakeIdP,
    idp_client: httpx.AsyncClient,
) -> None:
    """Verify valid RS256 workload token succeeds and claims are returned."""
    ws_id = await create_workspace(db_session, name="Workload WS")
    p_id = await create_user(db_session, ws_id, handle="admin-user", display_name="Admin")
    await db_session.flush()

    policy = WorkloadIdentityPolicy(
        workspace_id=ws_id,
        name="GitHub Actions Main",
        issuer="https://token.actions.githubusercontent.com",
        client_id="https://kanban.example.com",
        subject_pattern="repo:org/repo:ref:refs/heads/*",
        required_claims_json={"repository_owner": "org"},
        surface="agent",
        scopes=["agent:read", "agent:write"],
        capability_mask=255,
        created_by_id=p_id,
    )
    db_session.add(policy)
    await db_session.flush()

    now = int(time.time())
    token = fake_idp.create_id_token(
        subject="repo:org/repo:ref:refs/heads/main",
        issuer="https://token.actions.githubusercontent.com",
        audience="https://kanban.example.com",
        iat=now,
        exp=now + 300,
        custom_claims={"jti": str(uuid.uuid4()), "repository_owner": "org"},
    )

    claims = await validate_workload_jwt(
        session=db_session,
        raw_jwt=token,
        policy=policy,
        client=idp_client,
        now=now,
    )
    assert claims["sub"] == "repo:org/repo:ref:refs/heads/main"
    assert claims["repository_owner"] == "org"


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_idp")
async def test_validate_workload_jwt_forbidden_algs(
    db_session: AsyncSession,
    idp_client: httpx.AsyncClient,
) -> None:
    """Verify alg='none' and symmetric HMAC algorithms (HS*) are rejected."""
    ws_id = await create_workspace(db_session, name="Workload Alg WS")
    policy = WorkloadIdentityPolicy(
        workspace_id=ws_id,
        name="Alg Policy",
        issuer="https://token.actions.githubusercontent.com",
        client_id="https://kanban.example.com",
        subject_pattern="*",
        surface="agent",
    )
    db_session.add(policy)
    await db_session.flush()

    # 1. Reject unsigned alg='none'
    raw_none = (
        "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0."
    )
    with pytest.raises(OAuth2Error) as exc_none:
        await validate_workload_jwt(
            session=db_session,
            raw_jwt=raw_none,
            policy=policy,
            client=idp_client,
        )
    assert "Forbidden or unsupported signing algorithm" in str(exc_none.value.description)

    # 2. Reject HS256 symmetric token
    oct_key = OctKey.import_key({"kty": "oct", "k": "c2VjcmV0LWtleS1mb3ItaHMtbW9jaw"})
    raw_hs = jwt.encode({"alg": "HS256", "typ": "JWT"}, {"sub": "test"}, oct_key)
    with pytest.raises(OAuth2Error) as exc_hs:
        await validate_workload_jwt(
            session=db_session,
            raw_jwt=raw_hs,
            policy=policy,
            client=idp_client,
        )
    assert "Forbidden or unsupported signing algorithm" in str(exc_hs.value.description)


@pytest.mark.asyncio
async def test_validate_workload_jwt_claims_enforcement(
    db_session: AsyncSession,
    fake_idp: FakeIdP,
    idp_client: httpx.AsyncClient,
) -> None:
    """Verify strict validation of iss, aud, exp, nbf, iat, sub, and required_claims."""
    ws_id = await create_workspace(db_session, name="Workload Claims WS")
    policy = WorkloadIdentityPolicy(
        workspace_id=ws_id,
        name="Strict Policy",
        issuer="https://token.actions.githubusercontent.com",
        client_id="https://kanban.example.com",
        subject_pattern="repo:org/repo:env:prod",
        required_claims_json={"environment": "production", "runner_environment": "github-hosted"},
        surface="agent",
    )
    db_session.add(policy)
    await db_session.flush()

    now = int(time.time())

    # 1. Issuer mismatch
    t_bad_iss = fake_idp.create_id_token(
        subject="repo:org/repo:env:prod",
        issuer="https://evil.idp.com",
        audience="https://kanban.example.com",
        iat=now,
        exp=now + 300,
    )
    with pytest.raises(OAuth2Error) as exc_iss:
        await validate_workload_jwt(
            session=db_session,
            raw_jwt=t_bad_iss,
            policy=policy,
            client=idp_client,
            now=now,
        )
    assert "does not match policy issuer" in str(exc_iss.value.description)

    # 2. Audience mismatch
    t_bad_aud = fake_idp.create_id_token(
        subject="repo:org/repo:env:prod",
        issuer="https://token.actions.githubusercontent.com",
        audience="https://different.app.com",
        iat=now,
        exp=now + 300,
    )
    with pytest.raises(OAuth2Error) as exc_aud:
        await validate_workload_jwt(
            session=db_session,
            raw_jwt=t_bad_aud,
            policy=policy,
            client=idp_client,
            now=now,
        )
    assert "does not match policy client_id" in str(exc_aud.value.description)

    # 3. Expired token
    t_exp = fake_idp.create_id_token(
        subject="repo:org/repo:env:prod",
        issuer="https://token.actions.githubusercontent.com",
        audience="https://kanban.example.com",
        iat=now - 600,
        exp=now - 10,
    )
    with pytest.raises(OAuth2Error) as exc_exp:
        await validate_workload_jwt(
            session=db_session,
            raw_jwt=t_exp,
            policy=policy,
            client=idp_client,
            now=now,
        )
    assert "expired" in str(exc_exp.value.description)

    # 4. Token issued too far in past (iat > 600s old)
    t_old_iat = fake_idp.create_id_token(
        subject="repo:org/repo:env:prod",
        issuer="https://token.actions.githubusercontent.com",
        audience="https://kanban.example.com",
        iat=now - 650,
        exp=now + 300,
    )
    with pytest.raises(OAuth2Error) as exc_iat:
        await validate_workload_jwt(
            session=db_session,
            raw_jwt=t_old_iat,
            policy=policy,
            client=idp_client,
            now=now,
        )
    assert "exceeds maximum allowed" in str(exc_iat.value.description)

    # 5. Subject mismatch
    t_bad_sub = fake_idp.create_id_token(
        subject="repo:org/other:env:prod",
        issuer="https://token.actions.githubusercontent.com",
        audience="https://kanban.example.com",
        iat=now,
        exp=now + 300,
        custom_claims={"environment": "production", "runner_environment": "github-hosted"},
    )
    with pytest.raises(OAuth2Error) as exc_sub:
        await validate_workload_jwt(
            session=db_session,
            raw_jwt=t_bad_sub,
            policy=policy,
            client=idp_client,
            now=now,
        )
    assert "does not match policy pattern" in str(exc_sub.value.description)

    # 6. Missing required claims
    t_missing_claims = fake_idp.create_id_token(
        subject="repo:org/repo:env:prod",
        issuer="https://token.actions.githubusercontent.com",
        audience="https://kanban.example.com",
        iat=now,
        exp=now + 300,
        custom_claims={"environment": "staging"},
    )
    with pytest.raises(OAuth2Error) as exc_req:
        await validate_workload_jwt(
            session=db_session,
            raw_jwt=t_missing_claims,
            policy=policy,
            client=idp_client,
            now=now,
        )
    assert "value mismatch" in str(exc_req.value.description)


@pytest.mark.asyncio
async def test_validate_workload_jwt_atomic_jti_replay_defense(
    db_session: AsyncSession,
    fake_idp: FakeIdP,
    idp_client: httpx.AsyncClient,
) -> None:
    """Verify duplicate JTI insertion raises 401 WORKLOAD_TOKEN_REPLAYED."""
    ws_id = await create_workspace(db_session, name="Replay WS")
    policy = WorkloadIdentityPolicy(
        workspace_id=ws_id,
        name="Replay Test Policy",
        issuer="https://token.actions.githubusercontent.com",
        client_id="https://kanban.example.com",
        subject_pattern="*",
        surface="agent",
    )
    db_session.add(policy)
    await db_session.flush()

    now = int(time.time())
    token_jti = f"replay-jti-{uuid.uuid4()}"
    token = fake_idp.create_id_token(
        subject="repo:org/repo:ref:main",
        issuer="https://token.actions.githubusercontent.com",
        audience="https://kanban.example.com",
        iat=now,
        exp=now + 300,
        custom_claims={"jti": token_jti},
    )

    # First exchange succeeds
    claims1 = await validate_workload_jwt(
        session=db_session,
        raw_jwt=token,
        policy=policy,
        client=idp_client,
        now=now,
    )
    assert claims1["jti"] == token_jti

    # Second exchange with identical token/JTI must fail with 401 WORKLOAD_TOKEN_REPLAYED
    with pytest.raises(OAuth2Error) as exc_replay:
        await validate_workload_jwt(
            session=db_session,
            raw_jwt=token,
            policy=policy,
            client=idp_client,
            now=now,
        )
    err = exc_replay.value
    assert err.error == "WORKLOAD_TOKEN_REPLAYED"
    assert err.status_code == 401


@pytest.mark.asyncio
@pytest.mark.usefixtures("idp_client")
async def test_oauth_token_exchange_endpoint(
    api_env: ApiEnv,
    fake_idp: FakeIdP,
) -> None:
    """Verify POST /oauth/token token-exchange grant type and discovery metadata."""
    ws_id = api_env.workspace_id
    policy = WorkloadIdentityPolicy(
        workspace_id=ws_id,
        name="CI Policy",
        issuer="https://token.actions.githubusercontent.com",
        client_id="https://kanban.example.com",
        subject_pattern="repo:org/*",
        surface="agent",
        scopes=["agent:read", "agent:write"],
        capability_mask=15,
        allowed_cidrs=["127.0.0.1/32", "192.168.1.0/24"],
        max_ttl_seconds=1800,
    )
    api_env.seed.add(policy)
    await api_env.seed.commit()

    # 1. Verify discovery metadata includes token-exchange
    res_meta = await api_env.client.get("/.well-known/oauth-authorization-server")
    assert res_meta.status_code == 200
    meta_json = res_meta.json()
    assert "urn:ietf:params:oauth:grant-type:token-exchange" in meta_json["grant_types_supported"]
    assert "token_exchange_token_types_supported" in meta_json

    # 2. Test token exchange with FakeIdP mock
    now = int(time.time())
    id_token = fake_idp.create_id_token(
        subject="repo:org/app:ref:main",
        issuer="https://token.actions.githubusercontent.com",
        audience="https://kanban.example.com",
        iat=now,
        exp=now + 300,
        custom_claims={"jti": f"ci-{uuid.uuid4()}"},
    )

    mock_doc = AsyncMock()
    mock_doc.jwks_uri = "https://token.actions.githubusercontent.com/.well-known/jwks.json"
    keyset = KeySet.import_key_set({"keys": [fake_idp.jwk_public_dict]})

    with (
        patch("kanban.auth.oidc.workload.fetch_discovery", return_value=mock_doc),
        patch.object(JwksCache, "get_keyset", return_value=keyset),
    ):
        # Successful exchange
        res_ex = await api_env.client.post(
            "/oauth/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                "subject_token": id_token,
                "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
            },
            headers={"X-Forwarded-For": "127.0.0.1"},
        )
        assert res_ex.status_code == 200, res_ex.text
        data = res_ex.json()
        assert "access_token" in data
        assert data["token_type"] == "Bearer"
        assert data["issued_token_type"] == "urn:ietf:params:oauth:token-type:access_token"
        assert data["expires_in"] <= 1800
        assert "refresh_token" not in data

        # Verify minted access token claims
        claims = verify_access_token(data["access_token"])
        assert claims["token_kind"] == "workload"
        assert claims["surface"] == "agent"
        assert claims["capability_mask"] == 15
        assert claims["workload_sub"] == "repo:org/app:ref:main"

        # CIDR rejection (client IP outside allowed CIDRs)
        id_token2 = fake_idp.create_id_token(
            subject="repo:org/app:ref:main",
            issuer="https://token.actions.githubusercontent.com",
            audience="https://kanban.example.com",
            iat=now,
            exp=now + 300,
            custom_claims={"jti": f"ci-{uuid.uuid4()}"},
        )
        res_cidr_blocked = await api_env.client.post(
            "/oauth/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                "subject_token": id_token2,
                "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
            },
            headers={"X-Forwarded-For": "10.0.0.1"},
        )
        assert res_cidr_blocked.status_code == 403


@pytest.mark.asyncio
async def test_admin_workload_identities_crud(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Verify Depends(require_admin_aal2) CRUD routes for workload identities."""
    admin = await make_user("admin_wl_user", workspace_role="WORKSPACE_ADMIN")
    await _as_admin_aal2(api_env, admin)

    # 1. Create policy
    res_create = await api_env.client.post(
        "/api/v1/admin/workload-identities",
        json={
            "name": "GitLab CI Runner",
            "issuer": "https://gitlab.example.com",
            "client_id": "kanban-mcp",
            "subject_pattern": "project_path:group/project:*",
            "required_claims_json": {"ref_type": "branch"},
            "surface": "agent",
            "scopes": ["agent:read", "agent:write"],
            "capability_mask": 31,
            "max_ttl_seconds": 3600,
        },
    )
    assert res_create.status_code == 201, res_create.text
    pol = res_create.json()
    pol_id = pol["id"]
    assert pol["name"] == "GitLab CI Runner"

    # 2. List policies
    res_list = await api_env.client.get("/api/v1/admin/workload-identities")
    assert res_list.status_code == 200
    assert len(res_list.json()) >= 1

    # 3. Get single policy
    res_get = await api_env.client.get(f"/api/v1/admin/workload-identities/{pol_id}")
    assert res_get.status_code == 200
    assert res_get.json()["id"] == pol_id

    # 4. Patch policy
    res_patch = await api_env.client.patch(
        f"/api/v1/admin/workload-identities/{pol_id}",
        json={"name": "GitLab CI Production", "capability_mask": 7},
    )
    assert res_patch.status_code == 200
    assert res_patch.json()["name"] == "GitLab CI Production"
    assert res_patch.json()["capability_mask"] == 7

    # 5. Delete policy
    res_del = await api_env.client.delete(f"/api/v1/admin/workload-identities/{pol_id}")
    assert res_del.status_code == 204

    # 6. Verify 404 after deletion
    res_get404 = await api_env.client.get(f"/api/v1/admin/workload-identities/{pol_id}")
    assert res_get404.status_code == 404


@pytest.mark.asyncio
async def test_validate_workload_jwt_edge_cases_and_coverage(  # noqa: PLR0915
    db_session: AsyncSession,
    fake_idp: FakeIdP,
    idp_client: httpx.AsyncClient,
) -> None:
    """Verify all parser and validation error branches for complete coverage."""
    ws_id = await create_workspace(db_session, name="Edge Cases WS")
    policy = WorkloadIdentityPolicy(
        workspace_id=ws_id,
        name="Edge Policy",
        issuer="https://token.actions.githubusercontent.com",
        client_id="https://kanban.example.com",
        subject_pattern="repo:org/exact-sub",
        required_claims_json={"roles": ["reader", "deployer"], "flag": True},
        surface="agent",
    )
    db_session.add(policy)
    await db_session.flush()

    now = int(time.time())

    # 1. Malformed JWT segments
    with pytest.raises(OAuth2Error) as exc_mal:
        _extract_unverified_header_and_claims("only.two")
    assert "dot-separated segments" in str(exc_mal.value.description)

    with pytest.raises(OAuth2Error) as exc_b64:
        _extract_unverified_header_and_claims("not-valid-b64.part2.part3")
    assert "Failed to parse JWT segment" in str(exc_b64.value.description)

    # Base64 encoded array instead of object
    arr_b64 = base64.urlsafe_b64encode(b"[1, 2, 3]").decode("ascii")
    with pytest.raises(OAuth2Error) as exc_arr:
        _extract_unverified_header_and_claims(f"{arr_b64}.{arr_b64}.sig")
    assert "JSON root must be an object" in str(exc_arr.value.description)

    # 2. OIDC discovery / JWKS error
    with patch("kanban.auth.oidc.workload.fetch_discovery", side_effect=OidcError("Net down")):
        good_tok = fake_idp.create_id_token(
            subject="repo:org/exact-sub",
            issuer="https://token.actions.githubusercontent.com",
            audience="https://kanban.example.com",
            iat=now,
            exp=now + 300,
        )
        with pytest.raises(OAuth2Error) as exc_oidc:
            await validate_workload_jwt(
                session=db_session,
                raw_jwt=good_tok,
                policy=policy,
                client=idp_client,
                now=now,
            )
        assert "OIDC discovery/JWKS resolution failed" in str(exc_oidc.value.description)

    # 3. Signature validation failure (tampered token body)
    parts = good_tok.split(".")
    tampered_claims = base64.urlsafe_b64encode(b'{"sub":"hacked"}').decode("ascii")
    tampered_token = f"{parts[0]}.{tampered_claims}.{parts[2]}"
    with pytest.raises(OAuth2Error) as exc_sig:
        await validate_workload_jwt(
            session=db_session,
            raw_jwt=tampered_token,
            policy=policy,
            client=idp_client,
            now=now,
        )
    assert "JWT signature validation failed" in str(exc_sig.value.description)

    # 4. Audience variants
    # aud as matching list
    token_aud_list = fake_idp.create_id_token(
        subject="repo:org/exact-sub",
        issuer="https://token.actions.githubusercontent.com",
        audience="https://kanban.example.com",
        iat=now,
        exp=now + 300,
        custom_claims={
            "aud": ["https://kanban.example.com", "other-aud"],
            "roles": ["reader", "deployer", "admin"],
            "flag": True,
            "jti": str(uuid.uuid4()),
        },
    )
    res_aud_list = await validate_workload_jwt(
        session=db_session,
        raw_jwt=token_aud_list,
        policy=policy,
        client=idp_client,
        now=now,
    )
    assert res_aud_list["sub"] == "repo:org/exact-sub"

    # aud as non-matching list
    token_bad_aud_list = fake_idp.create_id_token(
        subject="repo:org/exact-sub",
        issuer="https://token.actions.githubusercontent.com",
        audience="https://kanban.example.com",
        iat=now,
        exp=now + 300,
        custom_claims={"aud": ["other-aud"], "jti": str(uuid.uuid4())},
    )
    with pytest.raises(OAuth2Error) as exc_bad_aud_list:
        await validate_workload_jwt(
            session=db_session,
            raw_jwt=token_bad_aud_list,
            policy=policy,
            client=idp_client,
            now=now,
        )
    assert "does not match policy client_id" in str(exc_bad_aud_list.value.description)

    # aud missing
    token_no_aud = fake_idp.create_id_token(
        subject="repo:org/exact-sub",
        issuer="https://token.actions.githubusercontent.com",
        audience="https://kanban.example.com",
        iat=now,
        exp=now + 300,
        custom_claims={"aud": None, "jti": str(uuid.uuid4())},
    )
    with pytest.raises(OAuth2Error) as exc_no_aud:
        await validate_workload_jwt(
            session=db_session,
            raw_jwt=token_no_aud,
            policy=policy,
            client=idp_client,
            now=now,
        )
    assert "missing aud claim" in str(exc_no_aud.value.description)

    # 5. Missing / non-numeric exp
    token_bad_exp = fake_idp.create_id_token(
        subject="repo:org/exact-sub",
        issuer="https://token.actions.githubusercontent.com",
        audience="https://kanban.example.com",
        iat=now,
        exp=now + 300,
        custom_claims={"exp": "not-a-number", "jti": str(uuid.uuid4())},
    )
    with pytest.raises(OAuth2Error) as exc_bad_exp:
        await validate_workload_jwt(
            session=db_session,
            raw_jwt=token_bad_exp,
            policy=policy,
            client=idp_client,
            now=now,
        )
    assert "missing valid numeric exp claim" in str(exc_bad_exp.value.description)

    # 6. nbf in future vs nbf in past
    token_future_nbf = fake_idp.create_id_token(
        subject="repo:org/exact-sub",
        issuer="https://token.actions.githubusercontent.com",
        audience="https://kanban.example.com",
        iat=now,
        exp=now + 300,
        custom_claims={"nbf": now + 120, "jti": str(uuid.uuid4())},
    )
    with pytest.raises(OAuth2Error) as exc_nbf:
        await validate_workload_jwt(
            session=db_session,
            raw_jwt=token_future_nbf,
            policy=policy,
            client=idp_client,
            now=now,
        )
    assert "Token not yet valid (nbf)" in str(exc_nbf.value.description)

    # 7. iat in future or non-numeric iat
    token_future_iat = fake_idp.create_id_token(
        subject="repo:org/exact-sub",
        issuer="https://token.actions.githubusercontent.com",
        audience="https://kanban.example.com",
        iat=now + 200,
        exp=now + 300,
        custom_claims={"jti": str(uuid.uuid4())},
    )
    with pytest.raises(OAuth2Error) as exc_future_iat:
        await validate_workload_jwt(
            session=db_session,
            raw_jwt=token_future_iat,
            policy=policy,
            client=idp_client,
            now=now,
        )
    assert "exceeds maximum allowed" in str(exc_future_iat.value.description)

    token_no_iat = fake_idp.create_id_token(
        subject="repo:org/exact-sub",
        issuer="https://token.actions.githubusercontent.com",
        audience="https://kanban.example.com",
        iat=now,
        exp=now + 300,
        custom_claims={"iat": "bad", "jti": str(uuid.uuid4())},
    )
    with pytest.raises(OAuth2Error) as exc_no_iat:
        await validate_workload_jwt(
            session=db_session,
            raw_jwt=token_no_iat,
            policy=policy,
            client=idp_client,
            now=now,
        )
    assert "missing valid numeric iat claim" in str(exc_no_iat.value.description)

    # 8. sub non-string or missing
    token_bad_sub = fake_idp.create_id_token(
        subject="repo:org/exact-sub",
        issuer="https://token.actions.githubusercontent.com",
        audience="https://kanban.example.com",
        iat=now,
        exp=now + 300,
        custom_claims={"sub": 12345, "jti": str(uuid.uuid4())},
    )
    with pytest.raises(OAuth2Error) as exc_no_sub:
        await validate_workload_jwt(
            session=db_session,
            raw_jwt=token_bad_sub,
            policy=policy,
            client=idp_client,
            now=now,
        )
    assert "missing valid string sub claim" in str(exc_no_sub.value.description)

    # 9. required claims subset mismatch
    token_subset_mismatch = fake_idp.create_id_token(
        subject="repo:org/exact-sub",
        issuer="https://token.actions.githubusercontent.com",
        audience="https://kanban.example.com",
        iat=now,
        exp=now + 300,
        custom_claims={"roles": ["reader"], "flag": True, "jti": str(uuid.uuid4())},
    )
    with pytest.raises(OAuth2Error) as exc_subset:
        await validate_workload_jwt(
            session=db_session,
            raw_jwt=token_subset_mismatch,
            policy=policy,
            client=idp_client,
            now=now,
        )
    assert "required subset" in str(exc_subset.value.description)

    # 10. missing jti
    token_no_jti = fake_idp.create_id_token(
        subject="repo:org/exact-sub",
        issuer="https://token.actions.githubusercontent.com",
        audience="https://kanban.example.com",
        iat=now,
        exp=now + 300,
        custom_claims={"roles": ["reader", "deployer"], "flag": True, "jti": None},
    )
    with pytest.raises(OAuth2Error) as exc_no_jti:
        await validate_workload_jwt(
            session=db_session,
            raw_jwt=token_no_jti,
            policy=policy,
            client=idp_client,
            now=now,
        )
    assert "missing valid string jti claim" in str(exc_no_jti.value.description)
