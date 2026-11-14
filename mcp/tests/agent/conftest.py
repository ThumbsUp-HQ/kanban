# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Test fixtures for /mcp/agent surface tests."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

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
from kanban.services.activity import ActivityEventType, record_activity
from kanban.tests.security.helpers import (
    add_role_binding,
    create_agent,
    create_project,
    create_user,
    create_workspace,
    rebuild_era,
)
from mcp.app import create_mcp_app
from mcp.internal_client import KanbanApiClient
from mcp.settings import McpSettings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from starlette.requests import Request


@dataclass(frozen=True, slots=True)
class AgentSeededUser:
    """User principal representation in agent tests."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    handle: str


@dataclass(slots=True)
class AgentTestEnv:
    """Complete test environment for /mcp/agent surface."""

    mcp_client: httpx.AsyncClient
    internal_client: KanbanApiClient
    seed_session: AsyncSession
    workspace_id: uuid.UUID
    admin_user: AgentSeededUser
    adam_user: AgentSeededUser
    agent_no_grant_id: uuid.UUID
    proj_kan_id: uuid.UUID
    proj_pub_id: uuid.UUID
    proj_sec_id: uuid.UUID
    issue_142_id: uuid.UUID
    issue_150_id: uuid.UUID
    issue_pending_id: uuid.UUID
    token_adam: str
    token_no_grant: str
    token_admin: str


class _TestTokenResolver:
    """Resolves PrincipalContext by checking X-KB-Subject-Token header."""

    def __init__(
        self,
        default_principal: PrincipalContext,
        token_map: dict[str, PrincipalContext],
    ) -> None:
        self.default_principal = default_principal
        self.token_map = token_map

    async def resolve(self, request: Request) -> PrincipalContext | None:
        tok = request.headers.get("x-kb-subject-token")
        if tok and tok in self.token_map:
            return self.token_map[tok]
        return self.default_principal


async def _seed_issue(  # noqa: PLR0913, PLR0917
    session: AsyncSession,
    ws_id: uuid.UUID,
    proj_id: uuid.UUID,
    identifier: str,
    seq: int,
    summary: str,
    description: str,
    user_id: uuid.UUID,
    state_id: uuid.UUID,
    priority_id: uuid.UUID,
    board_rank: str = "a0",
    pending_exec_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Seed an issue row with sequence update and object registration."""
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
            "cr": user_id,
            "id": iss_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO issues (id, object_type, workspace_id, project_id, sequence_id, summary, "
            "description_markdown, state_id, priority_id, created_by_id, original_created_by_id, "
            "board_rank, ancestry_path, pending_transition_exec_id) "
            "VALUES (:id, 'issue', :ws, :proj, :seq, :summary, :desc, :st, :pri, :cr, :cr, "
            ":rnk, 'top', :pexec)"
        ),
        {
            "id": iss_id,
            "ws": ws_id,
            "proj": proj_id,
            "seq": seq,
            "summary": summary,
            "desc": description,
            "st": state_id,
            "pri": priority_id,
            "cr": user_id,
            "rnk": board_rank,
            "pexec": pending_exec_id,
        },
    )
    return iss_id


@pytest.fixture
async def agent_test_env(  # noqa: PLR0915
    committed_db_session: AsyncSession,
    pg_worker_db: AsyncEngine,
) -> AsyncIterator[AgentTestEnv]:
    """Fixture spinning up 3 projects / 30 issues + 1 restricted issue on real clean-DB."""
    ws_id = await create_workspace(committed_db_session, name="Engineering WS")
    await committed_db_session.commit()

    # 1. Create users
    admin_id = await create_user(
        committed_db_session, ws_id, handle="@admin", display_name="Admin User"
    )
    await add_role_binding(
        committed_db_session, ws_id, admin_id, role="WORKSPACE_ADMIN", scope_type="workspace"
    )

    adam_id = await create_user(committed_db_session, ws_id, handle="@adam", display_name="Adam")

    agent_no_grant_id = await create_agent(
        committed_db_session, ws_id, "Agent Without Grant", principal_type="AGENT"
    )
    # Notice: agent_no_grant_id is NOT given any role binding on KAN

    # 2. Create projects
    proj_kan_id = await create_project(
        committed_db_session,
        ws_id,
        identifier="KAN",
        name="Kanban Core",
        created_by_id=admin_id,
    )
    await add_role_binding(
        committed_db_session,
        ws_id,
        adam_id,
        role="MEMBER",
        scope_type="project",
        project_id=proj_kan_id,
    )

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

    proj_sec_id = await create_project(
        committed_db_session,
        ws_id,
        identifier="SEC",
        name="Secret Confidential",
        created_by_id=admin_id,
    )
    # Adam has NO role on SEC. Only admin has PROJECT_ADMIN on SEC.
    await add_role_binding(
        committed_db_session,
        ws_id,
        admin_id,
        role="PROJECT_ADMIN",
        scope_type="project",
        project_id=proj_sec_id,
    )

    await rebuild_era(committed_db_session, ws_id)
    await committed_db_session.commit()

    # Get states and priorities for KAN
    kan_states: dict[str, uuid.UUID] = {
        row[0]: row[1]
        for row in (
            await committed_db_session.execute(
                text("SELECT name, id FROM workflow_states WHERE project_id = :p"),
                {"p": proj_kan_id},
            )
        ).all()
    }
    kan_priorities: dict[str, uuid.UUID] = {
        row[0]: row[1]
        for row in (
            await committed_db_session.execute(
                text("SELECT slug, id FROM project_priorities WHERE project_id = :p"),
                {"p": proj_kan_id},
            )
        ).all()
    }

    in_progress_state_id = kan_states["In Progress"]
    todo_state_id = kan_states["Todo"]
    urgent_pri_id = kan_priorities["urgent"]
    high_pri_id = kan_priorities["high"]
    med_pri_id = kan_priorities["medium"]

    # Get states and priorities for PUB
    pub_states: dict[str, uuid.UUID] = {
        row[0]: row[1]
        for row in (
            await committed_db_session.execute(
                text("SELECT name, id FROM workflow_states WHERE project_id = :p"),
                {"p": proj_pub_id},
            )
        ).all()
    }
    pub_priorities: dict[str, uuid.UUID] = {
        row[0]: row[1]
        for row in (
            await committed_db_session.execute(
                text("SELECT slug, id FROM project_priorities WHERE project_id = :p"),
                {"p": proj_pub_id},
            )
        ).all()
    }

    # Get states and priorities for SEC
    sec_states: dict[str, uuid.UUID] = {
        row[0]: row[1]
        for row in (
            await committed_db_session.execute(
                text("SELECT name, id FROM workflow_states WHERE project_id = :p"),
                {"p": proj_sec_id},
            )
        ).all()
    }
    sec_priorities: dict[str, uuid.UUID] = {
        row[0]: row[1]
        for row in (
            await committed_db_session.execute(
                text("SELECT slug, id FROM project_priorities WHERE project_id = :p"),
                {"p": proj_sec_id},
            )
        ).all()
    }

    # 3. Seed issues:
    # In KAN: 20 issues (total across KAN + PUB = 30 issues accessible to Adam)
    # KAN-142: In Progress, urgent, assigned to Adam.
    iss_142_id = await _seed_issue(
        committed_db_session,
        ws_id,
        proj_kan_id,
        "KAN",
        seq=142,
        summary="Harden Multi-Card OIDC & LDAPS Auth Studio",
        description="# OIDC Architecture\nFull description with sensitive details.\nLine 2.",
        user_id=admin_id,
        state_id=in_progress_state_id,
        priority_id=urgent_pri_id,
        board_rank="0|hzzzzz:",
    )
    # Assign Adam to KAN-142
    await committed_db_session.execute(
        text("INSERT INTO issue_assignees (issue_id, principal_id) VALUES (:iss, :p)"),
        {"iss": iss_142_id, "p": adam_id},
    )
    # Add comment to KAN-142
    comm_id = uuid.uuid4()
    await committed_db_session.execute(
        text(
            "INSERT INTO issue_comments (id, workspace_id, issue_id, author_id, body_markdown) "
            "VALUES (:id, :ws, :iss, :author, :body)"
        ),
        {
            "id": comm_id,
            "ws": ws_id,
            "iss": iss_142_id,
            "author": adam_id,
            "body": "Initial security audit comment for OIDC.",
        },
    )
    # Add activity for KAN-142
    await record_activity(
        committed_db_session,
        workspace_id=ws_id,
        object_id=iss_142_id,
        actor_principal_id=adam_id,
        event_type=ActivityEventType.COMMENT_CREATED,
        payload={"comment_id": str(comm_id)},
    )

    # KAN-150: Todo, high, summary: "LDAPS StartTLS bind verification"
    iss_150_id = await _seed_issue(
        committed_db_session,
        ws_id,
        proj_kan_id,
        "KAN",
        seq=150,
        summary="LDAPS StartTLS bind verification",
        description="Verify LDAPS bind with StartTLS certificate validation.",
        user_id=admin_id,
        state_id=todo_state_id,
        priority_id=high_pri_id,
        board_rank="0|i00000:",
    )

    # Add object link: KAN-142 RELATES_TO KAN-150
    await committed_db_session.execute(
        text(
            "INSERT INTO object_links (id, workspace_id, source_id, source_type, target_id, "
            "target_type, link_type, link_state, source_key_snapshot, target_key_snapshot, "
            "created_by_id) VALUES (:id, :ws, :src, 'issue', :tgt, 'issue', 'RELATES_TO', "
            "'ACTIVE', 'KAN-142', 'KAN-150', :cr)"
        ),
        {
            "id": uuid.uuid4(),
            "ws": ws_id,
            "src": iss_142_id,
            "tgt": iss_150_id,
            "cr": admin_id,
        },
    )

    # KAN-3: Pending gate issue
    pending_exec_id = uuid.uuid4()
    iss_pending_id = await _seed_issue(
        committed_db_session,
        ws_id,
        proj_kan_id,
        "KAN",
        seq=3,
        summary="OIDC Token Refresh",
        description="Refresh tokens under OIDC specification.",
        user_id=admin_id,
        state_id=todo_state_id,
        priority_id=med_pri_id,
        board_rank="0|i00001:",
        pending_exec_id=pending_exec_id,
    )

    # Seed KAN-4 .. KAN-20 (17 more issues in KAN)
    for seq in range(4, 21):
        await _seed_issue(
            committed_db_session,
            ws_id,
            proj_kan_id,
            "KAN",
            seq=seq,
            summary=f"KAN Issue {seq} for pagination test",
            description=f"Description for KAN issue {seq}.",
            user_id=admin_id,
            state_id=todo_state_id,
            priority_id=med_pri_id,
            board_rank=f"0|i{seq:05d}:",
        )

    # In PUB: 10 issues (PUB-1 .. PUB-10)
    for seq in range(1, 11):
        await _seed_issue(
            committed_db_session,
            ws_id,
            proj_pub_id,
            "PUB",
            seq=seq,
            summary=f"PUB Issue {seq} for public backlog",
            description=f"Description for PUB issue {seq}.",
            user_id=admin_id,
            state_id=pub_states["Todo"],
            priority_id=pub_priorities["medium"],
            board_rank=f"0|p{seq:05d}:",
        )

    # In SEC: 1 restricted issue (SEC-1)
    await _seed_issue(
        committed_db_session,
        ws_id,
        proj_sec_id,
        "SEC",
        seq=1,
        summary="Secret issue containing secret data",
        description="Ultra secret confidential details.",
        user_id=admin_id,
        state_id=sec_states["Todo"],
        priority_id=sec_priorities["high"],
        board_rank="0|s00001:",
    )

    await rebuild_era(committed_db_session, ws_id)
    await committed_db_session.commit()

    # 4. Set up FastAPI and MCP app
    db_name = pg_worker_db.url.database or "kanban_test"
    socket_dir = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")
    app_engine = create_async_engine(
        build_dsn(database=db_name, host=socket_dir, user="kanban_app"),
        poolclass=NullPool,
    )

    token_adam = "kb_agt_adam_" + "a" * 32
    token_no_grant = "kb_agt_nogrant_" + "b" * 32
    token_admin = "kb_agt_admin_" + "c" * 32

    token_map = {
        token_adam: PrincipalContext(
            principal_id=adam_id,
            workspace_id=ws_id,
            token_scopes=("agent:read", "agent:write"),
        ),
        token_no_grant: PrincipalContext(
            principal_id=agent_no_grant_id,
            workspace_id=ws_id,
            token_scopes=("agent:read",),
        ),
        token_admin: PrincipalContext(
            principal_id=admin_id,
            workspace_id=ws_id,
            token_scopes=("agent:read", "agent:write"),
        ),
    }

    resolver = _TestTokenResolver(
        default_principal=token_map[token_adam],
        token_map=token_map,
    )

    fastapi_app = create_app()
    fastapi_app.state.session_factory = RLSSessionFactory(app_engine)
    fastapi_app.state.principal_resolver = resolver

    mcp_settings = McpSettings(mode="standalone_inprocess", auth_enabled=False)
    internal_client = KanbanApiClient(mcp_settings, kanban_app=fastapi_app)

    mcp_starlette_app = create_mcp_app(mcp_settings, kanban_app=fastapi_app)
    transport = httpx.ASGITransport(app=mcp_starlette_app)

    csrf_token = generate_csrf_token(PRE_SESSION_ID, b"\x00" * 32)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={
            CSRF_HEADER_NAME: csrf_token,
            "X-KB-Subject-Token": token_adam,
        },
        cookies={CSRF_COOKIE_NAME: csrf_token},
    ) as mcp_http_client:
        env = AgentTestEnv(
            mcp_client=mcp_http_client,
            internal_client=internal_client,
            seed_session=committed_db_session,
            workspace_id=ws_id,
            admin_user=AgentSeededUser(id=admin_id, workspace_id=ws_id, handle="admin"),
            adam_user=AgentSeededUser(id=adam_id, workspace_id=ws_id, handle="adam"),
            agent_no_grant_id=agent_no_grant_id,
            proj_kan_id=proj_kan_id,
            proj_pub_id=proj_pub_id,
            proj_sec_id=proj_sec_id,
            issue_142_id=iss_142_id,
            issue_150_id=iss_150_id,
            issue_pending_id=iss_pending_id,
            token_adam=token_adam,
            token_no_grant=token_no_grant,
            token_admin=token_admin,
        )
        try:
            yield env
        finally:
            await internal_client.aclose()
            await app_engine.dispose()
