# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: PLC0415, E501, I001, PT018
"""Feature unit and security tests for read-taint exfiltration guard (KB-P4-07).

Covers:
  1. Positive: Read records session and credential taint in mcp_read_taint table.
  2. Exfiltration canary: Reading SEC-1 and posting to PUB-1 is blocked (409 cross-scope-taint),
     zero comments with CANARY-7f3a exist in DB, MCP_TAINT_BLOCKED activity event is recorded.
  3. Session escape: New session ID with same subject token is still blocked by credential taint;
     different credential without reads succeeds.
  4. Allowed paths: Reading PUB and writing to SEC succeeds (narrower audience); reading SEC and
     writing to SEC succeeds; linking SEC-1 -> PUB-1 is blocked.
  5. Boundary: Expired session and credential taints allow writing to PUB-1.
  6. Missing header: Requests from mcp-gateway without X-KB-MCP-Session return 400.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import UTC, datetime, timedelta
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
    """Resolves PrincipalContext by checking X-KB-Subject-Token header or default."""

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


async def _seed_test_issue(  # noqa: PLR0913, PLR0917
    session: AsyncSession,
    ws_id: uuid.UUID,
    proj_id: uuid.UUID,
    identifier: str,
    seq: int,
    summary: str,
    description: str,
    creator_id: uuid.UUID,
) -> uuid.UUID:
    """Seed an issue row with sequence counter and Universal Object Graph registration."""
    await session.execute(
        text(
            "UPDATE projects SET issue_seq_counter = GREATEST(issue_seq_counter, :seq) "
            "WHERE id = :p"
        ),
        {"p": proj_id, "seq": seq},
    )
    iss_id = uuid.uuid4()
    await session.execute(
        text("SELECT register_object('issue'::object_kind, :ws, :proj, :ckey, :title, :cr, :id)"),
        {
            "ws": ws_id,
            "proj": proj_id,
            "ckey": f"{identifier}-{seq}",
            "title": summary,
            "cr": creator_id,
            "id": iss_id,
        },
    )
    st_row = (
        await session.execute(
            text("SELECT id FROM workflow_states WHERE project_id = :p LIMIT 1"),
            {"p": proj_id},
        )
    ).scalar_one()
    pri_row = (
        await session.execute(
            text("SELECT id FROM project_priorities WHERE project_id = :p LIMIT 1"),
            {"p": proj_id},
        )
    ).scalar_one()

    await session.execute(
        text(
            "INSERT INTO issues (id, object_type, workspace_id, project_id, sequence_id, summary, "
            "description_markdown, state_id, priority_id, created_by_id, original_created_by_id, "
            "board_rank, ancestry_path) "
            "VALUES (:id, 'issue', :ws, :proj, :seq, :summary, :desc, :st, :pri, :cr, :cr, "
            "'0|s00001:', 'top')"
        ),
        {
            "id": iss_id,
            "ws": ws_id,
            "proj": proj_id,
            "seq": seq,
            "summary": summary,
            "desc": description,
            "st": st_row,
            "pri": pri_row,
            "cr": creator_id,
        },
    )
    return iss_id


@pytest.fixture
async def taint_test_env(
    committed_db_session: AsyncSession,
    pg_worker_db: AsyncEngine,
) -> AsyncIterator[dict[str, Any]]:
    """Set up clean-DB test environment with SEC (restricted) and PUB (broader) projects."""
    ws_id = await create_workspace(committed_db_session, name="Security Workspace")

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
        committed_db_session, ws_id, identifier="SEC", name="Secret Project", created_by_id=admin_id
    )
    await add_role_binding(
        committed_db_session,
        ws_id,
        adam_id,
        role="MEMBER",
        scope_type="project",
        project_id=proj_sec_id,
    )

    # 2. PUB: Public project. Audience = {adam, admin, maya}.
    proj_pub_id = await create_project(
        committed_db_session, ws_id, identifier="PUB", name="Public Project", created_by_id=admin_id
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

    # Seed issues:
    # SEC-1 contains the canary CANARY-7f3a
    canary_content = "Confidential specification containing secret canary CANARY-7f3a."
    sec_1_id = await _seed_test_issue(
        committed_db_session,
        ws_id,
        proj_sec_id,
        "SEC",
        seq=1,
        summary="Secret Architecture",
        description=canary_content,
        creator_id=admin_id,
    )

    pub_1_id = await _seed_test_issue(
        committed_db_session,
        ws_id,
        proj_pub_id,
        "PUB",
        seq=1,
        summary="Public Roadmap",
        description="Publicly visible backlog roadmap.",
        creator_id=admin_id,
    )

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
            "sec_1_id": sec_1_id,
            "pub_1_id": pub_1_id,
            "tok_adam": tok_adam,
            "tok_maya": tok_maya,
        }
    await app_engine.dispose()


@pytest.mark.asyncio
async def test_case_1_positive_read_taint_recorded(taint_test_env: dict[str, Any]) -> None:
    """Case 1: Reading an issue records session and credential taints in mcp_read_taint."""
    client: httpx.AsyncClient = taint_test_env["client"]
    db_session: AsyncSession = taint_test_env["session"]
    sec_1_id = taint_test_env["sec_1_id"]
    tok_adam = taint_test_env["tok_adam"]
    session_id = f"mcp-sess-{uuid.uuid4()}"

    resp = await client.get(
        f"/api/v1/issues/{sec_1_id}",
        headers={
            "X-KB-Service-Principal": "mcp-gateway",
            "X-KB-MCP-Session": session_id,
            "X-KB-Subject-Token": tok_adam,
        },
    )
    assert resp.status_code == 200

    # Query mcp_read_taint directly
    sess_hash = hashlib.sha256(session_id.encode("utf-8")).digest()
    tok_hash = hashlib.sha256(tok_adam.encode("utf-8")).digest()

    await db_session.rollback()
    rows = (
        await db_session.execute(
            text(
                "SELECT taint_key, key_kind, project_id FROM mcp_read_taint WHERE project_id = :p"
            ),
            {"p": taint_test_env["proj_sec_id"]},
        )
    ).all()

    assert len(rows) >= 2
    kinds = {row[1] for row in rows}
    assert "session" in kinds
    assert "credential" in kinds
    keys = {bytes(row[0]) for row in rows}
    assert sess_hash in keys
    assert tok_hash in keys


@pytest.mark.asyncio
async def test_case_2_canary_exfiltration_blocked(taint_test_env: dict[str, Any]) -> None:
    """Case 2: Canary exfiltration test: reading SEC-1 then writing to PUB-1 is blocked."""
    client: httpx.AsyncClient = taint_test_env["client"]
    db_session: AsyncSession = taint_test_env["session"]
    sec_1_id = taint_test_env["sec_1_id"]
    pub_1_id = taint_test_env["pub_1_id"]
    tok_adam = taint_test_env["tok_adam"]
    session_id = f"mcp-sess-canary-{uuid.uuid4()}"

    # 1. Read SEC-1 containing CANARY-7f3a
    read_resp = await client.get(
        f"/api/v1/issues/{sec_1_id}",
        headers={
            "X-KB-Service-Principal": "mcp-gateway",
            "X-KB-MCP-Session": session_id,
            "X-KB-Subject-Token": tok_adam,
        },
    )
    assert read_resp.status_code == 200
    assert "CANARY-7f3a" in read_resp.json()["description_markdown"]

    # 2. Attempt to post comment with canary to PUB-1
    write_resp = await client.post(
        f"/api/v1/issues/{pub_1_id}/comments",
        json={"body_markdown": "Attempted exfiltration of secret canary CANARY-7f3a"},
        headers={
            "X-KB-Service-Principal": "mcp-gateway",
            "X-KB-MCP-Session": session_id,
            "X-KB-Subject-Token": tok_adam,
        },
    )
    assert write_resp.status_code == 409
    body = write_resp.json()
    assert body["code"] == "CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED"
    assert "tainted_by" in body
    assert any("SEC" in str(t) for t in body["tainted_by"])

    # 3. Forensic DB assertions: zero comments contain CANARY-7f3a
    await db_session.rollback()
    comment_count = (
        await db_session.execute(
            text("SELECT count(*) FROM issue_comments WHERE body_markdown LIKE '%CANARY-7f3a%'")
        )
    ).scalar_one()
    assert comment_count == 0

    # 4. Forensic DB assertions: MCP_TAINT_BLOCKED activity event recorded
    activity_count = (
        await db_session.execute(
            text("SELECT count(*) FROM activity_records WHERE event_type = 'MCP_TAINT_BLOCKED'")
        )
    ).scalar_one()
    assert activity_count >= 1


@pytest.mark.asyncio
async def test_case_3_session_escape_prevented(taint_test_env: dict[str, Any]) -> None:
    """Case 3: Session escape prevented by credential taint; clean credential succeeds."""
    client: httpx.AsyncClient = taint_test_env["client"]
    sec_1_id = taint_test_env["sec_1_id"]
    pub_1_id = taint_test_env["pub_1_id"]
    tok_adam = taint_test_env["tok_adam"]
    tok_maya = taint_test_env["tok_maya"]

    session_1 = f"mcp-sess-read-{uuid.uuid4()}"

    # Read SEC-1 with tok_adam under session_1
    r_read = await client.get(
        f"/api/v1/issues/{sec_1_id}",
        headers={
            "X-KB-Service-Principal": "mcp-gateway",
            "X-KB-MCP-Session": session_1,
            "X-KB-Subject-Token": tok_adam,
        },
    )
    assert r_read.status_code == 200

    # Escape attempt: New session_2 with same tok_adam writing to PUB-1
    session_2 = f"mcp-sess-escape-{uuid.uuid4()}"
    r_escape = await client.post(
        f"/api/v1/issues/{pub_1_id}/comments",
        json={"body_markdown": "Attempting session escape with new session ID"},
        headers={
            "X-KB-Service-Principal": "mcp-gateway",
            "X-KB-MCP-Session": session_2,
            "X-KB-Subject-Token": tok_adam,
        },
    )
    assert r_escape.status_code == 409
    assert r_escape.json()["code"] == "CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED"

    # Different credential without reads (tok_maya) succeeds
    session_maya = f"mcp-sess-maya-{uuid.uuid4()}"
    r_maya = await client.post(
        f"/api/v1/issues/{pub_1_id}/comments",
        json={"body_markdown": "Legitimate comment from untainted principal Maya."},
        headers={
            "X-KB-Service-Principal": "mcp-gateway",
            "X-KB-MCP-Session": session_maya,
            "X-KB-Subject-Token": tok_maya,
        },
    )
    assert r_maya.status_code == 201


@pytest.mark.asyncio
async def test_case_4_allowed_paths_and_link_guard(taint_test_env: dict[str, Any]) -> None:
    """Case 4: Reading PUB and writing to SEC succeeds; linking SEC-1 -> PUB-1 is blocked."""
    client: httpx.AsyncClient = taint_test_env["client"]
    sec_1_id = taint_test_env["sec_1_id"]
    pub_1_id = taint_test_env["pub_1_id"]
    tok_adam = taint_test_env["tok_adam"]

    # Path A: Read PUB-1, then write to SEC-1 (SEC audience {adam, admin} is subset of PUB audience)
    session_pub = f"mcp-sess-pub-{uuid.uuid4()}"
    r_read_pub = await client.get(
        f"/api/v1/issues/{pub_1_id}",
        headers={
            "X-KB-Service-Principal": "mcp-gateway",
            "X-KB-MCP-Session": session_pub,
            "X-KB-Subject-Token": tok_adam,
        },
    )
    assert r_read_pub.status_code == 200

    r_write_sec = await client.post(
        f"/api/v1/issues/{sec_1_id}/comments",
        json={"body_markdown": "Writing narrower scope SEC-1 after reading PUB-1 is permitted."},
        headers={
            "X-KB-Service-Principal": "mcp-gateway",
            "X-KB-MCP-Session": session_pub,
            "X-KB-Subject-Token": tok_adam,
        },
    )
    assert r_write_sec.status_code == 201

    # Path B: Read SEC-1, write into same project SEC-1 succeeds
    session_sec = f"mcp-sess-same-{uuid.uuid4()}"
    r_read_sec = await client.get(
        f"/api/v1/issues/{sec_1_id}",
        headers={
            "X-KB-Service-Principal": "mcp-gateway",
            "X-KB-MCP-Session": session_sec,
            "X-KB-Subject-Token": tok_adam,
        },
    )
    assert r_read_sec.status_code == 200

    r_write_same = await client.post(
        f"/api/v1/issues/{sec_1_id}/comments",
        json={"body_markdown": "Writing into same SEC-1 project after reading SEC-1 is permitted."},
        headers={
            "X-KB-Service-Principal": "mcp-gateway",
            "X-KB-MCP-Session": session_sec,
            "X-KB-Subject-Token": tok_adam,
        },
    )
    assert r_write_same.status_code == 201

    # Path C: Link SEC-1 -> PUB-1 is blocked because PUB audience is broader
    r_link_blocked = await client.post(
        f"/api/v1/objects/{sec_1_id}/links",
        json={"target": str(pub_1_id), "link_type": "BLOCKS"},
        headers={
            "X-KB-Service-Principal": "mcp-gateway",
            "X-KB-MCP-Session": session_sec,
            "X-KB-Subject-Token": tok_adam,
        },
    )
    assert r_link_blocked.status_code == 409
    assert r_link_blocked.json()["code"] == "CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED"


@pytest.mark.asyncio
async def test_case_5_taint_expiry_allows_write(taint_test_env: dict[str, Any]) -> None:
    """Case 5: Expired taints in mcp_read_taint do not block writing to PUB-1."""
    client: httpx.AsyncClient = taint_test_env["client"]
    db_session: AsyncSession = taint_test_env["session"]
    pub_1_id = taint_test_env["pub_1_id"]
    tok_adam = taint_test_env["tok_adam"]
    session_expired = f"mcp-sess-exp-{uuid.uuid4()}"

    # Insert pre-expired session and credential taints
    sess_hash = hashlib.sha256(session_expired.encode("utf-8")).digest()
    tok_hash = hashlib.sha256(tok_adam.encode("utf-8")).digest()
    past_time = datetime.now(UTC) - timedelta(seconds=30)

    await db_session.execute(
        text(
            "INSERT INTO mcp_read_taint (workspace_id, taint_key, key_kind, project_id, first_read_at, expires_at) "
            "VALUES (:ws, :k1, 'session', :p, :exp, :exp), (:ws, :k2, 'credential', :p, :exp, :exp) "
            "ON CONFLICT (taint_key, project_id) DO UPDATE SET expires_at = :exp"
        ),
        {
            "ws": taint_test_env["ws_id"],
            "k1": sess_hash,
            "k2": tok_hash,
            "p": taint_test_env["proj_sec_id"],
            "exp": past_time,
        },
    )
    await db_session.commit()

    # Attempt to write to PUB-1: should succeed because taints are expired
    r_post = await client.post(
        f"/api/v1/issues/{pub_1_id}/comments",
        json={"body_markdown": "Writing after taints have expired is allowed."},
        headers={
            "X-KB-Service-Principal": "mcp-gateway",
            "X-KB-MCP-Session": session_expired,
            "X-KB-Subject-Token": tok_adam,
        },
    )
    assert r_post.status_code == 201


@pytest.mark.asyncio
async def test_case_6_missing_session_header_rejected(taint_test_env: dict[str, Any]) -> None:
    """Case 6: Requests from mcp-gateway without X-KB-MCP-Session return 400 Bad Request."""
    client: httpx.AsyncClient = taint_test_env["client"]
    sec_1_id = taint_test_env["sec_1_id"]
    tok_adam = taint_test_env["tok_adam"]

    resp = await client.get(
        f"/api/v1/issues/{sec_1_id}",
        headers={
            "X-KB-Service-Principal": "mcp-gateway",
            # X-KB-MCP-Session missing!
            "X-KB-Subject-Token": tok_adam,
        },
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] in ("MISSING_MCP_SESSION", "MISSING_SESSION_HEADER")


@pytest.mark.asyncio
async def test_case_7_unit_coverage_read_taint(taint_test_env: dict[str, Any]) -> None:
    """Case 7: Direct unit coverage for read_taint resolver, deps, and branch fallbacks."""
    from starlette.requests import Request
    from kanban.security.read_taint import (
        _resolve_project_uuid,
        TaintGuard,
        TaintRecorder,
        get_taint_guard,
        get_taint_recorder,
    )

    db_session: AsyncSession = taint_test_env["session"]
    ws_id = taint_test_env["ws_id"]
    proj_sec_id = taint_test_env["proj_sec_id"]
    adam_id = taint_test_env["adam_id"]

    # 1. _resolve_project_uuid with string identifier and string UUID
    res_ident = await _resolve_project_uuid(db_session, ws_id, "SEC")
    assert res_ident is not None and res_ident[0] == proj_sec_id
    res_str_uuid = await _resolve_project_uuid(db_session, ws_id, str(proj_sec_id))
    assert res_str_uuid is not None and res_str_uuid[0] == proj_sec_id
    res_unknown = await _resolve_project_uuid(db_session, ws_id, "DOES_NOT_EXIST")
    assert res_unknown is None

    # 2. TaintRecorder without session ID (noop)
    scope = {"type": "http", "headers": []}
    req_no_session = Request(scope)
    caller = PrincipalContext(
        principal_id=adam_id,
        workspace_id=ws_id,
        token_scopes=("agent:read",),
    )
    rec_no_sess = TaintRecorder(req_no_session, db_session, caller)
    await rec_no_sess.record_project_ids(["SEC", "SEC", "DOES_NOT_EXIST"])

    # 3. TaintRecorder with session ID and duplicate/unknown projects
    scope_with_sess = {
        "type": "http",
        "headers": [(b"x-kb-mcp-session", b"test-sess-123")],
    }
    rec_with_sess = TaintRecorder(Request(scope_with_sess), db_session, caller)
    await rec_with_sess.record_project_ids(["SEC", "SEC", "DOES_NOT_EXIST"])

    # 4. TaintGuard without session ID (noop)
    guard_no_sess = TaintGuard(req_no_session, db_session, caller)
    await guard_no_sess.check_write("SEC")

    # 5. TaintGuard with unknown target project (noop)
    guard_with_sess = TaintGuard(Request(scope_with_sess), db_session, caller)
    await guard_with_sess.check_write("DOES_NOT_EXIST")

    # 6. Dependency factory functions
    dep_rec = get_taint_recorder(req_no_session, db_session, caller)
    assert isinstance(dep_rec, TaintRecorder)
    dep_guard = get_taint_guard(req_no_session, db_session, caller)
    assert isinstance(dep_guard, TaintGuard)
