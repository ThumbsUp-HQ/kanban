"""Unit tests for issue key and reference resolution (S7.2 8a, S3.4)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from database.session import RLSContext, RLSSessionFactory
from database.testing.pg_harness import build_dsn
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.api.v1.schemas.issues import IssueCreate
from kanban.services.issue_keys import resolve_issue_ref
from kanban.services.issues import create_issue
from kanban.tests.security.helpers import (
    add_role_binding,
    create_project,
    create_user,
    create_workspace,
    rebuild_era,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

pytestmark = pytest.mark.committed_db


async def test_resolve_issue_ref_by_key_and_uuid(  # noqa: PLR0915
    committed_db_session: AsyncSession,
    pg_worker_db: AsyncEngine,
) -> None:
    """Verify resolve_issue_ref resolves valid issue keys and UUIDs under RLS."""
    session = committed_db_session
    ws_id = await create_workspace(session, name="Key Resolution WS")
    admin_id = await create_user(session, ws_id, handle="@admin", display_name="Admin")
    viewer_id = await create_user(session, ws_id, handle="@viewer", display_name="Viewer")

    await add_role_binding(session, ws_id, admin_id, role="WORKSPACE_ADMIN", scope_type="workspace")
    await add_role_binding(
        session, ws_id, viewer_id, role="WORKSPACE_MEMBER", scope_type="workspace"
    )
    await session.commit()

    proj_id = await create_project(
        session, ws_id, identifier="KEYTEST", name="Key Test", created_by_id=admin_id
    )
    await add_role_binding(
        session, ws_id, admin_id, role="PROJECT_ADMIN", scope_type="project", project_id=proj_id
    )
    await add_role_binding(
        session, ws_id, viewer_id, role="VIEWER", scope_type="project", project_id=proj_id
    )
    await rebuild_era(session, ws_id)
    await session.commit()

    db_name = pg_worker_db.url.database or "kanban_test"
    socket_dir = "/tmp/kb-pgsock-23"

    app_engine = create_async_engine(
        build_dsn(database=db_name, host=socket_dir, user="kanban_app"),
        pool_size=5,
        max_overflow=0,
    )
    factory = RLSSessionFactory(app_engine)

    admin_ctx = PrincipalContext(
        principal_id=admin_id, workspace_id=ws_id, token_scopes=("session",)
    )
    viewer_ctx = PrincipalContext(
        principal_id=viewer_id, workspace_id=ws_id, token_scopes=("session",)
    )

    admin_rls = RLSContext(principal_id=admin_id, workspace_id=ws_id, token_scopes=("session",))
    viewer_rls = RLSContext(principal_id=viewer_id, workspace_id=ws_id, token_scopes=("session",))

    # Create an issue
    async with factory.session(admin_rls) as rls_sess:
        created, _ = await create_issue(
            rls_sess,
            admin_ctx,
            "KEYTEST",
            IssueCreate(summary="Initial Issue", description_markdown="Body content"),
        )
        await rls_sess.commit()

    issue_id = created.id
    issue_key = created.key
    assert issue_key == "KEYTEST-1"

    # Resolve by key as viewer
    async with factory.session(viewer_rls) as rls_sess:
        resolved_by_key = await resolve_issue_ref(rls_sess, viewer_ctx, "KEYTEST-1")
        assert resolved_by_key.id == issue_id
        assert resolved_by_key.sequence_id == 1

        resolved_by_uuid = await resolve_issue_ref(rls_sess, viewer_ctx, str(issue_id))
        assert resolved_by_uuid.id == issue_id

        # Non-existent key
        with pytest.raises(ProblemException) as exc_info:
            await resolve_issue_ref(rls_sess, viewer_ctx, "KEYTEST-999")
        assert exc_info.value.status == 404

        # Non-existent UUID
        with pytest.raises(ProblemException) as exc_info:
            await resolve_issue_ref(rls_sess, viewer_ctx, str(uuid.uuid4()))
        assert exc_info.value.status == 404

        # Malformed key
        with pytest.raises(ProblemException) as exc_info:
            await resolve_issue_ref(rls_sess, viewer_ctx, "not-a-valid-key")
        assert exc_info.value.status == 404

    # Create a user in another workspace
    other_ws_id = await create_workspace(session, name="Other WS")
    other_user_id = await create_user(
        session, other_ws_id, handle="@outsider", display_name="Outsider"
    )
    await add_role_binding(
        session, other_ws_id, other_user_id, role="WORKSPACE_MEMBER", scope_type="workspace"
    )
    await session.commit()
    outsider_ctx = PrincipalContext(
        principal_id=other_user_id, workspace_id=other_ws_id, token_scopes=("session",)
    )
    outsider_rls = RLSContext(
        principal_id=other_user_id, workspace_id=other_ws_id, token_scopes=("session",)
    )

    async with factory.session(outsider_rls) as rls_sess:
        with pytest.raises(ProblemException) as exc_info:
            await resolve_issue_ref(rls_sess, outsider_ctx, "KEYTEST-1")
        assert exc_info.value.status == 404

    # Verify soft-deleted issue returns 404
    await session.execute(
        text("UPDATE objects SET deleted_at = clock_timestamp() WHERE id = :id"),
        {"id": issue_id},
    )
    await session.commit()

    async with factory.session(viewer_rls) as rls_sess:
        with pytest.raises(ProblemException) as exc_info:
            await resolve_issue_ref(rls_sess, viewer_ctx, "KEYTEST-1")
        assert exc_info.value.status == 404

    await app_engine.dispose()
