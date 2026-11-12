# ruff: noqa: PLR0915
"""Unit tests for anti-enumeration AccessManifest serializer and visibility boundaries (S3.4)."""

from __future__ import annotations

import json
import re
import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import ObjectKind, Principal, ResourceAclEntry, User, View, ViewLayout
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.security.access_manifest import (
    _collect_deny_overrides,
    _create_manifest_agent,
    _create_manifest_user,
    _is_out_of_boundary,
    _ManifestContext,
    build_access_manifest,
)
from kanban.security.permissions import Capability
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


@pytest.mark.asyncio
async def test_case_5_positive_access_manifest(db_session: AsyncSession) -> None:
    """Test Case 5: Positive access_manifest matches S3.4 wireframe structure.

    Project KAN with:
    - 2 direct users: Adam (@adam, Project Owner), Maya (@maya, Direct Share Edit)
    - 2 groups: Core Backend (LDAP, 11 members, Project Role),
      SecOps (OIDC, 4 members, Direct Share)
    - 1 service AGENT: Local Sparkle (ollama/qwen2.5-coder)
    - 1 DENY group: Contractors Group (Explicit DENY)
    Verifies pill_label ("Project + 2"), member counts, and deny overrides.
    """
    ws_id = await create_workspace(db_session, name="Engineering")

    # 1. Users
    adam_id = await create_user(db_session, ws_id, handle="@adam", display_name="Adam Outler")
    maya_id = await create_user(db_session, ws_id, handle="@maya", display_name="Maya Lin")

    # Project KAN created by Adam
    proj_id = await create_project(
        db_session, ws_id, identifier="KAN", name="Platform Core", created_by_id=adam_id
    )

    issue_id = await create_registered_object(
        db_session,
        ws_id,
        kind="issue",
        key="KAN-142",
        title="Access Manifest Task",
        project_id=proj_id,
        created_by_id=adam_id,
    )

    # 2. Groups
    g_backend = await create_group(
        db_session, ws_id, "Core Backend", external_source="LDAP", external_id="cn=backend,dc=corp"
    )
    g_secops = await create_group(
        db_session,
        ws_id,
        "SecOps Reviewers",
        external_source="OIDC",
        external_id="group-secops-oidc",
    )
    g_contractors = await create_group(db_session, ws_id, "Contractors Group")

    # Enroll 11 members into Core Backend
    for i in range(11):
        u_m = await create_user(
            db_session, ws_id, handle=f"@backend_{i}", display_name=f"Backend Eng {i}"
        )
        await add_group_member(db_session, ws_id, g_backend, u_m)

    # Enroll 4 members into SecOps
    for i in range(4):
        u_s = await create_user(
            db_session, ws_id, handle=f"@secops_{i}", display_name=f"SecOps Eng {i}"
        )
        await add_group_member(db_session, ws_id, g_secops, u_s)

    # 3. Agents
    agent_id = await create_agent(
        db_session, ws_id, "Local Sparkle (ollama/qwen2.5-coder)", principal_type="AGENT"
    )

    # Bind Adam as PROJECT_ADMIN on project KAN
    await add_role_binding(
        db_session, ws_id, adam_id, role="PROJECT_ADMIN", scope_type="project", project_id=proj_id
    )

    # Bind Core Backend as MEMBER on project KAN
    await add_role_binding(
        db_session, ws_id, g_backend, role="MEMBER", scope_type="project", project_id=proj_id
    )

    # Bind Agent as VIEWER on project KAN
    await add_role_binding(
        db_session, ws_id, agent_id, role="VIEWER", scope_type="project", project_id=proj_id
    )

    # Direct ALLOW ACLs on issue KAN-142:
    # Maya -> EDIT (Direct Share)
    await add_acl_entry(
        db_session, ws_id, issue_id, maya_id, effect="ALLOW", capability_mask=Capability.EDIT
    )
    # SecOps -> COMMENT (Direct Share)
    await add_acl_entry(
        db_session, ws_id, issue_id, g_secops, effect="ALLOW", capability_mask=Capability.COMMENT
    )

    # Direct DENY on issue KAN-142:
    # Contractors Group -> DENY EDIT
    await add_acl_entry(
        db_session, ws_id, issue_id, g_contractors, effect="DENY", capability_mask=Capability.EDIT
    )

    await rebuild_era(db_session, ws_id)

    caller = PrincipalContext(principal_id=adam_id, workspace_id=ws_id, token_scopes=("session",))
    manifest = await build_access_manifest(db_session, caller, issue_id)

    # 4. Assertions
    # Two direct shares (Maya + SecOps) -> "Project + 2"
    assert manifest.explicit_grant_count == 2
    assert manifest.pill_label == "Project + 2"

    assert manifest.inherited_scope.kind == "project"
    assert manifest.inherited_scope.project_key == "KAN"
    assert manifest.inherited_scope.workspace_name == "Engineering"

    # Verify Adam and Maya user records
    user_handles = {u.handle for u in manifest.users}
    assert "@adam" in user_handles
    assert "@maya" in user_handles

    adam_entry = next(u for u in manifest.users if u.handle == "@adam")
    assert adam_entry.grant_source == "project_owner"
    assert "ADMIN" in adam_entry.capabilities

    maya_entry = next(u for u in manifest.users if u.handle == "@maya")
    assert maya_entry.grant_source == "direct_share"
    assert "EDIT" in maya_entry.capabilities

    # Groups: Core Backend and SecOps Reviewers
    group_names = {g.name for g in manifest.groups}
    assert "Core Backend" in group_names
    assert "SecOps Reviewers" in group_names

    backend_g = next(g for g in manifest.groups if g.name == "Core Backend")
    assert backend_g.member_count == 11
    assert backend_g.external_source == "LDAP"
    assert backend_g.grant_source == "project_role"

    secops_g = next(g for g in manifest.groups if g.name == "SecOps Reviewers")
    assert secops_g.member_count == 4
    assert secops_g.external_source == "OIDC"
    assert secops_g.grant_source == "direct_share"

    # Agents: Local Sparkle
    assert len(manifest.agents) == 1
    ag = manifest.agents[0]
    assert ag.display_name == "Local Sparkle (ollama/qwen2.5-coder)"
    assert ag.provider_badge == "ollama/qwen2.5-coder"
    assert ag.scope_summary == "Project Scoped"
    assert "VIEW" in ag.capabilities

    # Deny Overrides: Contractors Group
    assert len(manifest.deny_overrides) == 1
    deny = manifest.deny_overrides[0]
    assert deny.display_name == "Contractors Group"
    assert deny.principal_type == "GROUP"
    assert deny.redacted is False
    assert "EDIT" in deny.denied_capabilities

    # Zero redacted entries within same workspace
    assert manifest.redacted_count == 0
    assert manifest.redacted_entries == []


@pytest.mark.asyncio
async def test_case_6_anti_enumeration_redaction(db_session: AsyncSession) -> None:
    """Test Case 6: Security (out-of-boundary collaborator redaction without metadata leakage).

    Attach an out-of-boundary collaborator (external_user email secret@partner.example,
    handle @secret_ext, LDAP DN CN=Secret,OU=Partner,DC=corp) to KAN-1.
    Serialized JSON must contain:
    - redacted_count >= 1
    - {"redacted": true, "label": "1 External Collaborator"}
    - ZERO occurrences of secret@partner.example, secret_ext, CN=Secret, or external UUID.
    In-boundary LDAP group must also omit raw external_id.
    """
    ws_main = await create_workspace(db_session, name="Main Org")

    # In-boundary caller
    caller_id = await create_user(
        db_session, ws_main, handle="@host_user", display_name="Host User"
    )
    proj_id = await create_project(
        db_session, ws_main, identifier="KAN", name="Kanban", created_by_id=caller_id
    )
    issue_id = await create_registered_object(
        db_session, ws_main, kind="issue", key="KAN-1", title="Issue", project_id=proj_id
    )

    # In-boundary LDAP group with raw DN
    g_ldap = await create_group(
        db_session,
        ws_main,
        "Internal LDAP Team",
        external_source="LDAP",
        external_id="CN=Secret,OU=Partner,DC=corp",
    )
    await add_role_binding(
        db_session, ws_main, g_ldap, role="VIEWER", scope_type="project", project_id=proj_id
    )

    # Out-of-boundary external guest collaborator
    external_user_id = await create_user(
        db_session,
        ws_main,
        handle="@secret_ext",
        display_name="Secret External Partner",
        email="secret@partner.example",
    )
    await add_role_binding(
        db_session, ws_main, external_user_id, role="WORKSPACE_GUEST", scope_type="workspace"
    )

    # Add direct ACL grant on KAN-1 to external user
    await add_acl_entry(
        db_session,
        ws_main,
        issue_id,
        external_user_id,
        effect="ALLOW",
        capability_mask=Capability.VIEW,
    )

    # Add direct ACL grant to host user
    await add_acl_entry(
        db_session, ws_main, issue_id, caller_id, effect="ALLOW", capability_mask=Capability.ALL
    )

    await rebuild_era(db_session, ws_main)

    caller = PrincipalContext(
        principal_id=caller_id, workspace_id=ws_main, token_scopes=("session",)
    )
    manifest = await build_access_manifest(db_session, caller, issue_id)

    raw_json = json.dumps(manifest.model_dump(mode="json"))

    # 1. Assert redaction counts and structure
    assert manifest.redacted_count >= 1
    assert any(
        re.search(r"External Collaborator", r.label) and r.redacted is True
        for r in manifest.redacted_entries
    )

    # 2. Strict anti-leakage invariants: Zero occurrence of forbidden identifiers
    forbidden_tokens = [
        "secret@partner.example",
        "secret_ext",
        "CN=Secret",
        str(external_user_id),
    ]

    for token in forbidden_tokens:
        assert token not in raw_json, (
            f"Information leakage detected! Found '{token}' in serialized manifest."
        )


@pytest.mark.asyncio
async def test_case_access_manifest_branches(db_session: AsyncSession) -> None:
    """Test private views, workspace-scoped objects, direct shares, and deny overrides."""
    ws_id = await create_workspace(db_session, name="Branch Workspace")
    admin_id = await create_user(db_session, ws_id, handle="@b_admin", display_name="Branch Admin")
    guest_user_id = await create_user(
        db_session, ws_id, handle="@b_guest", display_name="Guest User"
    )
    await add_role_binding(
        db_session, ws_id, guest_user_id, role="WORKSPACE_GUEST", scope_type="workspace"
    )

    # 1. Private View Inherited Scope
    view_id = await create_registered_object(
        db_session,
        ws_id,
        kind="view",
        key="view-private-1",
        title="Private View",
        created_by_id=admin_id,
    )
    view_row = View(
        id=view_id,
        object_type=ObjectKind.VIEW,
        workspace_id=ws_id,
        project_id=None,
        owner_principal_id=admin_id,
        visibility="private",
        name="Private View",
        summary_markdown="Private view",
        layout=ViewLayout.BOARD,
    )
    db_session.add(view_row)
    await db_session.flush()

    await add_acl_entry(
        db_session, ws_id, view_id, admin_id, effect="ALLOW", capability_mask=Capability.ALL
    )
    await add_acl_entry(
        db_session, ws_id, view_id, guest_user_id, effect="DENY", capability_mask=Capability.EDIT
    )

    agent_direct = await create_agent(db_session, ws_id, "Direct Agent", principal_type="AGENT")
    await add_acl_entry(
        db_session, ws_id, view_id, agent_direct, effect="ALLOW", capability_mask=Capability.VIEW
    )

    await rebuild_era(db_session, ws_id)

    caller = PrincipalContext(principal_id=admin_id, workspace_id=ws_id, token_scopes=("session",))
    manifest_view = await build_access_manifest(db_session, caller, view_id)

    assert manifest_view.inherited_scope.kind == "private"
    assert manifest_view.inherited_scope.scope_label == "Private"
    assert "Private" in manifest_view.pill_label
    assert any(ag.scope_summary == "Direct Share" for ag in manifest_view.agents)
    assert any(
        d.redacted is True and d.display_name == "1 Restricted Principal"
        for d in manifest_view.deny_overrides
    )

    # 2. Workspace Scoped Object (no project, explicit_grant_count == 0
    # -> pill_label == "Workspace")
    doc_id = await create_registered_object(
        db_session,
        ws_id,
        kind="doc",
        key="ws-doc-1",
        title="Workspace Doc",
        created_by_id=admin_id,
    )
    await add_role_binding(
        db_session, ws_id, admin_id, role="WORKSPACE_ADMIN", scope_type="workspace"
    )
    await rebuild_era(db_session, ws_id)

    manifest_doc = await build_access_manifest(db_session, caller, doc_id)
    assert manifest_doc.inherited_scope.kind == "workspace"
    assert manifest_doc.inherited_scope.project_id is None
    assert manifest_doc.explicit_grant_count == 0
    assert manifest_doc.pill_label == "Workspace"

    # 3. Object not found raises 404
    with pytest.raises(ProblemException) as exc_info:
        await build_access_manifest(db_session, caller, uuid.uuid4())
    assert exc_info.value.status == 404

    # 4. Public View Inherited Scope (falls through to project scope)
    proj_id = await create_project(
        db_session, ws_id, identifier="BRN", name="Branch Proj", created_by_id=admin_id
    )
    pub_view_id = await create_registered_object(
        db_session,
        ws_id,
        kind="view",
        key="view-pub-1",
        title="Public View",
        project_id=proj_id,
        created_by_id=admin_id,
    )
    pub_view_row = View(
        id=pub_view_id,
        object_type=ObjectKind.VIEW,
        workspace_id=ws_id,
        project_id=proj_id,
        owner_principal_id=admin_id,
        visibility="project",
        name="Public View",
        summary_markdown="Public view",
        layout=ViewLayout.BOARD,
    )
    db_session.add(pub_view_row)
    await db_session.flush()

    # User with project role
    proj_user_id = await create_user(
        db_session, ws_id, handle="@proj_user", display_name="Project User"
    )
    await add_role_binding(
        db_session, ws_id, proj_user_id, role="MEMBER", scope_type="project", project_id=proj_id
    )

    # Agent with project role
    agent_proj = await create_agent(db_session, ws_id, "Proj Agent", principal_type="AGENT")
    await add_role_binding(
        db_session, ws_id, agent_proj, role="VIEWER", scope_type="project", project_id=proj_id
    )

    # Ephemeral principal (out of boundary)
    ephem_agent = await create_agent(db_session, ws_id, "Ephem", principal_type="SCRIPT_EPHEMERAL")
    await add_acl_entry(
        db_session, ws_id, pub_view_id, ephem_agent, effect="ALLOW", capability_mask=Capability.VIEW
    )

    await rebuild_era(db_session, ws_id)

    manifest_pub = await build_access_manifest(db_session, caller, pub_view_id)
    assert manifest_pub.inherited_scope.kind == "project"
    assert manifest_pub.inherited_scope.project_key == "BRN"
    pu = next((u for u in manifest_pub.users if u.handle == "@proj_user"), None)
    assert pu is not None
    assert pu.grant_source == "project_role"
    ap = next((a for a in manifest_pub.agents if a.display_name == "Proj Agent"), None)
    assert ap is not None
    assert ap.scope_summary == "Project Scoped"
    assert manifest_pub.redacted_count >= 1


@pytest.mark.asyncio
async def test_access_manifest_edge_cases(db_session: AsyncSession) -> None:
    """Test boundary checks, fallbacks, and internal helper edge cases."""
    ws_id = await create_workspace(db_session, name="Edge WS")
    manifest_ctx = _ManifestContext(
        caller_ws_id=ws_id,
        project_owner_id=None,
        direct_allow=set(),
        project_roles={},
        workspace_roles={},
    )

    # 1. _is_out_of_boundary checks
    cross_p = Principal(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        principal_type="USER",
        status="ACTIVE",
        display_name="Cross User",
    )
    assert _is_out_of_boundary(cross_p, manifest_ctx) is True

    ephem_p = Principal(
        id=uuid.uuid4(), workspace_id=ws_id, principal_type="SCRIPT_EPHEMERAL", status="ACTIVE"
    )
    assert _is_out_of_boundary(ephem_p, manifest_ctx) is True

    # 2. _collect_deny_overrides with missing principal
    fake_acl = ResourceAclEntry(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        object_id=uuid.uuid4(),
        principal_id=uuid.uuid4(),
        effect="DENY",
        capability_mask=255,
    )
    overrides = await _collect_deny_overrides(db_session, [fake_acl], manifest_ctx)
    assert overrides == []

    # 3. User with email fallback (no ObjectRecord)
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.get.side_effect = [
        None,
        User(
            id=cross_p.id,
            object_type=ObjectKind.USER,
            principal_type="USER",
            workspace_id=ws_id,
            email="fallback@example.com",
        ),
    ]
    m_user = await _create_manifest_user(mock_session, cross_p, 1, manifest_ctx)
    assert m_user.handle == "@fallback"
    assert m_user.grant_source == "workspace_role"

    # User with neither ObjectRecord nor email
    mock_session.get.side_effect = [None, None]
    bare_m_user = await _create_manifest_user(mock_session, cross_p, 1, manifest_ctx)
    assert bare_m_user.handle.startswith("@")

    # 4. Agent with workspace scope (not in direct_allow and not in project_roles)
    ag_p = Principal(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        principal_type="AGENT",
        status="ACTIVE",
        display_name="WS Agent (harness)",
    )
    ag_m = _create_manifest_agent(ag_p, 1, manifest_ctx)
    assert ag_m.scope_summary == "Workspace Scoped"
