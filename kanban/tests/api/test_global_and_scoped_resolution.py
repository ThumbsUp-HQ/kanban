# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration tests for global cross-workspace and scoped entity resolution (KB-P4-15, S11.1)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from sqlalchemy import text

from database.session import RLSContext, RLSSessionFactory
from kanban.api.deps import PrincipalContext
from kanban.api.problems import (
    ProblemException,
    problem_exception_handler,
    validation_exception_handler,
)
from kanban.api.request_id import RequestIdMiddleware
from kanban.api.v1.resolve import resolve_router
from kanban.resolve import ResolutionService
from kanban.services.issue_keys import resolve_issue_ref

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class _DynamicPrincipalResolver:
    """Principal resolver providing dynamically configured PrincipalContext."""

    def __init__(self, principal: PrincipalContext) -> None:
        self.principal = principal

    async def resolve(self, request: Any) -> PrincipalContext | None:  # noqa: ANN401
        del request
        return self.principal


def _build_app(
    principal: PrincipalContext,
    session_factory: RLSSessionFactory,
) -> FastAPI:
    """Build test FastAPI app with resolution router."""
    app = FastAPI(title="Global Resolution Test API")
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]

    app.state.principal_resolver = _DynamicPrincipalResolver(principal)
    app.state.session_factory = session_factory
    app.state.resolution_service = ResolutionService()

    app.include_router(resolve_router, prefix="/api/v1")
    return app


async def _seed_multi_workspace_fixtures(session: AsyncSession) -> dict[str, Any]:
    """Seed two workspaces ('ws-prod', 'ws-stage') with colliding and unique projects and issues."""
    user_id = uuid.uuid4()
    ws_prod_id = uuid.uuid4()
    ws_stage_id = uuid.uuid4()

    # Create ws-prod
    await session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, 'ws-prod', 'Production')"),
        {"id": ws_prod_id},
    )
    # Create ws-stage
    await session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, 'ws-stage', 'Staging')"),
        {"id": ws_stage_id},
    )

    # Principal for test user in ws-prod
    user_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name) "
            "VALUES (:id, 'USER', :ws, 'Operator')"
        ),
        {"id": user_id, "ws": ws_prod_id},
    )
    await session.execute(
        text(
            "SELECT register_object('user'::object_kind, :ws, NULL::uuid, "
            ":ckey, 'Operator', :creator, :id)"
        ),
        {"ws": ws_prod_id, "ckey": f"usr-{user_id.hex[:8]}", "creator": user_id, "id": user_id},
    )
    await session.execute(
        text(
            "INSERT INTO users (id, workspace_id, email) VALUES (:id, :ws, 'operator@example.com')"
        ),
        {"id": user_id, "ws": ws_prod_id},
    )

    # Principal for test user in ws-stage
    user_stage_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name) "
            "VALUES (:id, 'USER', :ws, 'Stage Operator')"
        ),
        {"id": user_stage_id, "ws": ws_stage_id},
    )
    await session.execute(
        text(
            "SELECT register_object('user'::object_kind, :ws, NULL::uuid, "
            ":ckey, 'Stage Operator', :creator, :id)"
        ),
        {
            "ws": ws_stage_id,
            "ckey": f"usr-{user_stage_id.hex[:8]}",
            "creator": user_stage_id,
            "id": user_stage_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO users (id, workspace_id, email) VALUES (:id, :ws, 'stage-op@example.com')"
        ),
        {"id": user_stage_id, "ws": ws_stage_id},
    )

    # Project API in ws-prod
    proj_api_prod_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object('project'::object_kind, :ws, NULL::uuid, "
            "'API', 'API Service Prod', :creator, :id)"
        ),
        {
            "ws": ws_prod_id,
            "creator": user_id,
            "id": proj_api_prod_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, identifier, name, modules_enabled) "
            "VALUES (:id, :ws, 'API', 'API Service Prod', true)"
        ),
        {"id": proj_api_prod_id, "ws": ws_prod_id},
    )

    # Project API in ws-stage
    proj_api_stage_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object('project'::object_kind, :ws, NULL::uuid, "
            "'API', 'API Service Stage', :creator, :id)"
        ),
        {
            "ws": ws_stage_id,
            "creator": user_stage_id,
            "id": proj_api_stage_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, identifier, name, modules_enabled) "
            "VALUES (:id, :ws, 'API', 'API Service Stage', true)"
        ),
        {"id": proj_api_stage_id, "ws": ws_stage_id},
    )

    # Unique project NETALERTXN in ws-stage
    proj_net_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object('project'::object_kind, :ws, NULL::uuid, "
            "'NETALERTXN', 'Network Alert', :creator, :id)"
        ),
        {
            "ws": ws_stage_id,
            "creator": user_stage_id,
            "id": proj_net_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, identifier, name, modules_enabled) "
            "VALUES (:id, :ws, 'NETALERTXN', 'Network Alert', true)"
        ),
        {"id": proj_net_id, "ws": ws_stage_id},
    )

    # Fetch default states and priorities
    st_prod = (
        await session.execute(
            text("SELECT id FROM workflow_states WHERE project_id = :p LIMIT 1"),
            {"p": proj_api_prod_id},
        )
    ).scalar_one()
    pr_prod = (
        await session.execute(
            text("SELECT id FROM project_priorities WHERE project_id = :p AND is_default = true"),
            {"p": proj_api_prod_id},
        )
    ).scalar_one()

    st_stage = (
        await session.execute(
            text("SELECT id FROM workflow_states WHERE project_id = :p LIMIT 1"),
            {"p": proj_api_stage_id},
        )
    ).scalar_one()
    pr_stage = (
        await session.execute(
            text("SELECT id FROM project_priorities WHERE project_id = :p AND is_default = true"),
            {"p": proj_api_stage_id},
        )
    ).scalar_one()

    st_net = (
        await session.execute(
            text("SELECT id FROM workflow_states WHERE project_id = :p LIMIT 1"),
            {"p": proj_net_id},
        )
    ).scalar_one()
    pr_net = (
        await session.execute(
            text("SELECT id FROM project_priorities WHERE project_id = :p AND is_default = true"),
            {"p": proj_net_id},
        )
    ).scalar_one()

    # Issue API-1 in ws-prod
    issue_prod_id = uuid.uuid4()
    await session.execute(
        text("UPDATE projects SET issue_seq_counter = 1 WHERE id = :id"),
        {"id": proj_api_prod_id},
    )
    await session.execute(
        text(
            "SELECT register_object('issue'::object_kind, :ws, :proj, "
            "'API-1', 'Prod Database Connection Pool', :creator, :id)"
        ),
        {
            "ws": ws_prod_id,
            "proj": proj_api_prod_id,
            "creator": user_id,
            "id": issue_prod_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO issues (id, workspace_id, project_id, sequence_id, "
            "state_id, priority_id, summary, created_by_id, board_rank) "
            "VALUES (:id, :ws, :proj, 1, :st, :pr, "
            "'Prod Database Connection Pool', :creator, '0|hzzzzz:')"
        ),
        {
            "id": issue_prod_id,
            "ws": ws_prod_id,
            "proj": proj_api_prod_id,
            "st": st_prod,
            "pr": pr_prod,
            "creator": user_id,
        },
    )

    # Issue API-1 in ws-stage
    issue_stage_id = uuid.uuid4()
    await session.execute(
        text("UPDATE projects SET issue_seq_counter = 1 WHERE id = :id"),
        {"id": proj_api_stage_id},
    )
    await session.execute(
        text(
            "SELECT register_object('issue'::object_kind, :ws, :proj, "
            "'API-1', 'Staging Database Connection Pool', :creator, :id)"
        ),
        {
            "ws": ws_stage_id,
            "proj": proj_api_stage_id,
            "creator": user_stage_id,
            "id": issue_stage_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO issues (id, workspace_id, project_id, sequence_id, "
            "state_id, priority_id, summary, created_by_id, board_rank) "
            "VALUES (:id, :ws, :proj, 1, :st, :pr, "
            "'Staging Database Connection Pool', :creator, '0|hzzzzz:')"
        ),
        {
            "id": issue_stage_id,
            "ws": ws_stage_id,
            "proj": proj_api_stage_id,
            "st": st_stage,
            "pr": pr_stage,
            "creator": user_stage_id,
        },
    )

    # Unique Issue NETALERTXN-12 in ws-stage
    issue_net_id = uuid.uuid4()
    await session.execute(
        text("UPDATE projects SET issue_seq_counter = 12 WHERE id = :id"),
        {"id": proj_net_id},
    )
    await session.execute(
        text(
            "SELECT register_object('issue'::object_kind, :ws, :proj, "
            "'NETALERTXN-12', 'Network Interface Flap Detected', :creator, :id)"
        ),
        {
            "ws": ws_stage_id,
            "proj": proj_net_id,
            "creator": user_stage_id,
            "id": issue_net_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO issues (id, workspace_id, project_id, sequence_id, "
            "state_id, priority_id, summary, created_by_id, board_rank) "
            "VALUES (:id, :ws, :proj, 12, :st, :pr, "
            "'Network Interface Flap Detected', :creator, '0|hzzzzz:')"
        ),
        {
            "id": issue_net_id,
            "ws": ws_stage_id,
            "proj": proj_net_id,
            "st": st_net,
            "pr": pr_net,
            "creator": user_stage_id,
        },
    )

    # Role bindings for operator
    await session.execute(
        text(
            "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:ws, :p, 'MEMBER', 'project', :proj)"
        ),
        {"ws": ws_prod_id, "p": user_id, "proj": proj_api_prod_id},
    )
    await session.execute(
        text(
            "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:ws, :p, 'MEMBER', 'project', :proj)"
        ),
        {"ws": ws_stage_id, "p": user_stage_id, "proj": proj_api_stage_id},
    )
    await session.execute(
        text(
            "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:ws, :p, 'MEMBER', 'project', :proj)"
        ),
        {"ws": ws_stage_id, "p": user_stage_id, "proj": proj_net_id},
    )

    await session.execute(
        text("SELECT rebuild_effective_access_for_workspace(:ws)"),
        {"ws": ws_prod_id},
    )
    await session.execute(
        text("SELECT rebuild_effective_access_for_workspace(:ws)"),
        {"ws": ws_stage_id},
    )

    return {
        "user_id": user_id,
        "ws_prod_id": ws_prod_id,
        "ws_stage_id": ws_stage_id,
        "issue_prod_id": issue_prod_id,
        "issue_stage_id": issue_stage_id,
        "issue_net_id": issue_net_id,
    }


@pytest.mark.committed_db
@pytest.mark.asyncio
async def test_global_resolution_unique_key(
    pg_worker_db: AsyncEngine,
    committed_db_session: AsyncSession,
) -> None:
    """Global resolution finds globally unique issue key across workspaces."""
    seed = await _seed_multi_workspace_fixtures(committed_db_session)
    await committed_db_session.commit()
    session_factory = RLSSessionFactory(pg_worker_db)

    principal = PrincipalContext(
        principal_id=seed["user_id"],
        workspace_id=seed["ws_prod_id"],
        scope_tier="global",
    )
    app = _build_app(principal, session_factory)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/resolve", params={"kind": "issue", "ref": "NETALERTXN-12"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(seed["issue_net_id"])
        assert data["key"] == "NETALERTXN-12"
        assert data["workspace"] == "ws-stage"


@pytest.mark.committed_db
@pytest.mark.asyncio
async def test_global_resolution_ambiguous_identifier(
    pg_worker_db: AsyncEngine,
    committed_db_session: AsyncSession,
) -> None:
    """Global resolution returns 409 AMBIGUOUS_IDENTIFIER when key exists in multiple workspaces."""
    seed = await _seed_multi_workspace_fixtures(committed_db_session)
    await committed_db_session.commit()
    session_factory = RLSSessionFactory(pg_worker_db)

    principal = PrincipalContext(
        principal_id=seed["user_id"],
        workspace_id=seed["ws_prod_id"],
        scope_tier="global",
    )
    app = _build_app(principal, session_factory)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/resolve", params={"kind": "issue", "ref": "API-1"})
        assert resp.status_code == 409
        problem = resp.json()
        assert problem["code"] == "AMBIGUOUS_IDENTIFIER"
        candidates = problem.get("candidates", [])
        assert len(candidates) == 2
        candidate_ws = {c.get("workspace") for c in candidates}
        assert candidate_ws == {"ws-prod", "ws-stage"}
        assert "pass workspace=" in problem.get("hint", "")

    # Also directly verify resolve_issue_ref service handles ambiguity and workspace_ref
    rls_ctx = RLSContext(
        principal_id=seed["user_id"],
        workspace_id=seed["ws_prod_id"],
    )
    async with session_factory.session(rls_ctx) as rls_sess:
        with pytest.raises(ProblemException) as exc_ambig:
            await resolve_issue_ref(rls_sess, principal, "API-1")
        assert exc_ambig.value.status == 409
        assert exc_ambig.value.code == "AMBIGUOUS_IDENTIFIER"

        # Disambiguated by workspace_ref
        iss_prod = await resolve_issue_ref(rls_sess, principal, "API-1", workspace_ref="ws-prod")
        assert iss_prod.id == seed["issue_prod_id"]


@pytest.mark.committed_db
@pytest.mark.asyncio
async def test_scoped_resolution_disambiguates(
    pg_worker_db: AsyncEngine,
    committed_db_session: AsyncSession,
) -> None:
    """Constraining resolution via workspace query param or header returns exact workspace issue."""
    seed = await _seed_multi_workspace_fixtures(committed_db_session)
    await committed_db_session.commit()
    session_factory = RLSSessionFactory(pg_worker_db)

    principal = PrincipalContext(
        principal_id=seed["user_id"],
        workspace_id=seed["ws_prod_id"],
        scope_tier="global",
    )
    app = _build_app(principal, session_factory)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 1. Via query param workspace=ws-prod
        resp_prod = await client.get(
            "/api/v1/resolve",
            params={"kind": "issue", "ref": "API-1", "workspace": "ws-prod"},
        )
        assert resp_prod.status_code == 200
        data_prod = resp_prod.json()
        assert data_prod["id"] == str(seed["issue_prod_id"])
        assert data_prod["workspace"] == "ws-prod"

        # 2. Via header x-kb-scope-workspace: ws-stage
        resp_stage = await client.get(
            "/api/v1/resolve",
            params={"kind": "issue", "ref": "API-1"},
            headers={"x-kb-scope-workspace": "ws-stage"},
        )
        assert resp_stage.status_code == 200
        data_stage = resp_stage.json()
        assert data_stage["id"] == str(seed["issue_stage_id"])
        assert data_stage["workspace"] == "ws-stage"


@pytest.mark.committed_db
@pytest.mark.asyncio
async def test_workspace_scoped_token_hard_ceiling(
    pg_worker_db: AsyncEngine,
    committed_db_session: AsyncSession,
) -> None:
    """A workspace-scoped token cannot resolve issues in a foreign workspace."""
    seed = await _seed_multi_workspace_fixtures(committed_db_session)
    await committed_db_session.commit()
    session_factory = RLSSessionFactory(pg_worker_db)

    # Token scoped strictly to ws_prod
    principal = PrincipalContext(
        principal_id=seed["user_id"],
        workspace_id=seed["ws_prod_id"],
        scope_tier="workspace",
    )
    app = _build_app(principal, session_factory)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # API-1 resolves cleanly to ws-prod
        resp_prod = await client.get("/api/v1/resolve", params={"kind": "issue", "ref": "API-1"})
        assert resp_prod.status_code == 200
        assert resp_prod.json()["id"] == str(seed["issue_prod_id"])

        # NETALERTXN-12 in ws-stage returns 404
        resp_foreign = await client.get(
            "/api/v1/resolve", params={"kind": "issue", "ref": "NETALERTXN-12"}
        )
        assert resp_foreign.status_code == 404
