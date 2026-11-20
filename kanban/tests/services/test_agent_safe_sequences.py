# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Service tests for agent-safe sequence allocation and SEQUENCE_SKIPPED audit events."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from database.models.projects import Project
from database.models.workspace_settings import WorkspaceSettings
from database.session import RLSContext, RLSSessionFactory
from database.testing.pg_harness import build_dsn
from kanban.api.deps import PrincipalContext
from kanban.api.v1.schemas.issue_copy import IssueCopyRequest
from kanban.api.v1.schemas.issue_trees import IssueTreeNode
from kanban.api.v1.schemas.issues import IssueCreate
from kanban.issues.tree_service import create_issue_tree
from kanban.services.activity import (
    EVENT_CATEGORY,
    ActivityCategory,
    ActivityEventType,
    clear_activity_listeners,
)
from kanban.services.issue_copy import copy_issue
from kanban.services.issues import create_issue
from kanban.tests.security.helpers import (
    add_role_binding,
    create_project,
    create_user,
    create_workspace,
    rebuild_era,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


@pytest.fixture(autouse=True)
def _isolated_listeners() -> Iterator[None]:
    """Ensure clean listeners between tests."""
    clear_activity_listeners()
    yield
    clear_activity_listeners()


def test_activity_event_type_registration() -> None:
    """Verify SEQUENCE_SKIPPED is registered and mapped to SYSTEM category."""
    assert ActivityEventType.SEQUENCE_SKIPPED == "SEQUENCE_SKIPPED"
    assert EVENT_CATEGORY[ActivityEventType.SEQUENCE_SKIPPED] == ActivityCategory.SYSTEM


@pytest.mark.committed_db
async def test_create_issue_skips_loaded_and_records_activity(
    committed_db_session: AsyncSession,
    pg_worker_db: AsyncEngine,
) -> None:
    """Verify create_issue skips sequence 13 when enabled and emits SEQUENCE_SKIPPED."""
    ws_id = await create_workspace(committed_db_session)
    admin_id = await create_user(
        committed_db_session, ws_id, handle="@admin1", display_name="Admin 1"
    )
    proj_id = await create_project(
        committed_db_session, ws_id, identifier="SAFE", name="Safe Project", created_by_id=admin_id
    )

    # Enable skip_loaded_sequence_numbers and set counter to 12
    project = await committed_db_session.get(Project, proj_id)
    assert project is not None
    project.skip_loaded_sequence_numbers = True
    project.issue_seq_counter = 12

    # Also test workspace_settings default_skip_loaded_sequence_numbers ORM property
    ws_settings = await committed_db_session.get(WorkspaceSettings, ws_id)
    if ws_settings is not None:
        ws_settings.default_skip_loaded_sequence_numbers = True

    await add_role_binding(
        committed_db_session,
        ws_id,
        admin_id,
        role="PROJECT_ADMIN",
        scope_type="project",
        project_id=proj_id,
    )
    await rebuild_era(committed_db_session, ws_id)
    await committed_db_session.commit()

    db_name = pg_worker_db.url.database or "kanban_test"
    socket_dir = os.environ.get(
        "KB_TEST_PGSOCKET_DIR", os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")
    )
    app_engine = create_async_engine(
        build_dsn(database=db_name, host=socket_dir, user="kanban_app"),
        pool_size=5,
        max_overflow=0,
    )
    factory = RLSSessionFactory(app_engine)
    admin_ctx = PrincipalContext(
        principal_id=admin_id, workspace_id=ws_id, token_scopes=("session",)
    )
    admin_rls = RLSContext(principal_id=admin_id, workspace_id=ws_id, token_scopes=("session",))

    async with factory.session(admin_rls) as rls_sess:
        created, _ = await create_issue(
            rls_sess,
            admin_ctx,
            "SAFE",
            IssueCreate(summary="Test Issue 1", description_markdown="Body content"),
        )
        await rls_sess.commit()

    # Sequence 13 should have been skipped -> sequence 14 allocated
    assert created.key == "SAFE-14"

    # Verify SEQUENCE_SKIPPED event in activity_records
    async with factory.session(admin_rls) as rls_sess:
        act_row = (
            await rls_sess.execute(
                text(
                    "SELECT event_type, payload FROM activity_records "
                    "WHERE workspace_id = :ws AND event_type = 'SEQUENCE_SKIPPED'"
                ),
                {"ws": ws_id},
            )
        ).one()
        assert act_row[0] == "SEQUENCE_SKIPPED"
        payload = act_row[1]
        assert payload["project_key"] == "SAFE"
        assert payload["skipped_sequences"] == [13]
        assert payload["allocated_sequence"] == 14
        assert payload["reason"] == "agent_safe_sequence_numbering"

        # Verify hash chain integrity
        chain_res = (
            await rls_sess.execute(
                text("SELECT is_valid, checked_rows FROM verify_activity_chain(:ws)"),
                {"ws": ws_id},
            )
        ).one()
        assert chain_res[0] is True
        assert chain_res[1] >= 1

    await app_engine.dispose()


@pytest.mark.committed_db
async def test_create_issue_does_not_skip_when_disabled(
    committed_db_session: AsyncSession,
    pg_worker_db: AsyncEngine,
) -> None:
    """Verify create_issue does not skip sequence 13 when skip_loaded_sequence_numbers=False."""
    ws_id = await create_workspace(committed_db_session)
    admin_id = await create_user(
        committed_db_session, ws_id, handle="@admin2", display_name="Admin 2"
    )
    proj_id = await create_project(
        committed_db_session,
        ws_id,
        identifier="NOSKIP",
        name="No Skip Project",
        created_by_id=admin_id,
    )

    project = await committed_db_session.get(Project, proj_id)
    assert project is not None
    project.skip_loaded_sequence_numbers = False
    project.issue_seq_counter = 12

    await add_role_binding(
        committed_db_session,
        ws_id,
        admin_id,
        role="PROJECT_ADMIN",
        scope_type="project",
        project_id=proj_id,
    )
    await rebuild_era(committed_db_session, ws_id)
    await committed_db_session.commit()

    db_name = pg_worker_db.url.database or "kanban_test"
    socket_dir = os.environ.get(
        "KB_TEST_PGSOCKET_DIR", os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")
    )
    app_engine = create_async_engine(
        build_dsn(database=db_name, host=socket_dir, user="kanban_app"),
        pool_size=5,
        max_overflow=0,
    )
    factory = RLSSessionFactory(app_engine)
    admin_ctx = PrincipalContext(
        principal_id=admin_id, workspace_id=ws_id, token_scopes=("session",)
    )
    admin_rls = RLSContext(principal_id=admin_id, workspace_id=ws_id, token_scopes=("session",))

    async with factory.session(admin_rls) as rls_sess:
        created, _ = await create_issue(
            rls_sess,
            admin_ctx,
            "NOSKIP",
            IssueCreate(summary="Issue 13", description_markdown="Body"),
        )
        await rls_sess.commit()

    assert created.key == "NOSKIP-13"

    # Zero SEQUENCE_SKIPPED records
    async with factory.session(admin_rls) as rls_sess:
        cnt = (
            await rls_sess.execute(
                text(
                    "SELECT count(*) FROM activity_records "
                    "WHERE workspace_id = :ws AND event_type = 'SEQUENCE_SKIPPED'"
                ),
                {"ws": ws_id},
            )
        ).scalar_one()
        assert cnt == 0

        chain_res = (
            await rls_sess.execute(
                text("SELECT is_valid, checked_rows FROM verify_activity_chain(:ws)"),
                {"ws": ws_id},
            )
        ).one()
        assert chain_res[0] is True

    await app_engine.dispose()


@pytest.mark.committed_db
async def test_create_issue_tree_batch_sequence_and_skip_activity(
    committed_db_session: AsyncSession,
    pg_worker_db: AsyncEngine,
) -> None:
    """Verify create_issue_tree allocates batch once and emits SEQUENCE_SKIPPED."""
    ws_id = await create_workspace(committed_db_session)
    admin_id = await create_user(
        committed_db_session, ws_id, handle="@admin3", display_name="Admin 3"
    )
    proj_id = await create_project(
        committed_db_session, ws_id, identifier="TREE", name="Tree Project", created_by_id=admin_id
    )

    project = await committed_db_session.get(Project, proj_id)
    assert project is not None
    project.skip_loaded_sequence_numbers = True
    project.issue_seq_counter = 11

    await add_role_binding(
        committed_db_session,
        ws_id,
        admin_id,
        role="PROJECT_ADMIN",
        scope_type="project",
        project_id=proj_id,
    )
    await rebuild_era(committed_db_session, ws_id)
    await committed_db_session.commit()

    db_name = pg_worker_db.url.database or "kanban_test"
    socket_dir = os.environ.get(
        "KB_TEST_PGSOCKET_DIR", os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")
    )
    app_engine = create_async_engine(
        build_dsn(database=db_name, host=socket_dir, user="kanban_app"),
        pool_size=5,
        max_overflow=0,
    )
    factory = RLSSessionFactory(app_engine)
    admin_ctx = PrincipalContext(
        principal_id=admin_id, workspace_id=ws_id, token_scopes=("session",)
    )
    admin_rls = RLSContext(principal_id=admin_id, workspace_id=ws_id, token_scopes=("session",))

    # Tree with 3 nodes: root + 2 children
    # Counter starts at 11:
    # 3 items needed -> candidate 12 (ok), 13 (SKIPPED), 14 (ok), 15 (ok)
    tree = IssueTreeNode(
        summary="Root Issue",
        children=[
            IssueTreeNode(summary="Child Issue 1"),
            IssueTreeNode(summary="Child Issue 2"),
        ],
    )

    async with factory.session(admin_rls) as rls_sess:
        tree_res = await create_issue_tree(rls_sess, admin_ctx, "TREE", tree)
        await rls_sess.commit()

    assert tree_res.root.key == "TREE-12"
    assert len(tree_res.children) == 2
    assert tree_res.children[0].key == "TREE-14"
    assert tree_res.children[1].key == "TREE-15"

    async with factory.session(admin_rls) as rls_sess:
        act_rows = (
            await rls_sess.execute(
                text(
                    "SELECT event_type, payload FROM activity_records "
                    "WHERE workspace_id = :ws AND event_type = 'SEQUENCE_SKIPPED'"
                ),
                {"ws": ws_id},
            )
        ).all()
        # Exactly ONE SEQUENCE_SKIPPED event emitted for the batch
        assert len(act_rows) == 1
        payload = act_rows[0][1]
        assert payload["project_key"] == "TREE"
        assert payload["skipped_sequences"] == [13]
        assert payload["allocated_sequence"] == 12
        assert payload["reason"] == "agent_safe_sequence_numbering"

        chain_res = (
            await rls_sess.execute(
                text("SELECT is_valid, checked_rows FROM verify_activity_chain(:ws)"),
                {"ws": ws_id},
            )
        ).one()
        assert chain_res[0] is True

    await app_engine.dispose()


@pytest.mark.committed_db
async def test_copy_issue_batch_sequence_and_skip_activity(
    committed_db_session: AsyncSession,
    pg_worker_db: AsyncEngine,
) -> None:
    """Verify copy_issue allocates batch once and emits SEQUENCE_SKIPPED."""
    ws_id = await create_workspace(committed_db_session)
    admin_id = await create_user(
        committed_db_session, ws_id, handle="@admin4", display_name="Admin 4"
    )
    proj_id = await create_project(
        committed_db_session, ws_id, identifier="COPYP", name="Copy Project", created_by_id=admin_id
    )

    project = await committed_db_session.get(Project, proj_id)
    assert project is not None
    # Start counter at 66 to create source issues 67 and 68
    project.skip_loaded_sequence_numbers = False
    project.issue_seq_counter = 66

    await add_role_binding(
        committed_db_session,
        ws_id,
        admin_id,
        role="PROJECT_ADMIN",
        scope_type="project",
        project_id=proj_id,
    )
    await rebuild_era(committed_db_session, ws_id)
    await committed_db_session.commit()

    db_name = pg_worker_db.url.database or "kanban_test"
    socket_dir = os.environ.get(
        "KB_TEST_PGSOCKET_DIR", os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")
    )
    app_engine = create_async_engine(
        build_dsn(database=db_name, host=socket_dir, user="kanban_app"),
        pool_size=5,
        max_overflow=0,
    )
    factory = RLSSessionFactory(app_engine)
    admin_ctx = PrincipalContext(
        principal_id=admin_id, workspace_id=ws_id, token_scopes=("session",)
    )
    admin_rls = RLSContext(principal_id=admin_id, workspace_id=ws_id, token_scopes=("session",))

    # Create parent issue (67) and child issue (68)
    async with factory.session(admin_rls) as rls_sess:
        parent_created, _ = await create_issue(
            rls_sess,
            admin_ctx,
            "COPYP",
            IssueCreate(summary="Parent to Copy", description_markdown="Parent body"),
        )
        child_created, _ = await create_issue(
            rls_sess,
            admin_ctx,
            "COPYP",
            IssueCreate(
                summary="Child to Copy",
                description_markdown="Child body",
                parent=parent_created.key,
            ),
        )
        await rls_sess.commit()

    assert parent_created.key == "COPYP-67"
    assert child_created.key == "COPYP-68"

    # Now enable skip_loaded_sequence_numbers on project (counter is currently 68)
    async with committed_db_session.begin():
        p = await committed_db_session.get(Project, proj_id)
        assert p is not None
        p.skip_loaded_sequence_numbers = True

    async with factory.session(admin_rls) as rls_sess:
        copy_res, canonical_key = await copy_issue(
            rls_sess,
            admin_ctx,
            parent_created.key,
            IssueCopyRequest(include_sub_issues=True),
        )
        await rls_sess.commit()

    # 69 was skipped, so top copy is 70, sub issue copy is 71
    assert canonical_key == "COPYP-70"
    assert copy_res.issue.key == "COPYP-70"
    assert len(copy_res.copied_sub_issues) == 1
    assert copy_res.copied_sub_issues[0].copy_key == "COPYP-71"

    async with factory.session(admin_rls) as rls_sess:
        act_rows = (
            await rls_sess.execute(
                text(
                    "SELECT event_type, payload FROM activity_records "
                    "WHERE workspace_id = :ws AND event_type = 'SEQUENCE_SKIPPED'"
                ),
                {"ws": ws_id},
            )
        ).all()
        # Exactly ONE SEQUENCE_SKIPPED event emitted
        assert len(act_rows) == 1
        payload = act_rows[0][1]
        assert payload["project_key"] == "COPYP"
        assert payload["skipped_sequences"] == [69]
        assert payload["allocated_sequence"] == 70
        assert payload["reason"] == "agent_safe_sequence_numbering"

        chain_res = (
            await rls_sess.execute(
                text("SELECT is_valid, checked_rows FROM verify_activity_chain(:ws)"),
                {"ws": ws_id},
            )
        ).one()
        assert chain_res[0] is True

    await app_engine.dispose()
