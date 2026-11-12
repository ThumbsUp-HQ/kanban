"""Unit tests for capability bitmask evaluation, OBO delegation, and 404/403 security (S3.2)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.security.permissions import (
    Capability,
    capabilities_to_names,
    evaluate_capabilities,
    parse_token_scope_mask,
    require_capability,
)
from kanban.tests.security.helpers import (
    add_acl_entry,
    add_group_member,
    add_role_binding,
    create_agent,
    create_group,
    create_project,
    create_registered_object,
    create_user,
    create_workspace,
    rebuild_era,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def test_token_scope_parsing_and_names() -> None:
    """Test token scope bitmask parsing and capability name conversions."""
    # Empty scopes fail closed
    assert parse_token_scope_mask(()) == Capability.NONE
    assert parse_token_scope_mask(("unknown:scope", "bad:scope")) == Capability.NONE

    # Browser session scope
    assert parse_token_scope_mask(("session",)) == Capability.ALL

    # Fine-grained scopes
    assert parse_token_scope_mask(("read",)) == Capability.VIEW
    assert parse_token_scope_mask(("comment",)) == Capability.VIEW | Capability.COMMENT
    assert parse_token_scope_mask(("write",)) == (
        Capability.VIEW
        | Capability.COMMENT
        | Capability.EDIT
        | Capability.TRANSITION
        | Capability.LINK
    )
    assert parse_token_scope_mask(("share",)) == Capability.VIEW | Capability.SHARE
    assert parse_token_scope_mask(("admin:write",)) == Capability(
        Capability.ALL & ~Capability.DELETE
    )
    assert parse_token_scope_mask(("admin:destructive",)) == Capability.ALL

    # Multi-scope union
    combo = parse_token_scope_mask(("read", "share"))
    assert combo == Capability.VIEW | Capability.SHARE

    # Name mapping
    names = capabilities_to_names(Capability.VIEW | Capability.EDIT)
    assert names == ["VIEW", "EDIT"]

    all_names = capabilities_to_names(Capability.ALL)
    assert all_names == [
        "VIEW",
        "COMMENT",
        "EDIT",
        "TRANSITION",
        "LINK",
        "SHARE",
        "ADMIN",
        "DELETE",
    ]


@pytest.mark.asyncio
async def test_case_1_rbac_and_direct_acl_union(db_session: AsyncSession) -> None:
    """Test Case 1: Positive RBAC + ACL union.

    User with project VIEWER (VIEW | COMMENT = 3) plus direct EDIT (4) ACL on issue
    evaluates to VIEW | COMMENT | EDIT (7).
    """
    ws_id = await create_workspace(db_session, name="WS-Case1")
    user_id = await create_user(db_session, ws_id, handle="@alice", display_name="Alice")
    proj_id = await create_project(db_session, ws_id, identifier="KAN", name="Kanban")
    issue_id = await create_registered_object(
        db_session, ws_id, kind="issue", key="KAN-1", title="Issue 1", project_id=proj_id
    )

    # Bind Alice as VIEWER on project KAN (VIEW | COMMENT = 3)
    await add_role_binding(
        db_session, ws_id, user_id, role="VIEWER", scope_type="project", project_id=proj_id
    )

    # Add direct EDIT ACL (4) on issue KAN-1
    await add_acl_entry(
        db_session, ws_id, issue_id, user_id, effect="ALLOW", capability_mask=Capability.EDIT
    )

    await rebuild_era(db_session, ws_id)

    ctx = PrincipalContext(
        principal_id=user_id,
        workspace_id=ws_id,
        token_scopes=("session",),
    )

    caps = await evaluate_capabilities(db_session, ctx, issue_id)
    expected = Capability.VIEW | Capability.COMMENT | Capability.EDIT
    assert caps == expected
    assert capabilities_to_names(caps) == ["VIEW", "COMMENT", "EDIT"]


@pytest.mark.asyncio
async def test_case_2_explicit_deny_precedence_and_group_closure(db_session: AsyncSession) -> None:
    """Test Case 2: Security (explicit deny precedence and nested group inheritance).

    User in Core Backend (ALLOW VIEW | EDIT) AND Contractors (DENY EDIT) evaluates to VIEW only.
    SubContractors -> Contractors nested group inherits the DENY EDIT via closure.
    """
    ws_id = await create_workspace(db_session, name="WS-Case2")
    user_bob = await create_user(db_session, ws_id, handle="@bob", display_name="Bob")
    proj_id = await create_project(db_session, ws_id, identifier="CORE", name="Core Project")
    issue_id = await create_registered_object(
        db_session, ws_id, kind="issue", key="CORE-1", title="Core Issue", project_id=proj_id
    )

    g_core = await create_group(db_session, ws_id, "Core Backend")
    g_contractors = await create_group(db_session, ws_id, "Contractors")
    g_subcontractors = await create_group(db_session, ws_id, "SubContractors")

    # Enroll Bob into Core Backend and SubContractors
    await add_group_member(db_session, ws_id, g_core, user_bob)
    await add_group_member(db_session, ws_id, g_subcontractors, user_bob)

    # Nest SubContractors -> Contractors
    await add_group_member(db_session, ws_id, g_contractors, g_subcontractors)

    # Core Backend gets direct ALLOW VIEW | EDIT on issue
    await add_acl_entry(
        db_session,
        ws_id,
        issue_id,
        g_core,
        effect="ALLOW",
        capability_mask=Capability.VIEW | Capability.EDIT,
    )

    # Contractors group has explicit DENY EDIT on issue
    await add_acl_entry(
        db_session,
        ws_id,
        issue_id,
        g_contractors,
        effect="DENY",
        capability_mask=Capability.EDIT,
    )

    await rebuild_era(db_session, ws_id)

    ctx = PrincipalContext(
        principal_id=user_bob,
        workspace_id=ws_id,
        token_scopes=("session",),
    )

    caps = await evaluate_capabilities(db_session, ctx, issue_id)
    # Explicit DENY EDIT overrides ALLOW EDIT, leaving VIEW only
    assert Capability.EDIT not in caps
    assert Capability.VIEW in caps
    assert caps == Capability.VIEW


@pytest.mark.asyncio
async def test_case_3_obo_intersection_narrowing(db_session: AsyncSession) -> None:
    """Test Case 3: Security (OBO intersection User ∩ AgentGrant ∩ TokenScope).

    User holds VIEW | EDIT | DELETE on KAN-1.
    Agent holds VIEW | EDIT on project KAN.
    Token carries agent:read -> returns VIEW only.
    Token carries agent:write -> returns VIEW | EDIT (never DELETE).
    On confidential project SEC-1 where agent has access but user has NONE -> returns NONE.
    """
    ws_id = await create_workspace(db_session, name="WS-Case3")
    user_carol = await create_user(db_session, ws_id, handle="@carol", display_name="Carol")
    agent_id = await create_agent(
        db_session, ws_id, "Worker Agent (llm/fast)", principal_type="AGENT"
    )

    proj_kan = await create_project(db_session, ws_id, identifier="KAN", name="Kanban")
    issue_kan = await create_registered_object(
        db_session, ws_id, kind="issue", key="KAN-1", title="Open Issue", project_id=proj_kan
    )

    proj_sec = await create_project(db_session, ws_id, identifier="SEC", name="Confidential")
    issue_sec = await create_registered_object(
        db_session,
        ws_id,
        kind="issue",
        key="SEC-1",
        title="Confidential Issue",
        project_id=proj_sec,
    )

    # User holds VIEW | EDIT | DELETE (1 | 4 | 128 = 133) on KAN-1
    await add_acl_entry(
        db_session,
        ws_id,
        issue_kan,
        user_carol,
        effect="ALLOW",
        capability_mask=Capability.VIEW | Capability.EDIT | Capability.DELETE,
    )

    # Agent holds MEMBER (VIEW | COMMENT | EDIT | TRANSITION | LINK = 31) on project KAN
    await add_role_binding(
        db_session, ws_id, agent_id, role="MEMBER", scope_type="project", project_id=proj_kan
    )

    # Agent also holds broad MEMBER access on project SEC
    await add_role_binding(
        db_session, ws_id, agent_id, role="MEMBER", scope_type="project", project_id=proj_sec
    )

    # Notice Carol holds NO access on SEC project or SEC-1 issue
    await rebuild_era(db_session, ws_id)

    # 1. Narrow token: agent:read (VIEW)
    ctx_read = PrincipalContext(
        principal_id=user_carol,
        workspace_id=ws_id,
        token_scopes=("agent:read",),
        agent_principal_id=agent_id,
    )
    caps_read = await evaluate_capabilities(db_session, ctx_read, issue_kan)
    assert caps_read == Capability.VIEW

    # 2. Widened token: agent:write (VIEW | COMMENT | EDIT | TRANSITION | LINK)
    ctx_write = PrincipalContext(
        principal_id=user_carol,
        workspace_id=ws_id,
        token_scopes=("agent:write",),
        agent_principal_id=agent_id,
    )
    caps_write = await evaluate_capabilities(db_session, ctx_write, issue_kan)
    # Intersection of User (VIEW|EDIT|DELETE) & Agent (MEMBER) & Token (agent:write)
    # = (133 & 31 & 31) = 1 | 4 = VIEW | EDIT. Notice DELETE is not included!
    assert caps_write == Capability.VIEW | Capability.EDIT
    assert Capability.DELETE not in caps_write

    # 3. Invoking OBO on SEC-1 where human has NONE -> returns NONE
    ctx_sec = PrincipalContext(
        principal_id=user_carol,
        workspace_id=ws_id,
        token_scopes=("agent:write",),
        agent_principal_id=agent_id,
    )
    caps_sec = await evaluate_capabilities(db_session, ctx_sec, issue_sec)
    assert caps_sec == Capability.NONE

    # require_capability raises 404 NOT_FOUND due to lack of VIEW
    with pytest.raises(ProblemException) as exc_info:
        await require_capability(db_session, ctx_sec, issue_sec, Capability.VIEW)
    assert exc_info.value.status == 404
    assert exc_info.value.code == "NOT_FOUND"


@pytest.mark.asyncio
async def test_case_4_disabled_principal_and_unknown_scope(db_session: AsyncSession) -> None:
    """Test Case 4: Security (disabled agent principal and unknown token scopes)."""
    ws_id = await create_workspace(db_session, name="WS-Case4")
    user_id = await create_user(db_session, ws_id, handle="@dave", display_name="Dave")
    disabled_agent = await create_agent(
        db_session, ws_id, "Disabled Agent", principal_type="AGENT", status="DISABLED"
    )
    active_agent = await create_agent(
        db_session, ws_id, "Active Agent", principal_type="AGENT", status="ACTIVE"
    )
    proj_id = await create_project(db_session, ws_id, identifier="DAVE", name="Dave Project")
    issue_id = await create_registered_object(
        db_session, ws_id, kind="issue", key="DAVE-1", title="Issue", project_id=proj_id
    )

    await add_acl_entry(
        db_session, ws_id, issue_id, user_id, effect="ALLOW", capability_mask=Capability.ALL
    )
    await add_acl_entry(
        db_session, ws_id, issue_id, disabled_agent, effect="ALLOW", capability_mask=Capability.ALL
    )
    await add_acl_entry(
        db_session, ws_id, issue_id, active_agent, effect="ALLOW", capability_mask=Capability.ALL
    )
    await rebuild_era(db_session, ws_id)

    # 1. OBO with DISABLED agent returns NONE
    ctx_disabled = PrincipalContext(
        principal_id=user_id,
        workspace_id=ws_id,
        token_scopes=("session",),
        agent_principal_id=disabled_agent,
    )
    assert await evaluate_capabilities(db_session, ctx_disabled, issue_id) == Capability.NONE

    # 2. Token scopes with unknown scope only returns NONE
    ctx_unknown = PrincipalContext(
        principal_id=user_id,
        workspace_id=ws_id,
        token_scopes=("unknown:scope",),
        agent_principal_id=active_agent,
    )
    assert await evaluate_capabilities(db_session, ctx_unknown, issue_id) == Capability.NONE

    # 3. Human user with DISABLED status returns NONE (covers line 112)
    disabled_user = await create_user(
        db_session, ws_id, handle="@disabled", display_name="Disabled User", status="DISABLED"
    )
    ctx_disabled_user = PrincipalContext(
        principal_id=disabled_user,
        workspace_id=ws_id,
        token_scopes=("session",),
    )
    assert await evaluate_capabilities(db_session, ctx_disabled_user, issue_id) == Capability.NONE

    # 4. Target object with no ERA rows for principal returns NONE (covers line 140)
    unrelated_object_id = uuid.uuid4()
    ctx_unrelated = PrincipalContext(
        principal_id=user_id,
        workspace_id=ws_id,
        token_scopes=("session",),
    )
    assert (
        await evaluate_capabilities(db_session, ctx_unrelated, unrelated_object_id)
        == Capability.NONE
    )


@pytest.mark.asyncio
async def test_case_7_404_vs_403_discipline(db_session: AsyncSession) -> None:
    """Test Case 7: Security (anti-enumeration 404 NOT_FOUND vs 403 INSUFFICIENT_CAPABILITY)."""
    ws_id = await create_workspace(db_session, name="WS-Case7")
    user_viewer = await create_user(db_session, ws_id, handle="@eve", display_name="Eve")
    user_stranger = await create_user(
        db_session, ws_id, handle="@stranger", display_name="Stranger"
    )
    proj_id = await create_project(db_session, ws_id, identifier="EVE", name="Eve Project")
    issue_id = await create_registered_object(
        db_session, ws_id, kind="issue", key="EVE-1", title="Eve Issue", project_id=proj_id
    )

    # Eve holds VIEW only on issue
    await add_acl_entry(
        db_session, ws_id, issue_id, user_viewer, effect="ALLOW", capability_mask=Capability.VIEW
    )
    await rebuild_era(db_session, ws_id)

    ctx_eve = PrincipalContext(
        principal_id=user_viewer, workspace_id=ws_id, token_scopes=("session",)
    )
    ctx_stranger = PrincipalContext(
        principal_id=user_stranger, workspace_id=ws_id, token_scopes=("session",)
    )

    # 1. Caller holds VIEW, requires EDIT -> raises 403 INSUFFICIENT_CAPABILITY
    with pytest.raises(ProblemException) as exc_403:
        await require_capability(db_session, ctx_eve, issue_id, Capability.EDIT)
    assert exc_403.value.status == 403
    assert exc_403.value.code == "INSUFFICIENT_CAPABILITY"

    # 2. Caller lacks VIEW, requires EDIT -> raises 404 NOT_FOUND (never 403!)
    with pytest.raises(ProblemException) as exc_404:
        await require_capability(db_session, ctx_stranger, issue_id, Capability.EDIT)
    assert exc_404.value.status == 404
    assert exc_404.value.code == "NOT_FOUND"

    # 3. Caller lacks VIEW, requires VIEW -> raises 404 NOT_FOUND
    with pytest.raises(ProblemException) as exc_404_view:
        await require_capability(db_session, ctx_stranger, issue_id, Capability.VIEW)
    assert exc_404_view.value.status == 404
    assert exc_404_view.value.code == "NOT_FOUND"

    # 4. Caller holds VIEW, requires VIEW -> returns effective capabilities without error
    caps = await require_capability(db_session, ctx_eve, issue_id, Capability.VIEW)
    assert caps == Capability.VIEW
