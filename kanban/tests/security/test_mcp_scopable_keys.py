# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Feature unit tests for hierarchical scopable MCP keys, narrowing, RLS & gates (KB-P4-14)."""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.exc import IntegrityError

from database.models.mcp_api_key import McpApiKey
from database.session import RLSContext, bind_rls_context
from kanban.api.problems import ProblemException
from kanban.security.mcp_keys import (
    evaluate_key_boundary,
    generate_mcp_api_key,
    introspect_subject_token,
    mint_mcp_api_key,
    revoke_mcp_api_key,
)
from kanban.settings import get_settings
from kanban.tests.security.helpers import (
    add_role_binding,
    create_agent,
    create_project,
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
async def test_case_1_positive_global_bot_key(db_session: AsyncSession) -> None:
    """Test Case 1: Global bot key across allowed workspaces and blocking out-of-scope."""
    ws_a = await create_workspace(db_session, name="WS-Alpha")
    ws_b = await create_workspace(db_session, name="WS-Beta")
    ws_c = await create_workspace(db_session, name="WS-Gamma")
    ws_secret = await create_workspace(db_session, name="WS-Secret")

    admin_id = await create_user(
        db_session, ws_a, handle="@serveradmin", display_name="Server Admin"
    )
    await add_role_binding(db_session, ws_a, admin_id, role="SERVER_ADMIN", scope_type="server")

    # Global service bot principal in ws_a
    bot_id = await create_agent(db_session, ws_a, display_name="meatloaf-bot")

    ctx = RLSContext(
        principal_id=admin_id,
        workspace_id=ws_a,
        token_scopes=("session",),
        aal_level=2,
    )
    await bind_rls_context(db_session, ctx)

    key_record, _plaintext = await mint_mcp_api_key(
        db_session,
        workspace_id=None,
        principal_id=bot_id,
        surface="agent",
        scopes=["agent:read", "agent:write"],
        scope_tier="global",
        owner_kind="service_bot",
        allowed_workspace_ids=[ws_a, ws_b, ws_c],
        created_by_id=admin_id,
        caller_aal_level=2,
    )

    assert key_record.scope_tier == "global"
    assert key_record.workspace_id is None
    assert key_record.allowed_workspace_ids == [ws_a, ws_b, ws_c]

    # Verify evaluate_key_boundary passes for allowed workspaces
    evaluate_key_boundary(key_record, target_workspace_id=ws_a)
    evaluate_key_boundary(key_record, target_workspace_id=ws_b)
    evaluate_key_boundary(key_record, target_workspace_id=ws_c)

    # Verify evaluate_key_boundary rejects out-of-scope workspace
    with pytest.raises(ProblemException) as exc_info:
        evaluate_key_boundary(key_record, target_workspace_id=ws_secret)
    assert exc_info.value.status == 403
    assert exc_info.value.code == "KEY_SCOPE_VIOLATION"


@pytest.mark.asyncio
async def test_case_2_positive_per_project_key(db_session: AsyncSession) -> None:
    """Test Case 2: Project-scoped key on KANBA vs sibling project in same workspace."""
    ws_id = await create_workspace(db_session, name="WS-Projects")
    prj_kanba = await create_project(db_session, ws_id, identifier="KANBA", name="Kanban Core")
    prj_other = await create_project(db_session, ws_id, identifier="OTHER", name="Other Service")
    ws_external = await create_workspace(db_session, name="WS-External")

    admin_id = await create_user(db_session, ws_id, handle="@wsadmin", display_name="WS Admin")
    await add_role_binding(
        db_session, ws_id, admin_id, role="WORKSPACE_ADMIN", scope_type="workspace"
    )

    bot_id = await create_agent(db_session, ws_id, display_name="kanba-project-bot")

    ctx = RLSContext(
        principal_id=admin_id,
        workspace_id=ws_id,
        token_scopes=("session",),
        aal_level=2,
    )
    await bind_rls_context(db_session, ctx)

    key_record, _plaintext = await mint_mcp_api_key(
        db_session,
        workspace_id=ws_id,
        principal_id=bot_id,
        surface="agent",
        scopes=["agent:read", "agent:write"],
        scope_tier="project",
        owner_kind="service_bot",
        project_id=prj_kanba,
        created_by_id=admin_id,
        caller_aal_level=2,
    )

    assert key_record.scope_tier == "project"
    assert key_record.project_id == prj_kanba

    # Target project KANBA in ws_id passes
    evaluate_key_boundary(key_record, target_workspace_id=ws_id, target_project_id=prj_kanba)

    # Target sibling project OTHER fails
    with pytest.raises(ProblemException) as exc_info:
        evaluate_key_boundary(key_record, target_workspace_id=ws_id, target_project_id=prj_other)
    assert exc_info.value.status == 403
    assert exc_info.value.code == "KEY_SCOPE_VIOLATION"

    # Target external workspace fails
    with pytest.raises(ProblemException) as exc_info2:
        evaluate_key_boundary(
            key_record, target_workspace_id=ws_external, target_project_id=prj_kanba
        )
    assert exc_info2.value.status == 403
    assert exc_info2.value.code == "KEY_SCOPE_VIOLATION"


@pytest.mark.asyncio
async def test_case_3_personal_key_lifecycle_and_tool_narrowing(
    db_session: AsyncSession,
) -> None:
    """Test Case 3: Personal user self-service key with revocation & tool narrowing."""
    ws_id = await create_workspace(db_session, name="WS-SelfService")
    user_id = await create_user(db_session, ws_id, handle="@devuser", display_name="Dev User")
    await add_role_binding(
        db_session, ws_id, user_id, role="WORKSPACE_MEMBER", scope_type="workspace"
    )

    ctx = RLSContext(
        principal_id=user_id,
        workspace_id=ws_id,
        token_scopes=("session",),
        aal_level=1,
    )
    await bind_rls_context(db_session, ctx)

    key_record, plaintext = await mint_mcp_api_key(
        db_session,
        workspace_id=ws_id,
        principal_id=user_id,
        surface="agent",
        scopes=["agent:read", "agent:write"],
        scope_tier="workspace",
        owner_kind="personal_user",
        disabled_tools=["transition_ticket", "complete_work"],
        created_by_id=user_id,
        caller_aal_level=1,
    )

    assert key_record.scope_tier == "workspace"
    assert key_record.owner_kind == "personal_user"
    assert key_record.disabled_tools == ["transition_ticket", "complete_work"]

    # Allowed tool passes
    evaluate_key_boundary(key_record, tool_name="search_tickets")

    # Disabled tool fails with INSUFFICIENT_SCOPE
    with pytest.raises(ProblemException) as exc_info:
        evaluate_key_boundary(key_record, tool_name="complete_work")
    assert exc_info.value.status == 403
    assert exc_info.value.code == "INSUFFICIENT_SCOPE"

    # Introspect returns active key with disabled_tools
    intro = await introspect_subject_token(db_session, plaintext, surface="agent")
    assert intro is not None
    assert intro.active is True
    assert intro.disabled_tools == ["transition_ticket", "complete_work"]

    # Revoke key
    await revoke_mcp_api_key(db_session, key_id=key_record.id, caller_principal_id=user_id)

    # Introspect now returns inactive
    revoked_intro = await introspect_subject_token(db_session, plaintext, surface="agent")
    assert revoked_intro is not None
    assert revoked_intro.active is False


@pytest.mark.asyncio
async def test_case_4_privilege_escalation_blocked(db_session: AsyncSession) -> None:
    """Test Case 4: Privilege escalation blocked (AAL1 user attempting admin key or global tier)."""
    ws_id = await create_workspace(db_session, name="WS-Security")
    user_id = await create_user(db_session, ws_id, handle="@regular", display_name="Regular User")
    await add_role_binding(
        db_session, ws_id, user_id, role="WORKSPACE_MEMBER", scope_type="workspace"
    )

    ctx = RLSContext(
        principal_id=user_id,
        workspace_id=ws_id,
        token_scopes=("session",),
        aal_level=1,
    )
    await bind_rls_context(db_session, ctx)

    # 1. Non-admin attempting to mint global key -> 403
    with pytest.raises(ProblemException) as exc1:
        await mint_mcp_api_key(
            db_session,
            workspace_id=None,
            principal_id=user_id,
            surface="agent",
            scopes=["agent:read"],
            scope_tier="global",
            owner_kind="service_bot",
            created_by_id=user_id,
            caller_aal_level=1,
        )
    assert exc1.value.status == 403

    # 2. Member attempting to mint workspace tier bot key -> 403
    bot_id = await create_agent(db_session, ws_id, display_name="ws-bot")
    with pytest.raises(ProblemException) as exc2:
        await mint_mcp_api_key(
            db_session,
            workspace_id=ws_id,
            principal_id=bot_id,
            surface="agent",
            scopes=["agent:read"],
            scope_tier="workspace",
            owner_kind="service_bot",
            created_by_id=user_id,
            caller_aal_level=1,
        )
    assert exc2.value.status == 403

    # 3. Caller with AAL1 attempting to mint service_bot key -> 403 AAL2 Required
    admin_id = await create_user(db_session, ws_id, handle="@adminaal1", display_name="Admin AAL1")
    await add_role_binding(
        db_session, ws_id, admin_id, role="WORKSPACE_ADMIN", scope_type="workspace"
    )
    with pytest.raises(ProblemException) as exc3:
        await mint_mcp_api_key(
            db_session,
            workspace_id=ws_id,
            principal_id=bot_id,
            surface="agent",
            scopes=["agent:read"],
            scope_tier="workspace",
            owner_kind="service_bot",
            created_by_id=admin_id,
            caller_aal_level=1,
        )
    assert exc3.value.status == 403
    assert exc3.value.detail is not None
    assert "AAL2" in exc3.value.detail


@pytest.mark.asyncio
async def test_case_5_cidr_pin_and_shape_check_constraints(db_session: AsyncSession) -> None:
    """Test Case 5: CIDR Pinning and database tier shape check constraints (23514)."""
    ws_id = await create_workspace(db_session, name="WS-CIDR")
    user_id = await create_user(db_session, ws_id, handle="@cidruser", display_name="CIDR User")
    await add_role_binding(
        db_session, ws_id, user_id, role="WORKSPACE_MEMBER", scope_type="workspace"
    )

    ctx = RLSContext(
        principal_id=user_id,
        workspace_id=ws_id,
        token_scopes=("session",),
        aal_level=1,
    )
    await bind_rls_context(db_session, ctx)

    key_record, _ = await mint_mcp_api_key(
        db_session,
        workspace_id=ws_id,
        principal_id=user_id,
        surface="agent",
        scopes=["agent:read"],
        scope_tier="workspace",
        owner_kind="personal_user",
        allowed_cidrs=["192.168.1.0/24"],
        created_by_id=user_id,
        caller_aal_level=1,
    )

    # 1. CIDR evaluation: allowed IP passes
    evaluate_key_boundary(key_record, client_ip="192.168.1.100")

    # 2. CIDR evaluation: disallowed IP fails
    with pytest.raises(ProblemException) as exc_info:
        evaluate_key_boundary(key_record, client_ip="10.0.0.1")
    assert exc_info.value.status == 403
    assert exc_info.value.code == "KEY_CIDR_DENIED"

    # 3. Database shape check constraint: mcp_keys_tier_shape_chk
    # Global tier with non-null workspace_id violates CHECK constraint
    _, prefix, key_sha256, hint = generate_mcp_api_key("agent")
    invalid_global = McpApiKey(
        workspace_id=ws_id,  # Invalid: global MUST have workspace_id NULL
        principal_id=user_id,
        surface="agent",
        key_prefix=prefix,
        key_sha256=key_sha256,
        display_hint=hint,
        scopes=["agent:read"],
        scope_tier="global",
        owner_kind="service_bot",
        created_by_id=user_id,
    )
    async with db_session.begin_nested():
        db_session.add(invalid_global)
        with pytest.raises(IntegrityError) as exc_db1:
            await db_session.flush()
    assert "mcp_keys_tier_shape_chk" in str(exc_db1.value)

    # Project tier with NULL project_id violates CHECK constraint
    invalid_project = McpApiKey(
        workspace_id=ws_id,
        principal_id=user_id,
        surface="agent",
        key_prefix=prefix,
        key_sha256=key_sha256,
        display_hint=hint,
        scopes=["agent:read"],
        scope_tier="project",
        owner_kind="service_bot",
        project_id=None,  # Invalid: project tier MUST have project_id NOT NULL
        created_by_id=user_id,
    )
    async with db_session.begin_nested():
        db_session.add(invalid_project)
        with pytest.raises(IntegrityError) as exc_db2:
            await db_session.flush()
    assert "mcp_keys_tier_shape_chk" in str(exc_db2.value)


@pytest.mark.asyncio
async def test_case_6_unlimited_key_gate(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test Case 6: Unlimited key gate with friction confirmation and settings enforcement."""
    ws_id = await create_workspace(db_session, name="WS-Unlimited")
    user_id = await create_user(db_session, ws_id, handle="@unluser", display_name="Unlimited User")
    await add_role_binding(
        db_session, ws_id, user_id, role="WORKSPACE_MEMBER", scope_type="workspace"
    )

    ctx = RLSContext(
        principal_id=user_id,
        workspace_id=ws_id,
        token_scopes=("session",),
        aal_level=1,
    )
    await bind_rls_context(db_session, ctx)

    # 1. Unlimited requested without confirmation -> 422 UNLIMITED_CONFIRMATION_REQUIRED
    with pytest.raises(ProblemException) as exc1:
        await mint_mcp_api_key(
            db_session,
            workspace_id=ws_id,
            principal_id=user_id,
            surface="agent",
            scopes=["agent:read"],
            scope_tier="workspace",
            owner_kind="personal_user",
            unlimited=True,
            confirm_unlimited=False,
            created_by_id=user_id,
            caller_aal_level=1,
        )
    assert exc1.value.status == 422
    assert exc1.value.code == "UNLIMITED_CONFIRMATION_REQUIRED"

    # 2. Unlimited with confirmation when system forbids unlimited keys -> 422
    settings = get_settings()
    monkeypatch.setattr(settings, "disable_unlimited_mcp_keys", True)

    with pytest.raises(ProblemException) as exc2:
        await mint_mcp_api_key(
            db_session,
            workspace_id=ws_id,
            principal_id=user_id,
            surface="agent",
            scopes=["agent:read"],
            scope_tier="workspace",
            owner_kind="personal_user",
            unlimited=True,
            confirm_unlimited=True,
            created_by_id=user_id,
            caller_aal_level=1,
        )
    assert exc2.value.status == 422
    assert exc2.value.code == "UNLIMITED_KEY_FORBIDDEN"

    # 3. Unlimited with confirmation when system allows unlimited keys -> Success
    monkeypatch.setattr(settings, "disable_unlimited_mcp_keys", False)

    key_record, plaintext = await mint_mcp_api_key(
        db_session,
        workspace_id=ws_id,
        principal_id=user_id,
        surface="agent",
        scopes=["agent:read"],
        scope_tier="workspace",
        owner_kind="personal_user",
        unlimited=True,
        confirm_unlimited=True,
        created_by_id=user_id,
        caller_aal_level=1,
    )
    assert key_record.expires_at is None

    # Introspect also reflects expires_at is None
    intro = await introspect_subject_token(db_session, plaintext, surface="agent")
    assert intro is not None
    assert intro.active is True
    assert intro.expires_at is None
