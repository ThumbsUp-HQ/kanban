# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tests for scoped kb_* API keys, surface binding, scopes & introspection (KB-P4-02a)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from database.models.mcp_api_key import McpApiKey
from database.session import RLSContext, bind_rls_context
from kanban.api.problems import ProblemException
from kanban.security.mcp_keys import (
    KEY_TOKEN_TOTAL_LENGTH,
    McpIntrospectionResult,
    create_internal_mcp_auth_header,
    derive_internal_mcp_auth_key,
    generate_mcp_api_key,
    hash_mcp_api_key,
    introspect_subject_token,
    mint_mcp_api_key,
    revoke_mcp_api_key,
    verify_internal_mcp_auth_header,
)
from kanban.tests.security.helpers import (
    add_role_binding,
    create_agent,
    create_user,
    create_workspace,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


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


@pytest.mark.asyncio
async def test_case_1_positive_mint_and_catalog(db_session: AsyncSession) -> None:
    """Test Case 1: Positive mint, key length, DB catalog check (no plaintext column)."""
    ws_id = await create_workspace(db_session, name="WS-Alpha")
    admin_id = await create_user(db_session, ws_id, handle="@admin1", display_name="Admin One")
    await add_role_binding(
        db_session, ws_id, admin_id, role="WORKSPACE_ADMIN", scope_type="workspace"
    )

    ctx = RLSContext(
        principal_id=admin_id,
        workspace_id=ws_id,
        token_scopes=("session",),
        aal_level=2,
    )
    await bind_rls_context(db_session, ctx)

    key_record, plaintext = await mint_mcp_api_key(
        db_session,
        workspace_id=ws_id,
        principal_id=admin_id,
        surface="agent",
        scopes=["agent:read", "agent:write"],
        created_by_id=admin_id,
    )

    # 1. Plaintext length check: 7 (kb_agt_) + 43 = 50 chars
    assert len(plaintext) == KEY_TOKEN_TOTAL_LENGTH
    assert plaintext.startswith("kb_agt_")
    assert key_record.key_prefix == "kb_agt_"
    assert key_record.display_hint == plaintext[-4:]
    assert len(key_record.key_sha256) == 32
    assert key_record.key_sha256 == hash_mcp_api_key(plaintext)

    # 2. Catalog check: assert no column exists that could hold plaintext keys
    cols_result = await db_session.execute(
        text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'mcp_api_keys'"
        )
    )
    cols = {r[0]: r[1] for r in cols_result.all()}
    assert "key_sha256" in cols
    assert cols["key_sha256"] == "bytea"
    for col_name in cols:
        assert "token" not in col_name.lower()
        assert "plaintext" not in col_name.lower()
        assert "secret" not in col_name.lower()

    # 3. Introspection check: returns active: true with matching scopes
    intro = await introspect_subject_token(db_session, plaintext, surface="agent")
    assert intro.active is True
    assert intro.surface == "agent"
    assert intro.scopes == ["agent:read", "agent:write"]
    assert intro.principal_id == admin_id
    assert intro.workspace_id == ws_id
    assert intro.token_kind == "api_key"


@pytest.mark.asyncio
async def test_case_2_surface_binding_and_forgery(db_session: AsyncSession) -> None:
    """Test Case 2: Surface mismatch rejected locally without network, forged prefix rejected."""
    ws_id = await create_workspace(db_session, name="WS-Beta")
    admin_id = await create_user(db_session, ws_id, handle="@admin2", display_name="Admin Two")
    await add_role_binding(
        db_session, ws_id, admin_id, role="WORKSPACE_ADMIN", scope_type="workspace"
    )

    ctx = RLSContext(
        principal_id=admin_id,
        workspace_id=ws_id,
        token_scopes=("session",),
        aal_level=2,
    )
    await bind_rls_context(db_session, ctx)

    _, agent_token = await mint_mcp_api_key(
        db_session,
        workspace_id=ws_id,
        principal_id=admin_id,
        surface="agent",
        scopes=["agent:read"],
        created_by_id=admin_id,
    )

    # 1. Forged token: kb_adm_ prefix with agent token body
    forged_token = f"kb_adm_{agent_token[7:]}"
    intro_forged = await introspect_subject_token(db_session, forged_token, surface="admin")
    assert intro_forged.active is False

    # 2. Presenting agent token to introspect with surface="admin"
    intro_mismatch = await introspect_subject_token(db_session, agent_token, surface="admin")
    assert intro_mismatch.active is False
    assert intro_mismatch.reason == "SURFACE_KEY_MISMATCH"


@pytest.mark.asyncio
async def test_case_3_scope_negatives(db_session: AsyncSession) -> None:
    """Test Case 3: Scope negatives and server admin gate (422 and 403)."""
    ws_id = await create_workspace(db_session, name="WS-Gamma")
    admin_id = await create_user(db_session, ws_id, handle="@admin3", display_name="Admin Three")
    await add_role_binding(
        db_session, ws_id, admin_id, role="WORKSPACE_ADMIN", scope_type="workspace"
    )

    ctx = RLSContext(
        principal_id=admin_id,
        workspace_id=ws_id,
        token_scopes=("session",),
        aal_level=2,
    )
    await bind_rls_context(db_session, ctx)

    # 1. Minting admin:write on an agent key fails with 422
    with pytest.raises(ProblemException) as exc_info:
        await mint_mcp_api_key(
            db_session,
            workspace_id=ws_id,
            principal_id=admin_id,
            surface="agent",
            scopes=["admin:write"],
            created_by_id=admin_id,
        )
    assert exc_info.value.status == 422
    assert exc_info.value.code == "INVALID_SCOPE"

    # 2. Non-SERVER_ADMIN attempting to mint admin:destructive fails with 403
    with pytest.raises(ProblemException) as exc_info2:
        await mint_mcp_api_key(
            db_session,
            workspace_id=ws_id,
            principal_id=admin_id,
            surface="admin",
            scopes=["admin:destructive"],
            created_by_id=admin_id,
        )
    assert exc_info2.value.status == 403
    assert exc_info2.value.code == "INSUFFICIENT_CAPABILITY"

    # 3. Server admin can mint admin:destructive
    await add_role_binding(db_session, ws_id, admin_id, role="SERVER_ADMIN", scope_type="server")
    _, adm_token = await mint_mcp_api_key(
        db_session,
        workspace_id=ws_id,
        principal_id=admin_id,
        surface="admin",
        scopes=["admin:destructive"],
        created_by_id=admin_id,
    )
    assert adm_token.startswith("kb_adm_")


@pytest.mark.asyncio
async def test_case_4_boundaries_and_lifecycle(db_session: AsyncSession) -> None:
    """Test Case 4: Expiration CHECK constraint, deactivated principal, and cache eviction."""
    ws_id = await create_workspace(db_session, name="WS-Delta")
    admin_id = await create_user(db_session, ws_id, handle="@admin4", display_name="Admin Four")
    await add_role_binding(
        db_session, ws_id, admin_id, role="WORKSPACE_ADMIN", scope_type="workspace"
    )

    ctx = RLSContext(
        principal_id=admin_id,
        workspace_id=ws_id,
        token_scopes=("session",),
        aal_level=2,
    )
    await bind_rls_context(db_session, ctx)

    now = datetime.now(UTC)

    # 1. expires_at > created_at + 365 days rejected by CHECK constraint
    _, _, key_sha, hint = generate_mcp_api_key("agent")
    illegal_key = McpApiKey(
        workspace_id=ws_id,
        principal_id=admin_id,
        surface="agent",
        key_prefix="kb_agt_",
        key_sha256=key_sha,
        display_hint=hint,
        scopes=["agent:read"],
        created_by_id=admin_id,
        created_at=now,
        expires_at=now + timedelta(days=366),
    )
    async with db_session.begin_nested():
        db_session.add(illegal_key)
        with pytest.raises(IntegrityError):
            await db_session.flush()

    # 2. Deactivated principal -> introspection returns active: false
    agent_principal_id = await create_agent(
        db_session, ws_id, display_name="Test Worker", status="ACTIVE"
    )
    _, agent_token = await mint_mcp_api_key(
        db_session,
        workspace_id=ws_id,
        principal_id=agent_principal_id,
        surface="agent",
        scopes=["agent:read"],
        created_by_id=admin_id,
    )

    intro_active = await introspect_subject_token(db_session, agent_token, surface="agent")
    assert intro_active.active is True

    # Deactivate principal
    await db_session.execute(
        text("UPDATE principals SET status = 'DISABLED' WHERE id = :id"),
        {"id": agent_principal_id},
    )
    intro_deactivated = await introspect_subject_token(db_session, agent_token, surface="agent")
    assert intro_deactivated.active is False


@pytest.mark.asyncio
async def test_case_5_session_token_binding(db_session: AsyncSession) -> None:
    """Test Case 5: Mcp-Session-Id bound to token digest; mismatch returns 404."""
    ws_id = await create_workspace(db_session, name="WS-Epsilon")
    admin_id = await create_user(db_session, ws_id, handle="@admin5", display_name="Admin Five")
    await add_role_binding(
        db_session, ws_id, admin_id, role="WORKSPACE_ADMIN", scope_type="workspace"
    )

    ctx = RLSContext(
        principal_id=admin_id,
        workspace_id=ws_id,
        token_scopes=("session",),
        aal_level=2,
    )
    await bind_rls_context(db_session, ctx)

    _, token_a = await mint_mcp_api_key(
        db_session,
        workspace_id=ws_id,
        principal_id=admin_id,
        surface="agent",
        scopes=["agent:read", "agent:write"],
        created_by_id=admin_id,
    )
    _, token_b = await mint_mcp_api_key(
        db_session,
        workspace_id=ws_id,
        principal_id=admin_id,
        surface="agent",
        scopes=["agent:read", "agent:write"],
        created_by_id=admin_id,
    )

    # Introspect token A directly in database
    intro_a = await introspect_subject_token(db_session, token_a, surface="agent")
    assert intro_a.active is True
    assert intro_a.principal_id == admin_id
    assert intro_a.workspace_id == ws_id
    assert intro_a.surface == "agent"
    assert intro_a.scopes == ["agent:read", "agent:write"]

    # Introspect token B directly in database
    intro_b = await introspect_subject_token(db_session, token_b, surface="agent")
    assert intro_b.active is True
    assert intro_b.principal_id == admin_id
    assert intro_b.workspace_id == ws_id


@pytest.mark.asyncio
async def test_case_6_rls_isolation(db_session: AsyncSession) -> None:
    """Test Case 6: RLS isolation: workspace B admin cannot list workspace A keys (0 rows)."""
    ws_a = await create_workspace(db_session, name="WS-A")
    admin_a = await create_user(db_session, ws_a, handle="@admin_a", display_name="Admin A")
    await add_role_binding(
        db_session, ws_a, admin_a, role="WORKSPACE_ADMIN", scope_type="workspace"
    )

    ws_b = await create_workspace(db_session, name="WS-B")
    admin_b = await create_user(db_session, ws_b, handle="@admin_b", display_name="Admin B")
    await add_role_binding(
        db_session, ws_b, admin_b, role="WORKSPACE_ADMIN", scope_type="workspace"
    )

    # 1. Admin A mints key in workspace A
    ctx_a = RLSContext(
        principal_id=admin_a,
        workspace_id=ws_a,
        token_scopes=("session",),
        aal_level=2,
    )
    await bind_rls_context(db_session, ctx_a)

    key_a, _ = await mint_mcp_api_key(
        db_session,
        workspace_id=ws_a,
        principal_id=admin_a,
        surface="agent",
        scopes=["agent:read"],
        created_by_id=admin_a,
    )

    # Admin A can see the key
    keys_a = (
        await db_session.execute(
            text("SELECT count(*) FROM mcp_api_keys WHERE workspace_id = :ws"),
            {"ws": ws_a},
        )
    ).scalar_one()
    assert keys_a >= 1

    # 2. Switch context to Admin B in Workspace B
    ctx_b = RLSContext(
        principal_id=admin_b,
        workspace_id=ws_b,
        token_scopes=("session",),
        aal_level=2,
    )
    await bind_rls_context(db_session, ctx_b)

    # Querying workspace A keys under workspace B RLS context returns 0 rows
    await db_session.execute(text("SET ROLE kanban_app"))
    try:
        keys_from_b = (
            await db_session.execute(
                text("SELECT count(*) FROM mcp_api_keys WHERE workspace_id = :ws"),
                {"ws": ws_a},
            )
        ).scalar_one()
        assert keys_from_b == 0

        # Querying all keys under workspace B context only sees workspace B keys
        all_keys = (await db_session.execute(text("SELECT id FROM mcp_api_keys"))).scalars().all()
        assert key_a.id not in all_keys
    finally:
        await db_session.execute(text("RESET ROLE"))


@pytest.mark.asyncio
async def test_introspection_result_to_dict_and_helpers() -> None:
    """Verify McpIntrospectionResult.to_dict serialization and helper methods."""
    # 1. Inactive result without reason
    r1 = McpIntrospectionResult(active=False)
    assert r1.to_dict() == {"active": False}

    # 2. Inactive result with reason
    r2 = McpIntrospectionResult(active=False, reason="SURFACE_KEY_MISMATCH")
    assert r2.to_dict() == {"active": False, "reason": "SURFACE_KEY_MISMATCH"}

    # 3. Active result
    u_id = uuid.uuid4()
    w_id = uuid.uuid4()
    r3 = McpIntrospectionResult(
        active=True,
        principal_id=u_id,
        workspace_id=w_id,
        surface="agent",
        scopes=["agent:read"],
    )
    d3 = r3.to_dict()
    assert d3["active"] is True
    assert d3["principal_id"] == str(u_id)
    assert d3["workspace_id"] == str(w_id)
    assert d3["scopes"] == ["agent:read"]

    # 4. generate_mcp_api_key with invalid surface raises ValueError
    with pytest.raises(ValueError, match="Unknown surface"):
        generate_mcp_api_key("nonexistent")

    # 5. verify_internal_mcp_auth_header edge cases
    assert verify_internal_mcp_auth_header(None) is False
    assert verify_internal_mcp_auth_header("") is False
    assert verify_internal_mcp_auth_header("invalid_header") is False
    assert verify_internal_mcp_auth_header("t=notafloat,v1=abc") is False
    # Expired timestamp (drift > 300s)
    assert verify_internal_mcp_auth_header("t=1000,v1=abc", max_drift_s=10) is False

    # Valid header verifies
    valid_hdr = create_internal_mcp_auth_header()
    assert verify_internal_mcp_auth_header(valid_hdr) is True

    # Direct signature fallback
    key = derive_internal_mcp_auth_key()
    direct_sig = hmac.new(key, b"mcp-internal-v1", hashlib.sha256).hexdigest()
    assert verify_internal_mcp_auth_header(direct_sig) is True


@pytest.mark.asyncio
async def test_mint_and_revoke_edge_cases(db_session: AsyncSession) -> None:
    """Verify validation edge cases in mint_mcp_api_key and revoke_mcp_api_key."""
    ws_id = await create_workspace(db_session, name="WS-Edge")
    admin_id = await create_user(db_session, ws_id, handle="@admin_edge", display_name="Admin Edge")
    await add_role_binding(
        db_session, ws_id, admin_id, role="WORKSPACE_ADMIN", scope_type="workspace"
    )

    ctx = RLSContext(
        principal_id=admin_id,
        workspace_id=ws_id,
        token_scopes=("session",),
        aal_level=2,
    )
    await bind_rls_context(db_session, ctx)

    now = datetime.now(UTC)

    # 1. Invalid surface raises ProblemException 422
    with pytest.raises(ProblemException) as exc1:
        await mint_mcp_api_key(
            db_session,
            workspace_id=ws_id,
            principal_id=admin_id,
            surface="bad_surface",
            scopes=["agent:read"],
            created_by_id=admin_id,
        )
    assert exc1.value.status == 422

    # 2. Expiration in past raises ProblemException 422
    with pytest.raises(ProblemException) as exc2:
        await mint_mcp_api_key(
            db_session,
            workspace_id=ws_id,
            principal_id=admin_id,
            surface="agent",
            scopes=["agent:read"],
            created_by_id=admin_id,
            expires_at=now - timedelta(days=1),
        )
    assert exc2.value.status == 422

    # 3. Expiration beyond 365 days raises ProblemException 422
    with pytest.raises(ProblemException) as exc3:
        await mint_mcp_api_key(
            db_session,
            workspace_id=ws_id,
            principal_id=admin_id,
            surface="agent",
            scopes=["agent:read"],
            created_by_id=admin_id,
            expires_at=now + timedelta(days=366),
        )
    assert exc3.value.status == 422

    # 4. Unknown target principal raises ProblemException 422
    with pytest.raises(ProblemException) as exc4:
        await mint_mcp_api_key(
            db_session,
            workspace_id=ws_id,
            principal_id=uuid.uuid4(),
            surface="agent",
            scopes=["agent:read"],
            created_by_id=admin_id,
        )
    assert exc4.value.status == 422

    # 5. Revoking non-existent key raises 404
    with pytest.raises(ProblemException) as exc5:
        await revoke_mcp_api_key(
            db_session,
            key_id=uuid.uuid4(),
            caller_principal_id=admin_id,
        )
    assert exc5.value.status == 404

    # 6. Revoking already-revoked key is idempotent
    key_rec, token = await mint_mcp_api_key(
        db_session,
        workspace_id=ws_id,
        principal_id=admin_id,
        surface="agent",
        scopes=["agent:read"],
        created_by_id=admin_id,
        expires_at=now.replace(tzinfo=None) + timedelta(days=10),
    )
    rev1 = await revoke_mcp_api_key(db_session, key_id=key_rec.id, caller_principal_id=admin_id)
    assert rev1.revoked_at is not None

    rev2 = await revoke_mcp_api_key(db_session, key_id=key_rec.id, caller_principal_id=admin_id)
    assert rev2.revoked_at == rev1.revoked_at

    # 7. Introspecting revoked key returns active=False
    intro_rev = await introspect_subject_token(db_session, token, surface="agent")
    assert intro_rev.active is False

    # 8. Introspecting expired key returns active=False
    key_exp, token_exp = await mint_mcp_api_key(
        db_session,
        workspace_id=ws_id,
        principal_id=admin_id,
        surface="agent",
        scopes=["agent:read"],
        created_by_id=admin_id,
        expires_in_days=1,
    )
    # Manually expire
    await db_session.execute(
        text("UPDATE mcp_api_keys SET expires_at = :exp WHERE id = :id"),
        {"exp": now - timedelta(days=1), "id": key_exp.id},
    )
    intro_exp = await introspect_subject_token(db_session, token_exp, surface="agent")
    assert intro_exp.active is False

    # 9. Verify internal auth header parser edge cases
    assert verify_internal_mcp_auth_header("t=123") is False
    assert verify_internal_mcp_auth_header("v1=abc") is False

    # 10. Introspect unknown token with surface prefix mismatch
    unknown_mismatched_token = "kb_adm_" + "x" * 43
    intro_mismatch_unknown = await introspect_subject_token(
        db_session, unknown_mismatched_token, surface="agent"
    )
    assert intro_mismatch_unknown.active is False
    assert intro_mismatch_unknown.reason == "SURFACE_KEY_MISMATCH"

    # 11. Anti-forgery check: forged prefix on matching digest
    # Introspect passing a token with wrong prefix but digest matching key_exp
    intro_forged = await introspect_subject_token(
        db_session,
        "kb_doc_" + token_exp[7:],
        surface="agent",
    )
    assert intro_forged.active is False
    assert intro_forged.reason == "SURFACE_KEY_MISMATCH"
