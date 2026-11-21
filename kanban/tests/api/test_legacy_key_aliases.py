# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration tests for legacy key alias resolution (KB-P6-03)."""
# ruff: noqa: E501, PLC0415, TC002, RUF059

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Issue, IssueKeyAlias
from database.tests.conftest import bootstrap_workspace_admin
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.app import create_app
from kanban.resolve.service import ResolutionService
from kanban.services.issue_keys import resolve_issue_ref


@pytest.fixture
async def setup_alias_env(
    db_session: AsyncSession,
) -> tuple[AsyncSession, PrincipalContext, Issue, IssueKeyAlias]:
    """Bootstrap workspace, project, canonical issue, and alias."""
    ws_id, admin_id = await bootstrap_workspace_admin(db_session)

    await db_session.execute(
        text(
            "SELECT set_config('app.current_workspace_id', :ws, true), "
            "set_config('app.current_principal_id', :pid, true), "
            "set_config('app.aal_level', '2', true)"
        ),
        {"ws": str(ws_id), "pid": str(admin_id)},
    )

    caller = PrincipalContext(
        principal_id=admin_id,
        workspace_id=ws_id,
        aal_level=2,
    )

    # Create project
    proj_id = (
        await db_session.execute(
            text(
                "SELECT register_object('project'::object_kind, :ws, NULL, 'CORE', 'Core Project', :admin)"
            ),
            {"ws": ws_id, "admin": admin_id},
        )
    ).scalar_one()

    await db_session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, identifier, name, description_markdown) "
            "VALUES (:id, :ws, 'CORE', 'Core Project', 'Core issue tracking')"
        ),
        {"id": proj_id, "ws": ws_id},
    )

    # Get default state (seeded by trigger)
    state_id = (
        await db_session.execute(
            text("SELECT id FROM workflow_states WHERE project_id = :proj AND is_default LIMIT 1"),
            {"proj": proj_id},
        )
    ).scalar_one()

    # Create canonical issue: CORE-1
    seq = (
        await db_session.execute(
            text("SELECT allocate_issue_sequence(:proj)"),
            {"proj": proj_id},
        )
    ).scalar_one()

    issue_id = (
        await db_session.execute(
            text(
                "SELECT register_object('issue'::object_kind, :ws, :proj, :key, 'Canonical Issue One', :admin)"
            ),
            {"ws": ws_id, "proj": proj_id, "key": f"CORE-{seq}", "admin": admin_id},
        )
    ).scalar_one()

    # Get default priority (seeded by trigger)
    prio_id = (
        await db_session.execute(
            text(
                "SELECT id FROM project_priorities WHERE project_id = :proj AND is_default LIMIT 1"
            ),
            {"proj": proj_id},
        )
    ).scalar_one()

    await db_session.execute(
        text(
            "INSERT INTO issues (id, workspace_id, project_id, sequence_id, summary, description_markdown, state_id, priority_id, created_by_id, original_created_by_id, board_rank) "
            "VALUES (:id, :ws, :proj, :seq, 'Canonical Issue One', 'Canonical description', :state, :prio, :admin, :admin, '0|hzzzzz:')"
        ),
        {
            "id": issue_id,
            "ws": ws_id,
            "proj": proj_id,
            "seq": seq,
            "state": state_id,
            "prio": prio_id,
            "admin": admin_id,
        },
    )

    # Create legacy aliases: KANBA-123, JIRA-101, GH-88, ENG-42
    aliases = [
        ("KANBA-123", "plane"),
        ("JIRA-101", "jira"),
        ("GH-88", "github"),
        ("ENG-42", "linear"),
    ]
    created_aliases = []
    for leg_key, src in aliases:
        alias = IssueKeyAlias(
            workspace_id=ws_id,
            legacy_key=leg_key,
            issue_id=issue_id,
            source_system=src,
        )
        db_session.add(alias)
        created_aliases.append(alias)

    await db_session.commit()

    iss_res = await db_session.execute(select(Issue).where(Issue.id == issue_id))
    canonical_issue = iss_res.scalar_one()

    return db_session, caller, canonical_issue, created_aliases[0]


@pytest.mark.asyncio
async def test_resolution_service_legacy_aliases(
    setup_alias_env: tuple[AsyncSession, PrincipalContext, Issue, IssueKeyAlias],
) -> None:
    """Verify ResolutionService resolves KANBA-123, JIRA-101, GH-88, and ENG-42 to CORE-1."""
    session, caller, canonical_issue, _ = setup_alias_env

    resolver = ResolutionService()

    for test_key in ("KANBA-123", "JIRA-101", "GH-88", "ENG-42"):
        resolved = await resolver.resolve(
            session=session,
            kind="issue",
            ref=test_key,
            caller_workspace_id=caller.workspace_id,
            caller_principal_id=caller.principal_id,
        )
        assert resolved is not None
        assert resolved.kind == "issue"
        assert resolved.id == canonical_issue.id
        assert resolved.canonical_key == "CORE-1"
        assert resolved.is_alias is True

    # Canonical key resolution returns is_alias=False
    canonical_res = await resolver.resolve(
        session=session,
        kind="issue",
        ref="CORE-1",
        caller_workspace_id=caller.workspace_id,
        caller_principal_id=caller.principal_id,
    )
    assert canonical_res is not None
    assert canonical_res.id == canonical_issue.id
    assert canonical_res.is_alias is False


@pytest.mark.asyncio
async def test_api_resolve_headers_and_response(
    setup_alias_env: tuple[AsyncSession, PrincipalContext, Issue, IssueKeyAlias],
) -> None:
    """Verify legacy aliases resolve to canonical issue records and populate canonical headers."""
    session, caller, canonical_issue, _ = setup_alias_env
    from fastapi import Request, Response

    from kanban.api.v1.resolve import resolve_entity

    rec = await resolve_issue_ref(session, caller, "KANBA-123")
    assert rec.id == canonical_issue.id

    rec_linear = await resolve_issue_ref(session, caller, "ENG-42")
    assert rec_linear.id == canonical_issue.id

    # UUID resolution
    rec_uuid = await resolve_issue_ref(session, caller, str(canonical_issue.id))
    assert rec_uuid.id == canonical_issue.id

    # Canonical key resolution
    rec_canon = await resolve_issue_ref(session, caller, "CORE-1")
    assert rec_canon.id == canonical_issue.id

    # Invalid ref raises 404 ProblemException
    with pytest.raises(ProblemException):
        await resolve_issue_ref(session, caller, "DOES-NOT-EXIST-999")

    # FastAPI resolve_entity route
    req = Request(scope={"type": "http", "app": create_app(), "headers": []})
    resp = Response()
    api_res = await resolve_entity(
        request=req,
        response=resp,
        principal=caller,
        session=session,
        kind="issue",
        ref="KANBA-123",
    )
    assert api_res.id == canonical_issue.id
    assert api_res.canonical_key == "CORE-1"
    assert resp.headers.get("X-Kanban-Canonical-Key") == "CORE-1"


@pytest.mark.asyncio
async def test_cross_workspace_rls_isolation(
    setup_alias_env: tuple[AsyncSession, PrincipalContext, Issue, IssueKeyAlias],
) -> None:
    """Verify RLS prevents foreign workspace from discovering or resolving aliases."""
    session, _, canonical_issue, _ = setup_alias_env

    # Foreign workspace
    foreign_ws = uuid.uuid4()
    foreign_admin = uuid.uuid4()

    foreign_resolver = ResolutionService()
    with pytest.raises(ProblemException):
        await foreign_resolver.resolve(
            session=session,
            kind="issue",
            ref="KANBA-123",
            caller_workspace_id=foreign_ws,
            caller_principal_id=foreign_admin,
        )
