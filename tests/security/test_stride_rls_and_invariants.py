# ruff: noqa: PLR0915
"""STRIDE cross-cutting security regression suite: RLS catalog, invariants & anti-enumeration.

Spec S3.5 / KB-P6-03 Invariants:
1. Catalog RLS: 100% of public tenant tables and partitions have ENABLE + FORCE RLS.
   Role kanban_app has rolbypassrls = false and rolsuper = false.
2. Zero-Context Fail-Closed: SELECT as kanban_app with unset context returns 0 rows across
   all tenant tables.
3. No Stored Presentation State: 0 columns in information_schema.columns end in _html or _ast.
4. Architectural Boundary: mcp has 0 direct imports from database (verified via lint-imports).
5. Anti-Enumeration Discipline: Unreadable vs nonexistent UUIDs across /api/v1/issues, /docs,
   /pages, /stickies, /views return byte-identical RFC 7807 404 responses.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from database.models import (
    ProjectPriority,
    WorkflowState,
)
from database.session import RLSSessionFactory
from database.testing.pg_harness import build_dsn
from kanban.api.deps import PrincipalContext
from kanban.app import create_app
from kanban.tests.security.helpers import (
    add_role_binding,
    create_project,
    create_user,
    create_workspace,
    rebuild_era,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

CATALOG_RLS_QUERY = """
SELECT
    c.relname,
    c.relkind,
    c.relrowsecurity,
    c.relforcerowsecurity
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relkind IN ('r', 'p')
  AND c.relname NOT IN ('alembic_version', 'link_type_matrix')
ORDER BY c.relname;
"""

EXEMPT_CATALOG_TABLES = {"alembic_version", "link_type_matrix"}

# Tables isolated from kanban_app via security definer or grant boundaries
ISOLATED_TABLES = {
    "alembic_version",
    "link_type_matrix",
    "auth_provider_cards",
    "rate_limit_buckets",
    "local_admin_credentials",
    "sessions",
    "totp_factors",
    "recovery_codes",
    "webauthn_credentials",
    "webauthn_challenges",
    "oidc_auth_requests",
    "setup_claim_tokens",
    "user_identities",
    "identity_link_intents",
}


class _StubResolver:
    """Principal resolver returning a fixed PrincipalContext."""

    def __init__(self, principal: PrincipalContext) -> None:
        self.principal = principal

    async def resolve(self, request: Any) -> PrincipalContext | None:  # noqa: ANN401
        del request
        return self.principal


@pytest.mark.asyncio
async def test_stride_catalog_and_role_rls_invariants(db_session: AsyncSession) -> None:
    """Assert 100% of tenant tables have FORCE RLS and kanban_app cannot bypass RLS."""
    # 1. Catalog RLS verification
    result = await db_session.execute(text(CATALOG_RLS_QUERY))
    rows = result.mappings().all()

    assert len(rows) >= 25, f"Expected at least 25 tenant tables/partitions, found {len(rows)}"

    unprotected = [
        r["relname"] for r in rows if not r["relrowsecurity"] or not r["relforcerowsecurity"]
    ]
    assert len(unprotected) == 0, (
        f"Found {len(unprotected)} tenant tables/partitions missing FORCE RLS: {unprotected}"
    )

    # 2. Check exempt tables
    exempt_res = await db_session.execute(
        text(
            "SELECT c.relname FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname IN ('alembic_version', 'link_type_matrix')"
        )
    )
    found_exempt = {r[0] for r in exempt_res.all()}
    assert found_exempt == EXEMPT_CATALOG_TABLES

    # 3. Check role privileges for kanban_app
    role_res = await db_session.execute(
        text("SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'kanban_app'")
    )
    role_row = role_res.mappings().first()
    assert role_row is not None, "Role kanban_app not found in pg_roles"
    assert not role_row["rolsuper"], "Security violation: kanban_app must NOT have rolsuper"
    assert not role_row["rolbypassrls"], "Security violation: kanban_app must NOT have rolbypassrls"


@pytest.mark.asyncio
async def test_stride_unset_context_zero_rows_across_all_tenant_tables(
    db_session: AsyncSession,
) -> None:
    """Assert SELECT as kanban_app with unset context returns 0 rows across every tenant table."""
    # Seed a workspace and project so tenant tables contain rows
    ws_id = await create_workspace(db_session, "stride-zero-ctx")
    u_id = await create_user(db_session, ws_id, handle="zeroctx", display_name="Zero Context User")
    await add_role_binding(
        db_session,
        ws_id,
        u_id,
        role="WORKSPACE_ADMIN",
        scope_type="workspace",
    )
    await create_project(db_session, ws_id, identifier="ZCTX", name="Zero Ctx Project")
    await rebuild_era(db_session, ws_id)
    await db_session.flush()

    # Query all public tables except exempt catalog and security-definer isolated tables
    tbl_rows = await db_session.execute(
        text(
            "SELECT c.relname FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') "
            "  AND c.relname NOT IN ("
            "    'alembic_version', 'link_type_matrix', 'auth_provider_cards', "
            "    'rate_limit_buckets', 'local_admin_credentials', 'sessions', "
            "    'totp_factors', 'recovery_codes', 'webauthn_credentials', "
            "    'webauthn_challenges', 'oidc_auth_requests', 'setup_claim_tokens', "
            "    'user_identities', 'identity_link_intents'"
            "  ) "
            "ORDER BY c.relname"
        )
    )
    tables_to_check = [r[0] for r in tbl_rows.all()]
    assert len(tables_to_check) >= 20

    # 1. Switch to least-privilege kanban_app with UNSET session context
    await db_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))

    for tbl in tables_to_check:
        cnt = await db_session.scalar(text(f"SELECT count(*) FROM {tbl}"))  # noqa: S608
        assert cnt == 0, f"Expected 0 rows for kanban_app on {tbl} with unset context, got {cnt}"

    # 2. Test with explicitly empty string context
    await db_session.execute(
        text(
            "SELECT set_config('app.principal_id', '', true), "
            "set_config('app.workspace_id', '', true)"
        )
    )
    for tbl in tables_to_check:
        cnt = await db_session.scalar(text(f"SELECT count(*) FROM {tbl}"))  # noqa: S608
        assert cnt == 0, f"Expected 0 rows for kanban_app on {tbl} with empty context, got {cnt}"


@pytest.mark.asyncio
async def test_stride_zero_stored_html_and_ast_columns(db_session: AsyncSession) -> None:
    """Assert zero columns ending in _html or _ast exist in public schema (Spec S1.2)."""
    result = await db_session.execute(
        text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' "
            "  AND (column_name LIKE '%_html' OR column_name LIKE '%_ast') "
            "ORDER BY table_name, column_name"
        )
    )
    columns = result.all()
    assert len(columns) == 0, f"Forbidden rendered HTML or AST columns found in schema: {columns}"


def test_stride_mcp_zero_database_imports_boundary() -> None:
    """Assert mcp module has zero direct imports from database via lint-imports."""
    lint_bin = shutil.which("lint-imports") or "lint-imports"
    result = subprocess.run(
        [lint_bin],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"lint-imports failed with code {result.returncode}:\n{result.stdout}\n{result.stderr}"
    )
    assert "Contracts: 2 kept, 0 broken" in result.stdout or "KEPT" in result.stdout


@pytest.mark.committed_db
@pytest.mark.asyncio
async def test_stride_anti_enumeration_byte_identical_404(
    request: pytest.FixtureRequest,
    committed_db_session: AsyncSession,
    pg_worker_db: AsyncEngine,
) -> None:
    """Assert unreadable vs nonexistent UUIDs return byte-identical 404 RFC 7807 responses.

    Spec S3.4: All object read operations return 404 NOT_FOUND when the object is unreadable
    under RLS or non-existent, eliminating enumeration and oracle side-channels.
    """
    # 1. Setup Workspace A with User A, Project A, Issue, Doc, Page, Sticky, View
    ws_a = await create_workspace(committed_db_session, "stride-enuma")
    user_a = await create_user(committed_db_session, ws_a, handle="usera", display_name="User A")
    await add_role_binding(
        committed_db_session,
        ws_a,
        user_a,
        role="WORKSPACE_ADMIN",
        scope_type="workspace",
    )
    proj_a = await create_project(
        committed_db_session, ws_a, identifier="ENUA", name="Enum Project A", created_by_id=user_a
    )

    # Issue
    seq_id = await committed_db_session.scalar(
        text("SELECT allocate_issue_sequence(:p_id)"), {"p_id": proj_a}
    )
    await committed_db_session.execute(
        text(
            "UPDATE projects SET issue_seq_counter = GREATEST(issue_seq_counter, :seq) "
            "WHERE id = :p_id"
        ),
        {"seq": seq_id, "p_id": proj_a},
    )
    state_res = await committed_db_session.execute(
        select(WorkflowState).where(
            WorkflowState.project_id == proj_a, WorkflowState.is_default.is_(True)
        )
    )
    state = state_res.scalar_one()
    prio_res = await committed_db_session.execute(
        select(ProjectPriority).where(
            ProjectPriority.project_id == proj_a, ProjectPriority.slug == "medium"
        )
    )
    prio = prio_res.scalar_one()

    issue_id = uuid.uuid4()
    await committed_db_session.execute(
        text(
            "SELECT register_object('issue'::object_kind, :ws, :proj, :ckey, 'Issue A', :cr, :id)"
        ),
        {"ws": ws_a, "proj": proj_a, "ckey": f"ENUA-{seq_id}", "cr": user_a, "id": issue_id},
    )
    await committed_db_session.execute(
        text(
            "INSERT INTO issues (id, object_type, workspace_id, project_id, sequence_id, "
            "summary, description_markdown, state_id, priority_id, created_by_id, "
            "original_created_by_id, ancestry_path, board_rank) "
            "VALUES (:id, 'issue', :ws, :proj, :seq, 'Issue A', 'Secret summary', "
            ":st, :pr, :cr, :cr, :anc, '0|hzzzzz:')"
        ),
        {
            "id": issue_id,
            "ws": ws_a,
            "proj": proj_a,
            "seq": seq_id,
            "st": state.id,
            "pr": prio.id,
            "cr": user_a,
            "anc": str(seq_id),
        },
    )

    # Doc
    doc_id = uuid.uuid4()
    await committed_db_session.execute(
        text("SELECT register_object('doc'::object_kind, :ws, :proj, :ckey, 'Doc A', :cr, :id)"),
        {"ws": ws_a, "proj": proj_a, "ckey": "docs/doc-a", "cr": user_a, "id": doc_id},
    )
    await committed_db_session.execute(
        text(
            "INSERT INTO docs (id, object_type, workspace_id, project_id, title, "
            "body_markdown, hierarchy_path) "
            "VALUES (:id, 'doc', :ws, :proj, 'Doc A', 'Secret doc body', 'top')"
        ),
        {"id": doc_id, "ws": ws_a, "proj": proj_a},
    )

    # Page
    page_id = uuid.uuid4()
    await committed_db_session.execute(
        text("SELECT register_object('page'::object_kind, :ws, :proj, :ckey, 'Page A', :cr, :id)"),
        {"ws": ws_a, "proj": proj_a, "ckey": "docs/doc-a/page-a", "cr": user_a, "id": page_id},
    )
    await committed_db_session.execute(
        text(
            "INSERT INTO pages (id, workspace_id, doc_id, title, body_markdown) "
            "VALUES (:id, :ws, :doc, 'Page A', 'Secret page body')"
        ),
        {"id": page_id, "ws": ws_a, "doc": doc_id},
    )

    # Sticky
    sticky_id = uuid.uuid4()
    await committed_db_session.execute(
        text(
            "SELECT register_object('sticky'::object_kind, :ws, :proj, :ckey, 'Sticky A', :cr, :id)"
        ),
        {
            "ws": ws_a,
            "proj": proj_a,
            "ckey": f"ENUA/stickies/{sticky_id}",
            "cr": user_a,
            "id": sticky_id,
        },
    )
    await committed_db_session.execute(
        text(
            "INSERT INTO stickies (id, object_type, workspace_id, project_id, "
            "body_markdown, color_token) "
            "VALUES (:id, 'sticky', :ws, :proj, 'Secret sticky note', 'amber')"
        ),
        {"id": sticky_id, "ws": ws_a, "proj": proj_a},
    )

    # View
    view_id = uuid.uuid4()
    await committed_db_session.execute(
        text("SELECT register_object('view'::object_kind, :ws, :proj, :ckey, 'View A', :cr, :id)"),
        {"ws": ws_a, "proj": proj_a, "ckey": f"ENUA/views/{view_id}", "cr": user_a, "id": view_id},
    )
    await committed_db_session.execute(
        text(
            "INSERT INTO views (id, object_type, workspace_id, project_id, "
            "owner_principal_id, visibility, name, layout, filters_json, "
            "display_props_json, wip_limits_json, sort_rank) "
            "VALUES (:id, 'view', :ws, :proj, :owner, 'project', 'View A', 'board', "
            "'{}'::jsonb, '{}'::jsonb, '{}'::jsonb, 'a0')"
        ),
        {"id": view_id, "ws": ws_a, "proj": proj_a, "owner": user_a},
    )

    await rebuild_era(committed_db_session, ws_a)
    await committed_db_session.commit()

    # 2. Setup Workspace B with User B (unauthorized for Workspace A objects)
    ws_b = await create_workspace(committed_db_session, "stride-enumb")
    user_b = await create_user(committed_db_session, ws_b, handle="userb", display_name="User B")
    await add_role_binding(
        committed_db_session,
        ws_b,
        user_b,
        role="WORKSPACE_ADMIN",
        scope_type="workspace",
    )
    await rebuild_era(committed_db_session, ws_b)
    await committed_db_session.commit()

    # 3. Create app and test client under kanban_app role
    worker_id = getattr(request.config, "workerinput", {}).get("workerid", "master")
    db_name = pg_worker_db.url.database or f"kanban_test_{worker_id}"
    socket_dir = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")
    app_dsn = build_dsn(database=db_name, host=socket_dir, user="kanban_app")

    app_engine = create_async_engine(app_dsn, pool_size=5, max_overflow=0)
    try:
        factory = RLSSessionFactory(app_engine)
        user_b_principal = PrincipalContext(principal_id=user_b, workspace_id=ws_b)
        resolver = _StubResolver(user_b_principal)

        app = create_app()
        app.state.session_factory = factory
        app.state.principal_resolver = resolver

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            endpoints_to_test = [
                ("issue", f"/api/v1/issues/{issue_id}", f"/api/v1/issues/{uuid.uuid4()}"),
                ("doc", f"/api/v1/docs/{doc_id}", f"/api/v1/docs/{uuid.uuid4()}"),
                ("page", f"/api/v1/pages/{page_id}", f"/api/v1/pages/{uuid.uuid4()}"),
                ("sticky", f"/api/v1/stickies/{sticky_id}", f"/api/v1/stickies/{uuid.uuid4()}"),
                ("view", f"/api/v1/views/{view_id}", f"/api/v1/views/{uuid.uuid4()}"),
            ]

            for entity_kind, unreadable_url, nonexistent_url in endpoints_to_test:
                res_unreadable = await client.get(unreadable_url)
                res_nonexistent = await client.get(nonexistent_url)

                assert res_unreadable.status_code == 404, (
                    f"{entity_kind}: expected 404 for unreadable, "
                    f"got {res_unreadable.status_code}: {res_unreadable.text}"
                )
                assert res_nonexistent.status_code == 404, (
                    f"{entity_kind}: expected 404 for nonexistent, "
                    f"got {res_nonexistent.status_code}: {res_nonexistent.text}"
                )

                # RFC 7807 problem structure
                data_unreadable = res_unreadable.json()
                data_nonexistent = res_nonexistent.json()

                assert "request_id" in data_unreadable, (
                    f"{entity_kind}: missing request_id in unreadable"
                )
                assert "request_id" in data_nonexistent, (
                    f"{entity_kind}: missing request_id in nonexistent"
                )

                clean_unreadable = {k: v for k, v in data_unreadable.items() if k != "request_id"}
                clean_nonexistent = {k: v for k, v in data_nonexistent.items() if k != "request_id"}

                # Assert byte-identical body structure
                assert clean_unreadable == clean_nonexistent, (
                    f"{entity_kind}: body mismatch between unreadable and nonexistent:\n"
                    f"Unreadable: {clean_unreadable}\nNonexistent: {clean_nonexistent}"
                )

                # Assert standard ProblemException layout
                assert clean_unreadable == {
                    "type": "urn:kanban:problem:NOT_FOUND",
                    "title": "Not Found",
                    "status": 404,
                    "code": "NOT_FOUND",
                }

                # Compare headers excluding variable transport headers
                headers_unreadable = {
                    k.lower(): v
                    for k, v in res_unreadable.headers.items()
                    if k.lower() not in ("x-request-id", "date", "etag")
                }
                headers_nonexistent = {
                    k.lower(): v
                    for k, v in res_nonexistent.headers.items()
                    if k.lower() not in ("x-request-id", "date", "etag")
                }
                assert headers_unreadable == headers_nonexistent, (
                    f"{entity_kind}: header mismatch between unreadable and nonexistent:\n"
                    f"Unreadable: {headers_unreadable}\nNonexistent: {headers_nonexistent}"
                )
    finally:
        await app_engine.dispose()
