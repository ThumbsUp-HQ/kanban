"""Unit tests for Phase 1 role_bindings, resource_acl_entries, and effective_resource_access."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError

from database.tests.conftest import bind_ctx, bind_workspace_admin, bootstrap_workspace_admin

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _is_check_violation(exc: IntegrityError) -> bool:
    """Return True if exception indicates a PostgreSQL check_violation (23514)."""
    sqlstate = getattr(exc.orig, "sqlstate", None)
    return sqlstate == "23514" or "checkviolation" in str(exc).lower() or "23514" in str(exc)


async def _create_workspace(
    session: AsyncSession,
    slug: str | None = None,
    name: str = "Test Workspace",
) -> uuid.UUID:
    """Create a test workspace."""
    ws_slug = slug or f"ws-{uuid.uuid4().hex[:12]}"
    ws_id, _ = await bootstrap_workspace_admin(session, slug=ws_slug, name=name)
    return ws_id


async def _create_principal(
    session: AsyncSession,
    ws_id: uuid.UUID,
    *,
    principal_type: str = "USER",
    display_name: str = "Test Principal",
) -> uuid.UUID:
    """Create a principal in the principals table."""
    row = await session.execute(
        text(
            "INSERT INTO principals (workspace_id, principal_type, display_name) "
            "VALUES (:ws_id, :pt, :name) RETURNING id"
        ),
        {"ws_id": ws_id, "pt": principal_type, "name": display_name},
    )
    val = row.scalar_one()
    assert isinstance(val, uuid.UUID)
    return val


async def _create_group(
    session: AsyncSession,
    ws_id: uuid.UUID,
    name: str,
) -> uuid.UUID:
    """Create a principal and matching groups row."""
    p_id = await _create_principal(session, ws_id, principal_type="GROUP", display_name=name)
    await session.execute(
        text("INSERT INTO groups (id, workspace_id, name) VALUES (:id, :ws_id, :name)"),
        {"id": p_id, "ws_id": ws_id, "name": name},
    )
    return p_id


async def _create_project(
    session: AsyncSession,
    ws_id: uuid.UUID,
    *,
    identifier: str = "PRJ",
    name: str = "Test Project",
) -> uuid.UUID:
    """Register and create a project in the database."""
    u_id = uuid.uuid4()
    reg_row = await session.execute(
        text(
            "SELECT register_object("
            "  'project'::object_kind, :ws_id, NULL, :identifier, :name, :u_id"
            ")"
        ),
        {"ws_id": ws_id, "identifier": identifier, "name": name, "u_id": u_id},
    )
    proj_id = reg_row.scalar_one()
    assert isinstance(proj_id, uuid.UUID)
    await session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, identifier, name) "
            "VALUES (:id, :ws_id, :identifier, :name)"
        ),
        {"id": proj_id, "ws_id": ws_id, "identifier": identifier, "name": name},
    )
    return proj_id


async def _register_obj(
    session: AsyncSession,
    ws_id: uuid.UUID,
    kind: str,
    key: str,
    project_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Register an entity in the objects spine."""
    u_id = uuid.uuid4()
    row = await session.execute(
        text(
            "SELECT register_object("
            "  CAST(:kind AS object_kind), :ws_id, :proj_id, :key, :title, :u_id"
            ")"
        ),
        {
            "kind": kind,
            "ws_id": ws_id,
            "proj_id": project_id,
            "key": key,
            "title": f"{key} object",
            "u_id": u_id,
        },
    )
    val = row.scalar_one()
    assert isinstance(val, uuid.UUID)
    return val


async def test_01_rbac_and_nested_group_inheritance(app_session: AsyncSession) -> None:
    """Test RBAC role bindings through nested groups (U in G1 -> G2 -> G3)."""
    ws_id = await _create_workspace(app_session)
    user_u = await _create_principal(
        app_session, ws_id, principal_type="USER", display_name="User U"
    )
    g1 = await _create_group(app_session, ws_id, "Group 1")
    g2 = await _create_group(app_session, ws_id, "Group 2")
    g3 = await _create_group(app_session, ws_id, "Group 3")

    # Link U -> G1 -> G2 -> G3
    await app_session.execute(
        text(
            "INSERT INTO principal_group_edges (member_id, group_id, workspace_id) VALUES "
            "(:u, :g1, :ws_id), (:g1, :g2, :ws_id), (:g2, :g3, :ws_id)"
        ),
        {"u": user_u, "g1": g1, "g2": g2, "g3": g3, "ws_id": ws_id},
    )

    kan_proj = await _create_project(app_session, ws_id, identifier="KAN", name="Kanban Project")

    # Bind G3 as MEMBER (31) on project KAN
    await app_session.execute(
        text(
            "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:ws_id, :g3, 'MEMBER', 'project', :proj_id)"
        ),
        {"ws_id": ws_id, "g3": g3, "proj_id": kan_proj},
    )

    # Register child issue KAN-1
    issue_id = await _register_obj(app_session, ws_id, "issue", "KAN-1", kan_proj)

    # Query effective_resource_access for (KAN-1, U)
    res = await app_session.execute(
        text(
            "SELECT allow_mask, deny_mask, effective_mask "
            "FROM effective_resource_access "
            "WHERE object_id = :obj_id AND principal_id = :u_id"
        ),
        {"obj_id": issue_id, "u_id": user_u},
    )
    row = res.fetchone()
    assert row is not None
    assert row.allow_mask == 31
    assert row.deny_mask == 0
    assert row.effective_mask == 31

    # Verify app_effective_principal_set under U returns {U, G1, G2, G3}
    await bind_ctx(app_session, user_u, ws_id)
    set_res = await app_session.execute(text("SELECT app_effective_principal_set()"))
    p_set = set_res.scalar_one()
    assert set(p_set) == {user_u, g1, g2, g3}


async def test_02_explicit_deny_precedence_and_group_acls(app_session: AsyncSession) -> None:
    """Test explicit deny precedence: direct and sibling-group DENY overrides group ALLOW."""
    ws_id = await _create_workspace(app_session)
    user_u = await _create_principal(
        app_session, ws_id, principal_type="USER", display_name="User U"
    )
    g1 = await _create_group(app_session, ws_id, "Group 1")
    g_contractors = await _create_group(app_session, ws_id, "Contractors")

    # U in G1 and U in G_contractors
    await app_session.execute(
        text(
            "INSERT INTO principal_group_edges (member_id, group_id, workspace_id) VALUES "
            "(:u, :g1, :ws_id), (:u, :gc, :ws_id)"
        ),
        {"u": user_u, "g1": g1, "gc": g_contractors, "ws_id": ws_id},
    )

    kan_proj = await _create_project(app_session, ws_id, identifier="DNY", name="Deny Project")

    # Bind G1 as MEMBER (31) on project
    await app_session.execute(
        text(
            "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:ws_id, :g1, 'MEMBER', 'project', :proj_id)"
        ),
        {"ws_id": ws_id, "g1": g1, "proj_id": kan_proj},
    )

    issue_id = await _register_obj(app_session, ws_id, "issue", "DNY-1", kan_proj)

    # G1 holds ALLOW VIEW|EDIT (5) on DNY-1
    await app_session.execute(
        text(
            "INSERT INTO resource_acl_entries ("
            "  workspace_id, object_id, principal_id, effect, capability_mask"
            ") VALUES (:ws_id, :obj_id, :g1, 'ALLOW', 5)"
        ),
        {"ws_id": ws_id, "obj_id": issue_id, "g1": g1},
    )

    # Adding DENY EDIT (4) directly on U
    await app_session.execute(
        text(
            "INSERT INTO resource_acl_entries ("
            "  workspace_id, object_id, principal_id, effect, capability_mask"
            ") VALUES (:ws_id, :obj_id, :u, 'DENY', 4)"
        ),
        {"ws_id": ws_id, "obj_id": issue_id, "u": user_u},
    )

    res = await app_session.execute(
        text(
            "SELECT allow_mask, deny_mask, effective_mask "
            "FROM effective_resource_access "
            "WHERE object_id = :obj_id AND principal_id = :u_id"
        ),
        {"obj_id": issue_id, "u_id": user_u},
    )
    row = res.fetchone()
    assert row is not None
    assert row.allow_mask == 31
    assert row.deny_mask == 4
    assert row.effective_mask == 27  # 31 & (~4) = 27

    # Adding DENY VIEW (1) via sibling group G_contractors
    await app_session.execute(
        text(
            "INSERT INTO resource_acl_entries ("
            "  workspace_id, object_id, principal_id, effect, capability_mask"
            ") VALUES (:ws_id, :obj_id, :gc, 'DENY', 1)"
        ),
        {"ws_id": ws_id, "obj_id": issue_id, "gc": g_contractors},
    )

    # Now verify S3.3 RLS predicate evaluates to FALSE under U's session context
    await bind_ctx(app_session, user_u, ws_id)
    rls_check = await app_session.execute(
        text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM effective_resource_access era "
            "  WHERE era.object_id = :obj_id "
            "    AND era.principal_id = ANY (app_effective_principal_set()) "
            "    AND (era.allow_mask & 1) = 1 "
            "    AND (era.deny_mask & 1) = 0"
            ")"
        ),
        {"obj_id": issue_id},
    )
    assert rls_check.scalar_one() is False

    # Verify zero group rows exist in effective_resource_access
    grp_rows = await app_session.execute(
        text("SELECT count(*) FROM effective_resource_access WHERE principal_id IN (:g1, :gc)"),
        {"g1": g1, "gc": g_contractors},
    )
    assert grp_rows.scalar_one() == 0


async def test_03_project_level_deny_and_principal_disable(app_session: AsyncSession) -> None:
    """Test project-level DENY inheritance to child issues and principal status disable."""
    ws_id = await _create_workspace(app_session)
    user_u = await _create_principal(
        app_session, ws_id, principal_type="USER", display_name="User U"
    )
    gc = await _create_group(app_session, ws_id, "Contractor Group")

    await app_session.execute(
        text(
            "INSERT INTO principal_group_edges (member_id, group_id, workspace_id) "
            "VALUES (:u, :gc, :ws_id)"
        ),
        {"u": user_u, "gc": gc, "ws_id": ws_id},
    )

    kan_proj = await _create_project(app_session, ws_id, identifier="PRD", name="Propagate Project")

    # Bind GC as MEMBER on project
    await app_session.execute(
        text(
            "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:ws_id, :gc, 'MEMBER', 'project', :proj_id)"
        ),
        {"ws_id": ws_id, "gc": gc, "proj_id": kan_proj},
    )

    # Register child issue PRD-1
    issue_id = await _register_obj(app_session, ws_id, "issue", "PRD-1", kan_proj)

    # DENY VIEW (1) for G_contractors on project KAN (kan_proj)
    await app_session.execute(
        text(
            "INSERT INTO resource_acl_entries ("
            "  workspace_id, object_id, principal_id, effect, capability_mask"
            ") VALUES (:ws_id, :proj_id, :gc, 'DENY', 1)"
        ),
        {"ws_id": ws_id, "proj_id": kan_proj, "gc": gc},
    )

    # Verify project KAN has deny_mask & 1 == 1
    p_res = await app_session.execute(
        text(
            "SELECT deny_mask FROM effective_resource_access "
            "WHERE object_id = :proj_id AND principal_id = :u_id"
        ),
        {"proj_id": kan_proj, "u_id": user_u},
    )
    p_row = p_res.fetchone()
    assert p_row is not None
    assert (p_row.deny_mask & 1) == 1

    # Verify child issue PRD-1 also inherited deny_mask & 1 == 1
    i_res = await app_session.execute(
        text(
            "SELECT deny_mask FROM effective_resource_access "
            "WHERE object_id = :obj_id AND principal_id = :u_id"
        ),
        {"obj_id": issue_id, "u_id": user_u},
    )
    i_row = i_res.fetchone()
    assert i_row is not None
    assert (i_row.deny_mask & 1) == 1

    # Setting principals.status = 'DISABLED' on U removes effective access
    await app_session.execute(
        text("UPDATE principals SET status = 'DISABLED' WHERE id = :u_id"),
        {"u_id": user_u},
    )

    u_era = await app_session.execute(
        text("SELECT count(*) FROM effective_resource_access WHERE principal_id = :u_id"),
        {"u_id": user_u},
    )
    assert u_era.scalar_one() == 0

    # app_effective_principal_set() under disabled U returns empty array
    await bind_ctx(app_session, user_u, ws_id)
    empty_res = await app_session.execute(text("SELECT app_effective_principal_set()"))
    assert empty_res.scalar_one() == []


async def test_04_agent_non_inheritance_and_app_principal_has_role(
    app_session: AsyncSession,
) -> None:
    """Test autonomous agent non-inheritance and app_principal_has_role behavior."""
    ws_id = await _create_workspace(app_session)
    agent_id = await _create_principal(
        app_session, ws_id, principal_type="AGENT", display_name="Bot Agent"
    )
    admin_id = await _create_principal(
        app_session, ws_id, principal_type="USER", display_name="Admin User"
    )
    member_id = await _create_principal(
        app_session, ws_id, principal_type="USER", display_name="Member User"
    )

    kan_proj = await _create_project(app_session, ws_id, identifier="AGT", name="Agent Project")
    other_proj = await _create_project(app_session, ws_id, identifier="OTH", name="Other Project")
    issue_id = await _register_obj(app_session, ws_id, "issue", "AGT-1", kan_proj)

    # Bind Admin as PROJECT_ADMIN on KAN, Member as MEMBER on KAN
    await app_session.execute(
        text(
            "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES "
            "(:ws_id, :admin_id, 'PROJECT_ADMIN', 'project', :p_id), "
            "(:ws_id, :member_id, 'MEMBER', 'project', :p_id)"
        ),
        {"ws_id": ws_id, "admin_id": admin_id, "member_id": member_id, "p_id": kan_proj},
    )

    # Agent has zero explicit bindings -> 0 rows in effective_resource_access
    agent_era = await app_session.execute(
        text(
            "SELECT count(*) FROM effective_resource_access "
            "WHERE object_id = :obj_id AND principal_id = :a_id"
        ),
        {"obj_id": issue_id, "a_id": agent_id},
    )
    assert agent_era.scalar_one() == 0

    # Test app_principal_has_role:
    # 1. Admin on KAN -> TRUE for PROJECT_ADMIN
    await bind_ctx(app_session, admin_id, ws_id)
    r1 = await app_session.execute(
        text("SELECT app_principal_has_role(:p_id, ARRAY['PROJECT_ADMIN', 'SERVER_ADMIN'])"),
        {"p_id": kan_proj},
    )
    assert r1.scalar_one() is True

    # 2. Member on KAN -> FALSE for PROJECT_ADMIN/SERVER_ADMIN
    await bind_ctx(app_session, member_id, ws_id)
    r2 = await app_session.execute(
        text("SELECT app_principal_has_role(:p_id, ARRAY['PROJECT_ADMIN', 'SERVER_ADMIN'])"),
        {"p_id": kan_proj},
    )
    assert r2.scalar_one() is False

    # 3. Admin on OTHER -> FALSE because role is on KAN, not OTH
    await bind_ctx(app_session, admin_id, ws_id)
    r3 = await app_session.execute(
        text("SELECT app_principal_has_role(:p_id, ARRAY['PROJECT_ADMIN', 'SERVER_ADMIN'])"),
        {"p_id": other_proj},
    )
    assert r3.scalar_one() is False


async def test_05_cross_workspace_and_check_constraints(app_session: AsyncSession) -> None:
    """Test cross-workspace rejection, invalid role scope, and permission guards."""
    ws1 = await _create_workspace(app_session)
    ws2 = await _create_workspace(app_session)
    await bind_workspace_admin(app_session, ws1)
    user_ws1 = await _create_principal(app_session, ws1, principal_type="USER")
    await bind_workspace_admin(app_session, ws2)
    user_ws2 = await _create_principal(app_session, ws2, principal_type="USER")
    await bind_workspace_admin(app_session, ws1)
    proj_ws1 = await _create_project(app_session, ws1, identifier="CW1")

    # 1. Cross-workspace role_bindings raises ROLE_BINDING_WORKSPACE_MISMATCH
    sp1 = await app_session.begin_nested()
    with pytest.raises(DBAPIError) as exc1:
        await app_session.execute(
            text(
                "INSERT INTO role_bindings ("
                "  workspace_id, principal_id, role, scope_type, project_id"
                ") VALUES (:ws_id, :p_id, 'WORKSPACE_MEMBER', 'workspace', NULL)"
            ),
            {"ws_id": ws1, "p_id": user_ws2},
        )
    assert "ROLE_BINDING_WORKSPACE_MISMATCH" in str(exc1.value)
    await sp1.rollback()

    # 2. Cross-workspace resource_acl_entries raises ACL_WORKSPACE_MISMATCH
    sp2 = await app_session.begin_nested()
    with pytest.raises(DBAPIError) as exc2:
        await app_session.execute(
            text(
                "INSERT INTO resource_acl_entries ("
                "  workspace_id, object_id, principal_id, effect, capability_mask"
                ") VALUES (:ws_id, :obj_id, :p_id, 'ALLOW', 1)"
            ),
            {"ws_id": ws1, "obj_id": proj_ws1, "p_id": user_ws2},
        )
    assert "ACL_WORKSPACE_MISMATCH" in str(exc2.value)
    await sp2.rollback()

    # 3. Invalid (scope_type='project', role='SERVER_ADMIN') raises 23514
    sp3 = await app_session.begin_nested()
    with pytest.raises(IntegrityError) as exc3:
        await app_session.execute(
            text(
                "INSERT INTO role_bindings ("
                "  workspace_id, principal_id, role, scope_type, project_id"
                ") VALUES (:ws_id, :p_id, 'SERVER_ADMIN', 'project', :proj_id)"
            ),
            {"ws_id": ws1, "p_id": user_ws1, "proj_id": proj_ws1},
        )
    assert _is_check_violation(exc3.value)
    await sp3.rollback()

    # 4. capability_mask = 0 raises 23514
    sp4 = await app_session.begin_nested()
    with pytest.raises(IntegrityError) as exc4:
        await app_session.execute(
            text(
                "INSERT INTO resource_acl_entries ("
                "  workspace_id, object_id, principal_id, effect, capability_mask"
                ") VALUES (:ws_id, :obj_id, :p_id, 'ALLOW', 0)"
            ),
            {"ws_id": ws1, "obj_id": proj_ws1, "p_id": user_ws1},
        )
    assert _is_check_violation(exc4.value)
    await sp4.rollback()

    # 5. Direct INSERT into effective_resource_access raises 42501 (insufficient_privilege)
    sp5 = await app_session.begin_nested()
    with pytest.raises(ProgrammingError) as exc5:
        await app_session.execute(
            text(
                "INSERT INTO effective_resource_access ("
                "  object_id, principal_id, workspace_id, allow_mask, deny_mask"
                ") VALUES (:obj_id, :p_id, :ws_id, 31, 0)"
            ),
            {"obj_id": proj_ws1, "p_id": user_ws1, "ws_id": ws1},
        )
    assert "42501" in str(exc5.value) or "permission denied" in str(exc5.value).lower()
    await sp5.rollback()


async def test_06_dynamic_reactivity_edge_removal(app_session: AsyncSession) -> None:
    """Test dynamic reactivity: dropping group edge drops inherited access in same statement."""
    ws_id = await _create_workspace(app_session)
    user_u = await _create_principal(
        app_session, ws_id, principal_type="USER", display_name="User U"
    )
    g1 = await _create_group(app_session, ws_id, "Group 1")
    g2 = await _create_group(app_session, ws_id, "Group 2")

    await app_session.execute(
        text(
            "INSERT INTO principal_group_edges (member_id, group_id, workspace_id) VALUES "
            "(:u, :g1, :ws_id), (:g1, :g2, :ws_id)"
        ),
        {"u": user_u, "g1": g1, "g2": g2, "ws_id": ws_id},
    )

    kan_proj = await _create_project(app_session, ws_id, identifier="REA", name="React Project")

    # Bind G2 as MEMBER on project
    await app_session.execute(
        text(
            "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:ws_id, :g2, 'MEMBER', 'project', :proj_id)"
        ),
        {"ws_id": ws_id, "g2": g2, "proj_id": kan_proj},
    )

    issue_id = await _register_obj(app_session, ws_id, "issue", "REA-1", kan_proj)

    # U has access via G1 -> G2
    res_before = await app_session.execute(
        text(
            "SELECT allow_mask FROM effective_resource_access "
            "WHERE object_id = :obj_id AND principal_id = :u_id"
        ),
        {"obj_id": issue_id, "u_id": user_u},
    )
    row_b = res_before.fetchone()
    assert row_b is not None
    assert row_b.allow_mask == 31

    # Drop edge G1 -> G2
    await app_session.execute(
        text("DELETE FROM principal_group_edges WHERE member_id = :g1 AND group_id = :g2"),
        {"g1": g1, "g2": g2},
    )

    # U immediately loses access
    res_after = await app_session.execute(
        text(
            "SELECT count(*) FROM effective_resource_access "
            "WHERE object_id = :obj_id AND principal_id = :u_id"
        ),
        {"obj_id": issue_id, "u_id": user_u},
    )
    assert res_after.scalar_one() == 0
