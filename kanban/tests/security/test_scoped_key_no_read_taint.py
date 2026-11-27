# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501
"""Security and integration tests for explicit CredentialBoundary without read-taint (KAN-535).

Proves:
  (a) A workspace-scoped API key (scope_tier='workspace') can read issues, docs, stickies,
      and search in a restricted narrower-ACL project (TEST) and immediately write
      (create_issue, patch_issue, create_comment, begin_work, transition) to a broader-ACL
      project (KAN) with 200/201 and zero taint errors.
  (b) A project-scoped API key (scope_tier='project', project_id=KAN) cannot read, list,
      search, resolve, or mutate sibling project TEST (enforced at both REST API and PostgreSQL
      FORCE ROW LEVEL SECURITY via deps.py -> RLSContext(credential_boundary=...)).
"""

from __future__ import annotations

import os
import uuid
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from database.rls.context import RLSContext, bind_rls_context
from database.session import RLSSessionFactory
from database.testing.pg_harness import build_dsn
from kanban.api.deps import PrincipalContext
from kanban.app import create_app
from kanban.auth.sessions.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    PRE_SESSION_ID,
    generate_csrf_token,
)
from kanban.security.boundary import CredentialBoundary
from kanban.security.service_auth import create_internal_service_auth_header
from kanban.tests.security.helpers import (
    add_role_binding,
    create_project,
    create_user,
    create_workspace,
    rebuild_era,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

pytestmark = pytest.mark.committed_db


class _McpGatewaySigningTransport(httpx.AsyncBaseTransport):
    """Wraps ASGITransport and signs requests bearing X-KB-Service-Principal: mcp-gateway."""

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        self._inner = inner

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.headers.get("x-kb-service-principal") == "mcp-gateway":
            request.headers["x-kb-internal-auth"] = create_internal_service_auth_header(
                principal="mcp-gateway",
                method=request.method,
                path=request.url.path,
                body_bytes=request.content,
            )
        return await self._inner.handle_async_request(request)


class _TestTokenResolver:
    """Resolves PrincipalContext by checking X-KB-Subject-Token header."""

    def __init__(
        self,
        default_principal: PrincipalContext,
        token_map: dict[str, PrincipalContext],
    ) -> None:
        self.default_principal = default_principal
        self.token_map = token_map

    async def resolve(self, request: Any) -> PrincipalContext | None:  # noqa: ANN401
        tok = request.headers.get("x-kb-subject-token")
        if tok and tok in self.token_map:
            return self.token_map[tok]
        return self.default_principal


async def _seed_issue(  # noqa: PLR0913, PLR0917
    session: AsyncSession,
    ws_id: uuid.UUID,
    proj_id: uuid.UUID,
    proj_key: str,
    seq: int,
    summary: str,
    description: str,
    creator_id: uuid.UUID,
) -> uuid.UUID:
    """Seed an issue row with object spine registration."""
    iss_id = uuid.uuid4()
    st = (
        await session.execute(
            text(
                "SELECT id FROM workflow_states WHERE project_id = :p ORDER BY sort_order ASC LIMIT 1"
            ),
            {"p": proj_id},
        )
    ).scalar_one()
    pri = (
        await session.execute(
            text(
                "SELECT id FROM project_priorities WHERE project_id = :p ORDER BY sort_order ASC LIMIT 1"
            ),
            {"p": proj_id},
        )
    ).scalar_one()

    await session.execute(
        text(
            "UPDATE projects SET issue_seq_counter = GREATEST(issue_seq_counter, :s) WHERE id = :p"
        ),
        {"p": proj_id, "s": seq},
    )
    await session.execute(
        text("SELECT register_object('issue'::object_kind, :ws, :proj, :key, :sum, :cr, :id)"),
        {
            "ws": ws_id,
            "proj": proj_id,
            "key": f"{proj_key}-{seq}",
            "sum": summary,
            "cr": creator_id,
            "id": iss_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO issues (id, object_type, workspace_id, project_id, sequence_id, summary, "
            "description_markdown, state_id, priority_id, created_by_id, original_created_by_id, "
            "board_rank, ancestry_path, provenance_tier) "
            "VALUES (:id, 'issue', :ws, :proj, :seq, :sum, :desc, :st, :pri, :cr, :cr, "
            "'0|s00001:', 'top', 'trusted_member')"
        ),
        {
            "id": iss_id,
            "ws": ws_id,
            "proj": proj_id,
            "seq": seq,
            "sum": summary,
            "desc": description,
            "st": st,
            "pri": pri,
            "cr": creator_id,
        },
    )
    return iss_id


async def _seed_doc(  # noqa: PLR0913, PLR0917
    session: AsyncSession,
    ws_id: uuid.UUID,
    proj_id: uuid.UUID,
    title: str,
    body: str,
    creator_id: uuid.UUID,
) -> uuid.UUID:
    """Seed a doc row with object spine registration."""
    doc_id = uuid.uuid4()
    await session.execute(
        text("SELECT register_object('doc'::object_kind, :ws, :proj, :key, :title, :cr, :id)"),
        {
            "ws": ws_id,
            "proj": proj_id,
            "key": f"DOC-{doc_id.hex[:6]}",
            "title": title,
            "cr": creator_id,
            "id": doc_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO docs (id, object_type, workspace_id, project_id, title, body_markdown, "
            "hierarchy_path, provenance_tier) "
            "VALUES (:id, 'doc', :ws, :proj, :title, :body, 'top', 'trusted_member')"
        ),
        {"id": doc_id, "ws": ws_id, "proj": proj_id, "title": title, "body": body},
    )
    return doc_id


async def _seed_sticky(
    session: AsyncSession,
    ws_id: uuid.UUID,
    proj_id: uuid.UUID,
    body: str,
    creator_id: uuid.UUID,
) -> uuid.UUID:
    """Seed a sticky note row with object spine registration."""
    sticky_id = uuid.uuid4()
    await session.execute(
        text("SELECT register_object('sticky'::object_kind, :ws, :proj, :key, 'Sticky', :cr, :id)"),
        {
            "ws": ws_id,
            "proj": proj_id,
            "key": f"STK-{sticky_id.hex[:6]}",
            "cr": creator_id,
            "id": sticky_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO stickies (id, object_type, workspace_id, project_id, body_markdown, "
            "color_token, provenance_tier) "
            "VALUES (:id, 'sticky', :ws, :proj, :body, 'amber', 'trusted_member')"
        ),
        {"id": sticky_id, "ws": ws_id, "proj": proj_id, "body": body},
    )
    return sticky_id


@pytest.fixture
async def scoped_key_env(
    committed_db_session: AsyncSession,
    pg_worker_db: AsyncEngine,
) -> AsyncIterator[dict[str, Any]]:
    """Set up clean-DB test environment with Project TEST (restricted) and Project KAN (broader)."""
    ws_id = await create_workspace(committed_db_session, name="Scoped Key Isolation Workspace")

    admin_id = await create_user(committed_db_session, ws_id, handle="@admin", display_name="Admin")
    await add_role_binding(
        committed_db_session, ws_id, admin_id, role="WORKSPACE_ADMIN", scope_type="workspace"
    )

    alice_id = await create_user(committed_db_session, ws_id, handle="@alice", display_name="Alice")

    # Project TEST: restricted project
    proj_test_id = await create_project(
        committed_db_session,
        ws_id,
        identifier="TEST",
        name="Project Test",
        created_by_id=admin_id,
    )
    # Project KAN: broader project
    proj_kan_id = await create_project(
        committed_db_session,
        ws_id,
        identifier="KAN",
        name="Project Kan",
        created_by_id=admin_id,
    )

    # Alice is PROJECT_ADMIN on both projects
    await add_role_binding(
        committed_db_session,
        ws_id,
        alice_id,
        role="PROJECT_ADMIN",
        scope_type="project",
        project_id=proj_test_id,
    )
    await add_role_binding(
        committed_db_session,
        ws_id,
        alice_id,
        role="PROJECT_ADMIN",
        scope_type="project",
        project_id=proj_kan_id,
    )

    await rebuild_era(committed_db_session, ws_id)
    await committed_db_session.commit()

    # Seed issues, doc, and sticky in TEST
    test_1_id = await _seed_issue(
        committed_db_session,
        ws_id,
        proj_test_id,
        "TEST",
        seq=1,
        summary="Restricted Architecture Spec",
        description="Confidential specification: CANARY-TEST-SECRET-1234",
        creator_id=alice_id,
    )
    test_doc_id = await _seed_doc(
        committed_db_session,
        ws_id,
        proj_test_id,
        title="Restricted Internal Doc",
        body="Secret details for project TEST.",
        creator_id=alice_id,
    )
    test_sticky_id = await _seed_sticky(
        committed_db_session,
        ws_id,
        proj_test_id,
        body="Quick secret note: TEST-STICKY-SECRET",
        creator_id=alice_id,
    )

    # Seed issue in KAN
    kan_1_id = await _seed_issue(
        committed_db_session,
        ws_id,
        proj_kan_id,
        "KAN",
        seq=1,
        summary="Public Roadmap Item",
        description="General public roadmap item.",
        creator_id=alice_id,
    )

    await committed_db_session.commit()

    # Define boundaries:
    # 1. Workspace-scoped boundary
    boundary_ws = CredentialBoundary(
        scope_tier="workspace",
        workspace_allowlist=frozenset({ws_id}),
        capability_mask=0xFF,
    )
    tok_ws = "kb_agt_ws_token_" + "w" * 32

    # 2. Project-scoped boundary restricted strictly to KAN
    boundary_kan = CredentialBoundary(
        scope_tier="project",
        workspace_allowlist=frozenset({ws_id}),
        project_allowlist=frozenset({proj_kan_id}),
        capability_mask=0xFF,
    )
    tok_proj_kan = "kb_agt_proj_token_" + "k" * 32

    token_map = {
        tok_ws: PrincipalContext(
            principal_id=alice_id,
            workspace_id=ws_id,
            token_scopes=("agent:read", "agent:write"),
            credential_boundary=boundary_ws,
        ),
        tok_proj_kan: PrincipalContext(
            principal_id=alice_id,
            workspace_id=ws_id,
            token_scopes=("agent:read", "agent:write"),
            credential_boundary=boundary_kan,
        ),
    }

    resolver = _TestTokenResolver(default_principal=token_map[tok_ws], token_map=token_map)

    db_name = pg_worker_db.url.database or "kanban_test"
    socket_dir = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")
    app_engine = create_async_engine(
        build_dsn(database=db_name, host=socket_dir, user="kanban_app"),
        poolclass=NullPool,
    )

    app = create_app()
    app.state.session_factory = RLSSessionFactory(app_engine)
    app.state.principal_resolver = resolver

    csrf_token = generate_csrf_token(PRE_SESSION_ID, b"\x00" * 32)
    transport = _McpGatewaySigningTransport(httpx.ASGITransport(app=app))
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={
            CSRF_HEADER_NAME: csrf_token,
        },
        cookies={CSRF_COOKIE_NAME: csrf_token},
    ) as client:
        yield {
            "client": client,
            "session": committed_db_session,
            "ws_id": ws_id,
            "proj_test_id": proj_test_id,
            "proj_kan_id": proj_kan_id,
            "test_1_id": test_1_id,
            "test_doc_id": test_doc_id,
            "test_sticky_id": test_sticky_id,
            "kan_1_id": kan_1_id,
            "tok_ws": tok_ws,
            "tok_proj_kan": tok_proj_kan,
            "alice_id": alice_id,
            "boundary_kan": boundary_kan,
        }
    await app_engine.dispose()


@pytest.mark.asyncio
async def test_workspace_scoped_key_can_read_restricted_and_write_broader_without_taint(
    scoped_key_env: dict[str, Any],
) -> None:
    """Case (a): A workspace-scoped API key can read in restricted TEST and write to KAN without taint errors."""
    client: httpx.AsyncClient = scoped_key_env["client"]
    test_1_id = scoped_key_env["test_1_id"]
    test_doc_id = scoped_key_env["test_doc_id"]
    test_sticky_id = scoped_key_env["test_sticky_id"]
    kan_1_id = scoped_key_env["kan_1_id"]
    tok_ws = scoped_key_env["tok_ws"]
    session_id = f"mcp-session-{uuid.uuid4()}"

    headers = {
        "X-KB-Service-Principal": "mcp-gateway",
        "X-KB-MCP-Session": session_id,
        "X-KB-Subject-Token": tok_ws,
    }

    # 1. Read restricted issue TEST-1
    resp_issue = await client.get(f"/api/v1/issues/{test_1_id}", headers=headers)
    assert resp_issue.status_code == 200
    assert "CANARY-TEST-SECRET-1234" in resp_issue.json()["description_markdown"]
    assert "X-Kanban-Untrusted-Taint" not in resp_issue.headers

    # 2. Read restricted doc
    resp_doc = await client.get(f"/api/v1/docs/{test_doc_id}", headers=headers)
    assert resp_doc.status_code == 200
    assert "Secret details" in resp_doc.json()["body_markdown"]
    assert "X-Kanban-Untrusted-Taint" not in resp_doc.headers

    # 3. Read restricted sticky
    resp_sticky = await client.get(f"/api/v1/stickies/{test_sticky_id}", headers=headers)
    assert resp_sticky.status_code == 200
    assert "TEST-STICKY-SECRET" in resp_sticky.json()["body_markdown"]
    assert "X-Kanban-Untrusted-Taint" not in resp_sticky.headers

    # 4. Search restricted entities
    resp_search = await client.get("/api/v1/search?q=Confidential", headers=headers)
    assert resp_search.status_code == 200

    # 5. Immediately write to broader project KAN on the exact same session
    # 5a. create_issue in KAN
    create_resp = await client.post(
        "/api/v1/projects/KAN/issues",
        json={
            "summary": "Agent Created KAN Issue",
            "description_markdown": "Payload after reading TEST",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    assert create_resp.json()["summary"] == "Agent Created KAN Issue"

    # 5b. patch_issue on KAN-1
    patch_resp = await client.patch(
        f"/api/v1/issues/{kan_1_id}",
        json={"summary": "Updated Public Roadmap Item"},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["summary"] == "Updated Public Roadmap Item"

    # 5c. create_comment on KAN-1
    comment_resp = await client.post(
        f"/api/v1/issues/{kan_1_id}/comments",
        json={"body_markdown": "Automated comment following analysis of TEST architecture."},
        headers=headers,
    )
    assert comment_resp.status_code == 201
    assert "Automated comment" in comment_resp.json()["body_markdown"]

    # 5d. begin_work on KAN-1
    begin_resp = await client.post(
        "/api/v1/issues/KAN-1/begin-work",
        json={"plan_markdown": "Execution plan for KAN-1."},
        headers=headers,
    )
    assert begin_resp.status_code == 200

    # 5e. transition on KAN-1 to Todo
    trans_resp = await client.post(
        "/api/v1/issues/KAN-1/transition",
        json={"to_state": "Todo"},
        headers=headers,
    )
    assert trans_resp.status_code == 200, trans_resp.text
    assert trans_resp.json()["key"] == "KAN-1"

    # 5f. complete_work on KAN-1 to Done
    valid_report = """# Integration Agent Reality-Based Report

## Reality Check Validation
- Verified all deliverables against acceptance criteria.
- Complete audit of all source files and assets.

## Complete System Evidence
- System running smoothly with zero errors.
- Verification artifacts collected in docs/qa.

## Integration Testing Results
- All unit and integration test suites executed cleanly.
- Full regression suite passing.

## Comprehensive Issue Assessment
- Root cause identified and systematically resolved.
- Security and performance invariants verified.

## Realistic Quality Certification
- Verdict: READY
- Grade: A

## Deployment Readiness Assessment
- Ready for immediate production deployment.
- No rollback concerns or migration locks.
"""
    valid_proof = {
        "qa_dir": "docs/qa/KAN-1/",
        "reality_checker": {
            "verdict": "READY",
            "grade": "A",
            "report_path": "docs/qa/KAN-1/reality-checker-report.md",
        },
        "ci_run_url": "https://dash.hackedyour.info/runs/12345",
        "artifacts": [
            "docs/qa/KAN-1/git-diff.patch",
            "docs/qa/KAN-1/unit-test-results.txt",
        ],
    }
    complete_resp = await client.post(
        "/api/v1/issues/KAN-1/complete-work",
        json={
            "summary_markdown": valid_report,
            "verification_proof": valid_proof,
        },
        headers=headers,
    )
    assert complete_resp.status_code == 200, complete_resp.text
    assert complete_resp.json()["key"] == "KAN-1"
    assert complete_resp.json()["workflow_status"] == "completed"


@pytest.mark.asyncio
async def test_project_scoped_key_cannot_read_or_mutate_sibling_project(
    scoped_key_env: dict[str, Any],
) -> None:
    """Case (b): A project-scoped key (KAN) cannot read, list, search, or mutate sibling project TEST."""
    client: httpx.AsyncClient = scoped_key_env["client"]
    db_session: AsyncSession = scoped_key_env["session"]
    ws_id = scoped_key_env["ws_id"]
    alice_id = scoped_key_env["alice_id"]
    proj_test_id = scoped_key_env["proj_test_id"]
    proj_kan_id = scoped_key_env["proj_kan_id"]
    test_1_id = scoped_key_env["test_1_id"]
    test_doc_id = scoped_key_env["test_doc_id"]
    test_sticky_id = scoped_key_env["test_sticky_id"]
    tok_proj_kan = scoped_key_env["tok_proj_kan"]
    boundary_kan = scoped_key_env["boundary_kan"]
    session_id = f"mcp-session-{uuid.uuid4()}"

    headers = {
        "X-KB-Service-Principal": "mcp-gateway",
        "X-KB-MCP-Session": session_id,
        "X-KB-Subject-Token": tok_proj_kan,
    }

    # 1. Attempt to read TEST-1 -> 404 (row filtered out by PostgreSQL FORCE RLS)
    resp_issue = await client.get(f"/api/v1/issues/{test_1_id}", headers=headers)
    assert resp_issue.status_code == 404

    # 2. Attempt to list issues in TEST -> 404
    resp_list = await client.get("/api/v1/projects/TEST/issues", headers=headers)
    assert resp_list.status_code == 404

    # 3. Attempt to read doc in TEST -> 404
    resp_doc = await client.get(f"/api/v1/docs/{test_doc_id}", headers=headers)
    assert resp_doc.status_code == 404

    # 4. Attempt to read sticky in TEST -> 404
    resp_sticky = await client.get(f"/api/v1/stickies/{test_sticky_id}", headers=headers)
    assert resp_sticky.status_code == 404

    # 5. Search with KAN-scoped key does not return any TEST entities
    resp_search = await client.get("/api/v1/search?q=Confidential", headers=headers)
    assert resp_search.status_code == 200
    search_data = resp_search.json()
    items = search_data.get("items", [])
    assert not any(str(test_1_id) in str(item) or "TEST" in str(item) for item in items)

    # 6. Attempt mutations in TEST -> all rejected (404/403)
    # 6a. create_issue in TEST
    create_resp = await client.post(
        "/api/v1/projects/TEST/issues",
        json={"summary": "Unauthorized Issue Injection"},
        headers=headers,
    )
    assert create_resp.status_code in (403, 404)

    # 6b. patch_issue on TEST-1
    patch_resp = await client.patch(
        f"/api/v1/issues/{test_1_id}",
        json={"summary": "Tampered Title"},
        headers=headers,
    )
    assert patch_resp.status_code == 404

    # 6c. create_comment on TEST-1
    comment_resp = await client.post(
        f"/api/v1/issues/{test_1_id}/comments",
        json={"body_markdown": "Unauthorized comment injection."},
        headers=headers,
    )
    assert comment_resp.status_code == 404

    # 7. Direct PostgreSQL FORCE RLS validation at the database layer
    if not db_session.in_transaction():
        await db_session.begin()
    await db_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))
    ctx_kan = RLSContext(
        principal_id=alice_id,
        workspace_id=ws_id,
        credential_boundary=boundary_kan,
    )
    await bind_rls_context(db_session, ctx_kan)

    # Querying TEST project rows under KAN credential boundary returns 0 rows
    test_issues_count = (
        await db_session.execute(
            text("SELECT count(*) FROM issues WHERE project_id = :p"),
            {"p": proj_test_id},
        )
    ).scalar_one()
    assert test_issues_count == 0

    test_docs_count = (
        await db_session.execute(
            text("SELECT count(*) FROM docs WHERE project_id = :p"),
            {"p": proj_test_id},
        )
    ).scalar_one()
    assert test_docs_count == 0

    test_stickies_count = (
        await db_session.execute(
            text("SELECT count(*) FROM stickies WHERE project_id = :p"),
            {"p": proj_test_id},
        )
    ).scalar_one()
    assert test_stickies_count == 0

    # Querying KAN project rows under KAN credential boundary succeeds
    kan_issues_count = (
        await db_session.execute(
            text("SELECT count(*) FROM issues WHERE project_id = :p"),
            {"p": proj_kan_id},
        )
    ).scalar_one()
    assert kan_issues_count >= 1
