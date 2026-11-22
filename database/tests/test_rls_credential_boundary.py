# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Comprehensive unit and integration tests for PostgreSQL FORCE RLS CredentialBoundary GUCs.

Validates KB-SEC-05 Action 1:
1. RLSContext and bind_rls_context credential parameter binding.
2. app.credential_workspaces, app.credential_projects, app.credential_capability_mask GUCs.
3. SQL helper functions: app_credential_workspaces, app_credential_projects,
   app_credential_capability_mask.
4. Fail-closed row-level security enforcement for workspace allowlists, project allowlists,
   and capability bitmasks.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from database.rls.context import (
    RLSContext,
    bind_rls_context,
)
from database.tests.test_p1_14_rls_policies import (
    _create_issue,
    _create_project,
    _create_user,
    _create_workspace,
)

_CAP_VIEW = 1
_CAP_EDIT = 4
_CAP_TRANSITION = 8
_CAP_DELETE = 128

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def test_rls_context_credential_boundary_initialization() -> None:
    """Verify RLSContext accepts and normalizes credential boundary parameters."""
    p_id = uuid.uuid4()
    w_id = uuid.uuid4()
    ws1 = uuid.uuid4()
    proj1 = uuid.uuid4()

    # 1. Direct tuple parameters
    ctx = RLSContext(
        principal_id=p_id,
        workspace_id=w_id,
        credential_workspaces=(ws1,),
        credential_projects=(proj1,),
        credential_capability_mask=15,
    )
    assert ctx.credential_workspaces == (ws1,)
    assert ctx.credential_projects == (proj1,)
    assert ctx.credential_capability_mask == 15

    # 2. String conversion in tuples
    ctx_str = RLSContext(
        principal_id=p_id,
        workspace_id=w_id,
        credential_workspaces=(str(ws1),),  # type: ignore[arg-type]
        credential_projects=(str(proj1),),  # type: ignore[arg-type]
        credential_capability_mask="7",  # type: ignore[arg-type]
    )
    assert ctx_str.credential_workspaces == (ws1,)
    assert ctx_str.credential_projects == (proj1,)
    assert ctx_str.credential_capability_mask == 7

    # 3. Duck-typed CredentialBoundary object ingestion
    boundary_mock = MagicMock()
    boundary_mock.workspace_allowlist = frozenset({ws1})
    boundary_mock.project_allowlist = frozenset({proj1})
    boundary_mock.capability_mask = 31

    ctx_boundary = RLSContext(
        principal_id=p_id,
        workspace_id=w_id,
        credential_boundary=boundary_mock,
    )
    assert ws1 in ctx_boundary.credential_workspaces
    assert proj1 in ctx_boundary.credential_projects
    assert ctx_boundary.credential_capability_mask == 31


async def test_bind_rls_context_sets_credential_gucs(app_session: AsyncSession) -> None:
    """Verify bind_rls_context binds app.credential_* session GUCs via SET LOCAL."""
    p_id = uuid.uuid4()
    w_id = uuid.uuid4()
    ws1 = uuid.uuid4()
    ws2 = uuid.uuid4()
    proj1 = uuid.uuid4()

    ctx = RLSContext(
        principal_id=p_id,
        workspace_id=w_id,
        credential_workspaces=(ws1, ws2),
        credential_projects=(proj1,),
        credential_capability_mask=_CAP_VIEW | _CAP_EDIT,
    )

    await bind_rls_context(app_session, ctx)

    # Inspect current_setting values
    res_ws = await app_session.scalar(
        text("SELECT current_setting('app.credential_workspaces', true)")
    )
    assert str(ws1) in str(res_ws)
    assert str(ws2) in str(res_ws)

    res_proj = await app_session.scalar(
        text("SELECT current_setting('app.credential_projects', true)")
    )
    assert str(res_proj) == str(proj1)

    res_mask = await app_session.scalar(
        text("SELECT current_setting('app.credential_capability_mask', true)")
    )
    assert str(res_mask) == str(_CAP_VIEW | _CAP_EDIT)

    # Test SQL helper functions
    helper_ws = await app_session.scalar(text("SELECT app_credential_workspaces()"))
    assert set(helper_ws) == {ws1, ws2}

    helper_proj = await app_session.scalar(text("SELECT app_credential_projects()"))
    assert set(helper_proj) == {proj1}

    helper_mask = await app_session.scalar(text("SELECT app_credential_capability_mask()"))
    assert helper_mask == _CAP_VIEW | _CAP_EDIT


async def test_rls_workspace_allowlist_enforcement(app_session: AsyncSession) -> None:
    """Verify app.credential_workspaces restricts app_current_workspace_id fail-closed."""
    await app_session.execute(text("RESET SESSION AUTHORIZATION"))
    ws1 = await _create_workspace(app_session, name="Workspace 1")
    ws2 = await _create_workspace(app_session, name="Workspace 2")
    user_id, _ = await _create_user(app_session, ws1, display_name="Alice")

    await app_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))

    # 1. When session matches allowed workspace, app_current_workspace_id returns ws1
    ctx_allowed = RLSContext(
        principal_id=user_id,
        workspace_id=ws1,
        credential_workspaces=(ws1,),
    )
    await bind_rls_context(app_session, ctx_allowed)
    cur_ws = await app_session.scalar(text("SELECT app_current_workspace_id()"))
    assert cur_ws == ws1

    # 2. When session targets ws2 outside allowed workspaces (ws1),
    # app_current_workspace_id returns NULL
    ctx_denied = RLSContext(
        principal_id=user_id,
        workspace_id=ws2,
        credential_workspaces=(ws1,),
    )
    await bind_rls_context(app_session, ctx_denied)
    cur_ws_denied = await app_session.scalar(text("SELECT app_current_workspace_id()"))
    assert cur_ws_denied is None

    # Workspace query returns 0 rows fail-closed
    rows = (await app_session.execute(text("SELECT id FROM workspaces"))).scalars().all()
    assert len(rows) == 0


async def test_rls_project_allowlist_enforcement(app_session: AsyncSession) -> None:
    """Verify app.credential_projects restricts visibility and capabilities to allowed projects."""
    await app_session.execute(text("RESET SESSION AUTHORIZATION"))
    ws_id = await _create_workspace(app_session, name="Project Scope WS")
    user_id, _ = await _create_user(app_session, ws_id, display_name="Bob")

    proj1_id, _, _ = await _create_project(
        app_session, ws_id, user_id, identifier="PR1", name="Project 1"
    )
    proj2_id, _, _ = await _create_project(
        app_session, ws_id, user_id, identifier="PR2", name="Project 2"
    )

    # Grant Workspace Admin to user so they would normally see all projects
    await app_session.execute(
        text(
            "INSERT INTO role_bindings (principal_id, workspace_id, role, scope_type, project_id) "
            "VALUES (:p_id, :ws_id, 'WORKSPACE_ADMIN', 'workspace', NULL)"
        ),
        {"p_id": user_id, "ws_id": ws_id},
    )
    await app_session.execute(
        text("SELECT rebuild_effective_access_for_workspace(:ws_id)"),
        {"ws_id": ws_id},
    )

    await app_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))

    # 1. Unconstrained session sees both projects
    ctx_full = RLSContext(
        principal_id=user_id,
        workspace_id=ws_id,
    )
    await bind_rls_context(app_session, ctx_full)
    projs_full = (
        (
            await app_session.execute(
                text("SELECT id FROM projects WHERE id IN (:p1, :p2)"),
                {"p1": proj1_id, "p2": proj2_id},
            )
        )
        .scalars()
        .all()
    )
    assert set(projs_full) == {proj1_id, proj2_id}

    # 2. Session bounded to proj1 sees only proj1
    ctx_scoped = RLSContext(
        principal_id=user_id,
        workspace_id=ws_id,
        credential_projects=(proj1_id,),
    )
    await bind_rls_context(app_session, ctx_scoped)

    # Capability check
    can_view_p1 = await app_session.scalar(
        text("SELECT app_has_object_capability(:p_id, 1)"),
        {"p_id": proj1_id},
    )
    assert can_view_p1 is True

    can_view_p2 = await app_session.scalar(
        text("SELECT app_has_object_capability(:p_id, 1)"),
        {"p_id": proj2_id},
    )
    assert can_view_p2 is False

    # Projects table query enforces project allowlist at SQL row level
    projs_scoped = (
        (
            await app_session.execute(
                text("SELECT id FROM projects WHERE id IN (:p1, :p2)"),
                {"p1": proj1_id, "p2": proj2_id},
            )
        )
        .scalars()
        .all()
    )
    assert projs_scoped == [proj1_id]

    # Objects table query enforces project allowlist at SQL row level
    objs_scoped = (
        (
            await app_session.execute(
                text("SELECT id FROM objects WHERE id IN (:p1, :p2)"),
                {"p1": proj1_id, "p2": proj2_id},
            )
        )
        .scalars()
        .all()
    )
    assert objs_scoped == [proj1_id]

    # Role check on proj2 returns false
    has_p2_role = await app_session.scalar(
        text("SELECT app_principal_has_role(:p_id, ARRAY['WORKSPACE_ADMIN', 'PROJECT_ADMIN'])"),
        {"p_id": proj2_id},
    )
    assert has_p2_role is False


async def test_rls_capability_mask_enforcement(app_session: AsyncSession) -> None:
    """Verify app.credential_capability_mask enforces capability bitmask at SQL row level."""
    await app_session.execute(text("RESET SESSION AUTHORIZATION"))
    ws_id = await _create_workspace(app_session, name="Cap Mask WS")
    user_id, _ = await _create_user(app_session, ws_id, display_name="Charlie")
    proj_id, state_id, prio_id = await _create_project(
        app_session, ws_id, user_id, identifier="CAP", name="Cap Project"
    )

    # Create issue in project
    issue_id = await _create_issue(
        app_session,
        ws_id,
        proj_id,
        user_id,
        state_id,
        prio_id,
        summary="Test Issue",
    )

    # Grant Workspace Admin to user
    await app_session.execute(
        text(
            "INSERT INTO role_bindings (principal_id, workspace_id, role, scope_type, project_id) "
            "VALUES (:p_id, :ws_id, 'WORKSPACE_ADMIN', 'workspace', NULL)"
        ),
        {"p_id": user_id, "ws_id": ws_id},
    )
    await app_session.execute(
        text("SELECT rebuild_effective_access_for_workspace(:ws_id)"),
        {"ws_id": ws_id},
    )

    await app_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))

    # 1. Read-only capability mask (_CAP_VIEW = 1)
    ctx_view_only = RLSContext(
        principal_id=user_id,
        workspace_id=ws_id,
        credential_capability_mask=_CAP_VIEW,
    )
    await bind_rls_context(app_session, ctx_view_only)

    can_view = await app_session.scalar(
        text("SELECT app_has_object_capability(:id, 1)"), {"id": issue_id}
    )
    can_edit = await app_session.scalar(
        text("SELECT app_has_object_capability(:id, 4)"), {"id": issue_id}
    )
    can_trans = await app_session.scalar(
        text("SELECT app_has_object_capability(:id, 8)"), {"id": issue_id}
    )
    can_del = await app_session.scalar(
        text("SELECT app_has_object_capability(:id, 128)"), {"id": issue_id}
    )

    assert can_view is True
    assert can_edit is False
    assert can_trans is False
    assert can_del is False

    # Issue is visible on SELECT
    selected_issue = await app_session.scalar(
        text("SELECT id FROM issues WHERE id = :id"), {"id": issue_id}
    )
    assert selected_issue == issue_id

    # Direct UPDATE fails WITH CHECK because EDIT (4) capability is masked out
    with pytest.raises(SQLAlchemyError) as exc_info:
        async with app_session.begin_nested():
            await app_session.execute(
                text("UPDATE issues SET summary = 'Malicious Update' WHERE id = :id"),
                {"id": issue_id},
            )
    assert "row-level security policy" in str(exc_info.value).lower()

    # Direct DELETE fails because DELETE (128) capability is masked out in USING
    del_res = await app_session.execute(
        text("DELETE FROM issues WHERE id = :id"),
        {"id": issue_id},
    )
    assert getattr(del_res, "rowcount", 0) == 0

    # 2. Read + Edit capability mask (_CAP_VIEW | _CAP_EDIT = 5)
    ctx_view_edit = RLSContext(
        principal_id=user_id,
        workspace_id=ws_id,
        credential_capability_mask=_CAP_VIEW | _CAP_EDIT,
    )
    await bind_rls_context(app_session, ctx_view_edit)

    can_view_2 = await app_session.scalar(
        text("SELECT app_has_object_capability(:id, 1)"), {"id": issue_id}
    )
    can_edit_2 = await app_session.scalar(
        text("SELECT app_has_object_capability(:id, 4)"), {"id": issue_id}
    )
    can_trans_2 = await app_session.scalar(
        text("SELECT app_has_object_capability(:id, 8)"), {"id": issue_id}
    )

    assert can_view_2 is True
    assert can_edit_2 is True
    assert can_trans_2 is False

    # UPDATE succeeds because EDIT capability is present in bitmask
    await app_session.execute(
        text("UPDATE issues SET summary = 'Permitted Update' WHERE id = :id"),
        {"id": issue_id},
    )
    updated_summary = await app_session.scalar(
        text("SELECT summary FROM issues WHERE id = :id"), {"id": issue_id}
    )
    assert updated_summary == "Permitted Update"
