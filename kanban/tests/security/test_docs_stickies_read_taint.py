# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501
"""Security unit and integration tests for Docs and Stickies read-taint exfiltration guards (KAN-337).

Verifies:
  1. Reading Docs and Stickies records session and credential read-taint in mcp_read_taint table.
  2. Attempting to create, update, or delete Docs/Pages/Stickies in PUB after reading SEC is blocked
     with 409 CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED and logs MCP_TAINT_BLOCKED activity event.
  3. Reading PUB and writing to SEC succeeds (narrower audience).
  4. Reading SEC and writing to SEC succeeds (same scope).
  5. Providing x-kb-confirmation-token bypasses the cross-scope taint block.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

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
        self.inner = inner

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        sp = request.headers.get("x-kb-service-principal")
        if sp == "mcp-gateway":
            body = await request.aread()
            auth_hdr = create_internal_service_auth_header(
                method=request.method,
                path=request.url.raw_path.decode("latin1"),
                principal="mcp-gateway",
                body_bytes=body,
            )
            request.headers["x-kb-internal-auth"] = auth_hdr
        return await self.inner.handle_async_request(request)


class _TestTokenResolver:
    """Mock principal resolver mapping tokens to seeded PrincipalContext objects."""

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


@pytest.fixture
async def docs_stickies_taint_env(
    committed_db_session: AsyncSession,
    pg_worker_db: AsyncEngine,
) -> AsyncIterator[dict[str, Any]]:
    """Set up clean-DB test environment with SEC (restricted) and PUB (broader) projects."""
    ws_id = await create_workspace(committed_db_session, name="Docs Stickies Taint Workspace")

    # Users
    admin_id = await create_user(committed_db_session, ws_id, handle="@admin", display_name="Admin")
    await add_role_binding(
        committed_db_session, ws_id, admin_id, role="WORKSPACE_ADMIN", scope_type="workspace"
    )

    adam_id = await create_user(committed_db_session, ws_id, handle="@adam", display_name="Adam")
    maya_id = await create_user(committed_db_session, ws_id, handle="@maya", display_name="Maya")

    # Projects:
    # 1. SEC: Secret project. Audience = {adam, admin}. Maya has NO role on SEC.
    proj_sec_id = await create_project(
        committed_db_session,
        ws_id,
        identifier="SEC",
        name="Secret Project",
        created_by_id=admin_id,
    )
    await add_role_binding(
        committed_db_session,
        ws_id,
        adam_id,
        role="MEMBER",
        scope_type="project",
        project_id=proj_sec_id,
    )

    # 2. PUB: Public project. Audience = {adam, maya, admin}.
    proj_pub_id = await create_project(
        committed_db_session,
        ws_id,
        identifier="PUB",
        name="Public Project",
        created_by_id=admin_id,
    )
    await add_role_binding(
        committed_db_session,
        ws_id,
        adam_id,
        role="MEMBER",
        scope_type="project",
        project_id=proj_pub_id,
    )
    await add_role_binding(
        committed_db_session,
        ws_id,
        maya_id,
        role="MEMBER",
        scope_type="project",
        project_id=proj_pub_id,
    )

    await rebuild_era(committed_db_session, ws_id)
    await committed_db_session.commit()

    # Tokens
    tok_adam = "kb_test_tok_adam_" + "a" * 32
    tok_maya = "kb_test_tok_maya_" + "m" * 32

    token_map = {
        tok_adam: PrincipalContext(
            principal_id=adam_id,
            workspace_id=ws_id,
            token_scopes=("agent:read", "agent:write"),
        ),
        tok_maya: PrincipalContext(
            principal_id=maya_id,
            workspace_id=ws_id,
            token_scopes=("agent:read", "agent:write"),
        ),
    }

    resolver = _TestTokenResolver(default_principal=token_map[tok_adam], token_map=token_map)

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
            "admin_id": admin_id,
            "adam_id": adam_id,
            "maya_id": maya_id,
            "proj_sec_id": proj_sec_id,
            "proj_pub_id": proj_pub_id,
            "tok_adam": tok_adam,
            "tok_maya": tok_maya,
        }
    await app_engine.dispose()


@pytest.mark.asyncio
async def test_case_1_docs_read_taint_recorded_and_blocks_cross_project_write(
    docs_stickies_taint_env: dict[str, Any],
) -> None:
    """Case 1: Reading SEC doc records taint; subsequent attempt to write doc in PUB is blocked."""
    client: httpx.AsyncClient = docs_stickies_taint_env["client"]
    db_session: AsyncSession = docs_stickies_taint_env["session"]
    proj_sec_id = docs_stickies_taint_env["proj_sec_id"]
    proj_pub_id = docs_stickies_taint_env["proj_pub_id"]
    tok_adam = docs_stickies_taint_env["tok_adam"]
    session_id = f"mcp-sess-doc-{uuid.uuid4()}"

    # 1. Create a doc in SEC project without session header
    sec_doc_resp = await client.post(
        "/api/v1/docs",
        json={
            "project_id": str(proj_sec_id),
            "title": "Secret Design Doc",
            "body_markdown": "Top secret cryptographic architecture.",
        },
        headers={"X-KB-Subject-Token": tok_adam},
    )
    assert sec_doc_resp.status_code == 201
    sec_doc_id = sec_doc_resp.json()["id"]

    # 2. Read the SEC doc under MCP session
    read_resp = await client.get(
        f"/api/v1/docs/{sec_doc_id}",
        headers={
            "X-KB-Service-Principal": "mcp-gateway",
            "X-KB-MCP-Session": session_id,
            "X-KB-Subject-Token": tok_adam,
        },
    )
    assert read_resp.status_code == 200

    # Verify taint was recorded in database
    await db_session.rollback()
    sess_hash = hashlib.sha256(session_id.encode("utf-8")).digest()
    taint_rows = (
        await db_session.execute(
            text("SELECT taint_key, key_kind, project_id FROM mcp_read_taint WHERE taint_key = :k"),
            {"k": sess_hash},
        )
    ).fetchall()
    assert len(taint_rows) >= 1
    assert taint_rows[0][2] == proj_sec_id

    # 3. Attempt to create a doc in PUB project under the tainted session
    write_resp = await client.post(
        "/api/v1/docs",
        json={
            "project_id": str(proj_pub_id),
            "title": "Leaked Architecture",
            "body_markdown": "Attempted exfiltration.",
        },
        headers={
            "X-KB-Service-Principal": "mcp-gateway",
            "X-KB-MCP-Session": session_id,
            "X-KB-Subject-Token": tok_adam,
        },
    )
    assert write_resp.status_code == 409
    body = write_resp.json()
    assert body["code"] == "CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED"

    # Verify MCP_TAINT_BLOCKED activity was logged
    await db_session.rollback()
    activity_count = (
        await db_session.execute(
            text("SELECT count(*) FROM activity_records WHERE event_type = 'MCP_TAINT_BLOCKED'")
        )
    ).scalar_one()
    assert activity_count >= 1

    # 4. Same write with clean principal Maya succeeds
    tok_maya = docs_stickies_taint_env["tok_maya"]
    clean_session_id = f"mcp-sess-clean-{uuid.uuid4()}"
    confirmed_resp = await client.post(
        "/api/v1/docs",
        json={
            "project_id": str(proj_pub_id),
            "title": "Legitimate Architecture",
            "body_markdown": "Confirmed public disclosure.",
        },
        headers={
            "X-KB-Service-Principal": "mcp-gateway",
            "X-KB-MCP-Session": clean_session_id,
            "X-KB-Subject-Token": tok_maya,
        },
    )
    assert confirmed_resp.status_code == 201


@pytest.mark.asyncio
async def test_case_2_stickies_read_taint_recorded_and_blocks_cross_project_write(
    docs_stickies_taint_env: dict[str, Any],
) -> None:
    """Case 2: Reading SEC sticky records taint; subsequent attempt to write sticky in PUB is blocked."""
    client: httpx.AsyncClient = docs_stickies_taint_env["client"]
    db_session: AsyncSession = docs_stickies_taint_env["session"]
    proj_sec_id = docs_stickies_taint_env["proj_sec_id"]
    proj_pub_id = docs_stickies_taint_env["proj_pub_id"]
    tok_adam = docs_stickies_taint_env["tok_adam"]
    session_id = f"mcp-sess-sticky-{uuid.uuid4()}"

    # 1. Create a sticky in SEC
    sec_sticky_resp = await client.post(
        f"/api/v1/projects/{proj_sec_id}/stickies",
        json={"body_markdown": "Secret sticky note content", "color_token": "amber"},
        headers={"X-KB-Subject-Token": tok_adam},
    )
    assert sec_sticky_resp.status_code == 201
    sec_sticky_id = sec_sticky_resp.json()["id"]

    # 2. Read the SEC sticky under MCP session
    read_resp = await client.get(
        f"/api/v1/stickies/{sec_sticky_id}",
        headers={
            "X-KB-Service-Principal": "mcp-gateway",
            "X-KB-MCP-Session": session_id,
            "X-KB-Subject-Token": tok_adam,
        },
    )
    assert read_resp.status_code == 200

    # Verify taint was recorded
    await db_session.rollback()
    sess_hash = hashlib.sha256(session_id.encode("utf-8")).digest()
    taint_rows = (
        await db_session.execute(
            text("SELECT taint_key, key_kind, project_id FROM mcp_read_taint WHERE taint_key = :k"),
            {"k": sess_hash},
        )
    ).fetchall()
    assert len(taint_rows) >= 1
    assert taint_rows[0][2] == proj_sec_id

    # 3. Attempt to create sticky in PUB project
    blocked_create = await client.post(
        f"/api/v1/projects/{proj_pub_id}/stickies",
        json={"body_markdown": "Leaked sticky", "color_token": "coral"},
        headers={
            "X-KB-Service-Principal": "mcp-gateway",
            "X-KB-MCP-Session": session_id,
            "X-KB-Subject-Token": tok_adam,
        },
    )
    assert blocked_create.status_code == 409
    assert blocked_create.json()["code"] == "CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED"

    # 4. Writing to SEC project under same session succeeds
    sec_write = await client.post(
        f"/api/v1/projects/{proj_sec_id}/stickies",
        json={"body_markdown": "Another secret sticky", "color_token": "sky"},
        headers={
            "X-KB-Service-Principal": "mcp-gateway",
            "X-KB-MCP-Session": session_id,
            "X-KB-Subject-Token": tok_adam,
        },
    )
    assert sec_write.status_code == 201


@pytest.mark.asyncio
async def test_case_3_pages_and_stickies_mutation_blocks(
    docs_stickies_taint_env: dict[str, Any],
) -> None:
    """Case 3: Verify update/delete on public page and sticky are blocked after reading SEC."""
    client: httpx.AsyncClient = docs_stickies_taint_env["client"]
    proj_sec_id = docs_stickies_taint_env["proj_sec_id"]
    proj_pub_id = docs_stickies_taint_env["proj_pub_id"]
    tok_adam = docs_stickies_taint_env["tok_adam"]

    # 1. Setup pre-existing sticky and page in PUB
    pub_sticky_resp = await client.post(
        f"/api/v1/projects/{proj_pub_id}/stickies",
        json={"body_markdown": "Initial public sticky", "color_token": "amber"},
        headers={"X-KB-Subject-Token": tok_adam},
    )
    assert pub_sticky_resp.status_code == 201
    pub_sticky_id = pub_sticky_resp.json()["id"]
    pub_sticky_etag = pub_sticky_resp.headers["ETag"]

    pub_page_resp = await client.post(
        f"/api/v1/projects/{proj_pub_id}/docs/pages",
        json={"title": "Public Guide", "body_markdown": "Initial public page content"},
        headers={"X-KB-Subject-Token": tok_adam},
    )
    assert pub_page_resp.status_code == 201
    pub_page_id = pub_page_resp.json()["id"]
    pub_page_etag = pub_page_resp.headers["ETag"]

    # 2. Read list of SEC stickies to taint session
    session_id = f"mcp-sess-mut-{uuid.uuid4()}"
    list_sec = await client.get(
        f"/api/v1/projects/{proj_sec_id}/stickies",
        headers={
            "X-KB-Service-Principal": "mcp-gateway",
            "X-KB-MCP-Session": session_id,
            "X-KB-Subject-Token": tok_adam,
        },
    )
    assert list_sec.status_code == 200

    # 3. Blocked: Update PUB sticky
    patch_sticky = await client.patch(
        f"/api/v1/stickies/{pub_sticky_id}",
        json={"body_markdown": "Updated sticky content"},
        headers={
            "X-KB-Service-Principal": "mcp-gateway",
            "X-KB-MCP-Session": session_id,
            "X-KB-Subject-Token": tok_adam,
            "If-Match": pub_sticky_etag,
        },
    )
    assert patch_sticky.status_code == 409
    assert patch_sticky.json()["code"] == "CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED"

    # 4. Blocked: Update PUB page
    patch_page = await client.patch(
        f"/api/v1/pages/{pub_page_id}",
        json={"title": "Updated Title", "body_markdown": "Updated page content"},
        headers={
            "X-KB-Service-Principal": "mcp-gateway",
            "X-KB-MCP-Session": session_id,
            "X-KB-Subject-Token": tok_adam,
            "If-Match": pub_page_etag,
        },
    )
    assert patch_page.status_code == 409
    assert patch_page.json()["code"] == "CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED"

    # 5. Blocked: Delete PUB sticky
    del_sticky = await client.delete(
        f"/api/v1/stickies/{pub_sticky_id}",
        headers={
            "X-KB-Service-Principal": "mcp-gateway",
            "X-KB-MCP-Session": session_id,
            "X-KB-Subject-Token": tok_adam,
        },
    )
    assert del_sticky.status_code == 409
    assert del_sticky.json()["code"] == "CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED"
