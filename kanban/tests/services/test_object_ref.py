"""Unit tests for object reference resolution service.

Traceability: Spec S7.2 8m, S3.4.
"""

from __future__ import annotations

import os
import uuid  # noqa: TC003
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from database.models import ObjectKind
from database.session import RLSContext, RLSSessionFactory
from database.testing.pg_harness import build_dsn
from kanban.api.deps import PrincipalContext
from kanban.api.v1.schemas.issues import IssueCreate
from kanban.services.issues import create_issue
from kanban.services.object_ref import MAX_OBJECT_REF_LENGTH, resolve_object_ref
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


async def _setup_harness(
    session: AsyncSession,
    pg_worker_db: AsyncEngine,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, RLSSessionFactory]:
    """Create workspace, users, projects, and RLSSessionFactory for test cases."""
    ws_id = await create_workspace(session, name="Obj Ref Resolution WS")
    admin_id = await create_user(session, ws_id, handle="@admin", display_name="Admin")
    viewer_id = await create_user(session, ws_id, handle="@viewer", display_name="Viewer")

    await add_role_binding(session, ws_id, admin_id, role="WORKSPACE_ADMIN", scope_type="workspace")
    await add_role_binding(
        session, ws_id, viewer_id, role="WORKSPACE_GUEST", scope_type="workspace"
    )

    pub_proj_id = await create_project(
        session, ws_id, identifier="PUB", name="Public Project", created_by_id=admin_id
    )
    await add_role_binding(
        session, ws_id, admin_id, role="PROJECT_ADMIN", scope_type="project", project_id=pub_proj_id
    )
    await add_role_binding(
        session, ws_id, viewer_id, role="VIEWER", scope_type="project", project_id=pub_proj_id
    )

    sec_proj_id = await create_project(
        session, ws_id, identifier="SEC", name="Secret Project", created_by_id=admin_id
    )
    await add_role_binding(
        session, ws_id, admin_id, role="PROJECT_ADMIN", scope_type="project", project_id=sec_proj_id
    )

    await rebuild_era(session, ws_id)
    await session.commit()

    db_name = pg_worker_db.url.database or "kanban_test"
    socket_dir = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")
    app_engine = create_async_engine(
        build_dsn(database=db_name, host=socket_dir, user="kanban_app"),
        pool_size=5,
        max_overflow=0,
    )
    factory = RLSSessionFactory(app_engine)
    return ws_id, admin_id, viewer_id, pub_proj_id, sec_proj_id, factory


async def test_resolve_object_ref_uuid_and_keys(
    committed_db_session: AsyncSession,
    pg_worker_db: AsyncEngine,
) -> None:
    """Verify resolve_object_ref resolves UUIDs, issue keys, and project keys."""
    ws_id, admin_id, _, _pub_proj_id, _sec_proj_id, factory = await _setup_harness(
        committed_db_session, pg_worker_db
    )
    admin_ctx = PrincipalContext(
        principal_id=admin_id, workspace_id=ws_id, token_scopes=("session",)
    )
    admin_rls = RLSContext(principal_id=admin_id, workspace_id=ws_id, token_scopes=("session",))

    async with factory.session(admin_rls) as rls_sess:
        pub_issue, _ = await create_issue(
            rls_sess,
            admin_ctx,
            "PUB",
            IssueCreate(summary="Public Issue 1", description_markdown="Public body"),
        )
        sec_issue, _ = await create_issue(
            rls_sess,
            admin_ctx,
            "SEC",
            IssueCreate(summary="Secret Issue 1", description_markdown="Secret body"),
        )
        await rls_sess.commit()

    pub_issue_id = pub_issue.id
    sec_issue_id = sec_issue.id

    async with factory.session(admin_rls) as rls_sess:
        # Resolve by UUID
        res = await resolve_object_ref(rls_sess, str(pub_issue_id))
        assert res is not None
        assert res.id == pub_issue_id
        assert res.canonical_key == "PUB-1"

        # Resolve by UUID with matching and non-matching expected_type
        assert (
            await resolve_object_ref(rls_sess, str(pub_issue_id), expected_type=ObjectKind.ISSUE)
        ) is not None
        assert (
            await resolve_object_ref(rls_sess, str(pub_issue_id), expected_type=ObjectKind.PROJECT)
        ) is None

        # Resolve by issue key
        assert (await resolve_object_ref(rls_sess, "PUB-1")) is not None
        assert (
            await resolve_object_ref(rls_sess, "PUB-1", expected_type=ObjectKind.ISSUE)
        ) is not None
        assert (
            await resolve_object_ref(rls_sess, "PUB-1", expected_type=ObjectKind.PROJECT)
        ) is None

        # Resolve by project identifier
        assert (await resolve_object_ref(rls_sess, "PUB")) is not None
        assert (
            await resolve_object_ref(rls_sess, "PUB", expected_type=ObjectKind.PROJECT)
        ) is not None
        assert (await resolve_object_ref(rls_sess, "PUB", expected_type=ObjectKind.ISSUE)) is None

        # Admin resolves secret entities
        assert await resolve_object_ref(rls_sess, "SEC-1") is not None
        assert await resolve_object_ref(rls_sess, "SEC") is not None
        assert await resolve_object_ref(rls_sess, str(sec_issue_id)) is not None

    await factory.engine.dispose()


async def test_resolve_object_ref_rls_isolation(
    committed_db_session: AsyncSession,
    pg_worker_db: AsyncEngine,
) -> None:
    """Verify viewer cannot resolve unreadable secret entities through RLS."""
    ws_id, admin_id, viewer_id, _, _, factory = await _setup_harness(
        committed_db_session, pg_worker_db
    )
    admin_ctx = PrincipalContext(
        principal_id=admin_id, workspace_id=ws_id, token_scopes=("session",)
    )
    admin_rls = RLSContext(principal_id=admin_id, workspace_id=ws_id, token_scopes=("session",))
    viewer_rls = RLSContext(principal_id=viewer_id, workspace_id=ws_id, token_scopes=("session",))

    async with factory.session(admin_rls) as rls_sess:
        pub_issue, _ = await create_issue(
            rls_sess,
            admin_ctx,
            "PUB",
            IssueCreate(summary="Public Issue", description_markdown="Public body"),
        )
        sec_issue, _ = await create_issue(
            rls_sess,
            admin_ctx,
            "SEC",
            IssueCreate(summary="Secret Issue", description_markdown="Secret body"),
        )
        await rls_sess.commit()

    async with factory.session(viewer_rls) as rls_sess:
        assert await resolve_object_ref(rls_sess, "PUB-1") is not None
        assert await resolve_object_ref(rls_sess, "PUB") is not None
        assert await resolve_object_ref(rls_sess, str(pub_issue.id)) is not None

        # Secret entities return None identically to non-existent
        assert await resolve_object_ref(rls_sess, "SEC-1") is None
        assert await resolve_object_ref(rls_sess, "SEC") is None
        assert await resolve_object_ref(rls_sess, str(sec_issue.id)) is None

        # Non-existent entities return None
        assert await resolve_object_ref(rls_sess, "PUB-999") is None
        assert await resolve_object_ref(rls_sess, "NONEXIST") is None

    await factory.engine.dispose()


async def test_resolve_object_ref_boundaries_and_soft_delete(
    committed_db_session: AsyncSession,
    pg_worker_db: AsyncEngine,
) -> None:
    """Verify boundaries (length, whitespace, malformed) and soft-deleted object exclusion."""
    ws_id, admin_id, _, _, _, factory = await _setup_harness(committed_db_session, pg_worker_db)
    admin_ctx = PrincipalContext(
        principal_id=admin_id, workspace_id=ws_id, token_scopes=("session",)
    )
    admin_rls = RLSContext(principal_id=admin_id, workspace_id=ws_id, token_scopes=("session",))

    async with factory.session(admin_rls) as rls_sess:
        pub_issue, _ = await create_issue(
            rls_sess,
            admin_ctx,
            "PUB",
            IssueCreate(summary="Public Issue", description_markdown="Public body"),
        )
        await rls_sess.commit()

    async with factory.session(admin_rls) as rls_sess:
        assert await resolve_object_ref(rls_sess, "") is None
        assert await resolve_object_ref(rls_sess, "   ") is None
        assert await resolve_object_ref(rls_sess, "A" * (MAX_OBJECT_REF_LENGTH + 1)) is None
        assert await resolve_object_ref(rls_sess, "unknown-key-1234") is None
        assert (
            await resolve_object_ref(rls_sess, "unknown-key-1234", expected_type=ObjectKind.DOC)
        ) is None

    # Soft deletion: soft deleted objects return None
    await committed_db_session.execute(
        text("UPDATE objects SET deleted_at = clock_timestamp() WHERE id = :id"),
        {"id": pub_issue.id},
    )
    await committed_db_session.commit()

    async with factory.session(admin_rls) as rls_sess:
        assert await resolve_object_ref(rls_sess, "PUB-1") is None
        assert await resolve_object_ref(rls_sess, str(pub_issue.id)) is None

    await factory.engine.dispose()
