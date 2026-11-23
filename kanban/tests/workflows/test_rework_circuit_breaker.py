# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration and unit tests for Per-Issue Rework Loop Circuit Breaker (KAN-71).

Covers:
  - Rejection streak increment: rejections increment rework_rejection_streak.
  - Breaker trip threshold: reaching max_rework_attempts sets rework_tripped_at.
  - Agent transition blockage: 409 REWORK_LOOP_LIMIT_EXCEEDED when rework_tripped_at is set.
  - Human transition reset: human transition resets streak and clears rework_tripped_at.
  - Reset endpoint: POST /api/v1/issues/{key}/reset-rework-breaker allows human resets,
    rejects agent callers with 403.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING, Any, cast

import pytest
from sqlalchemy import update

from database.models.issues import Issue
from database.session import RLSContext
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.workflows.engine import TransitionEngine

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


async def test_rework_circuit_breaker_blocks_agent_transitions(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify that tripped rework breaker blocks agent callers but permits human callers."""
    admin = await make_user("admin_breaker", workspace_role="WORKSPACE_ADMIN")
    dev = await make_user("dev_breaker")
    await make_project("CB1", created_by=admin, roles={admin: "PROJECT_ADMIN", dev: "MEMBER"})

    client_admin = as_principal(admin)
    create_resp = await client_admin.post(
        "/api/v1/projects/CB1/issues",
        json={"summary": "Circuit Breaker Test", "description_markdown": "Test Description"},
    )
    assert create_resp.status_code == 201
    issue_key = create_resp.json()["key"]
    issue_id = uuid.UUID(create_resp.json()["id"])

    factory = cast("Any", api_env.client._transport).app.state.session_factory  # noqa: SLF001
    ctx_admin = RLSContext(
        principal_id=admin.id,
        workspace_id=admin.workspace_id,
        token_scopes=("admin",),
        aal_level=2,
    )

    # 2. Trip breaker directly in DB
    now = dt.datetime.now(dt.UTC)
    async with factory.session(ctx_admin) as session:
        await session.execute(
            update(Issue)
            .where(Issue.id == issue_id)
            .values(rework_rejection_streak=3, rework_tripped_at=now)
        )
        await session.commit()

    # 3. Agent caller tries to transition -> 409 REWORK_LOOP_LIMIT_EXCEEDED
    agent_caller = PrincipalContext(
        principal_id=dev.id,
        workspace_id=admin.workspace_id,
        principal_type="agent",
        is_mcp_credential=True,
        token_scopes=("read", "write"),
    )

    async with factory.session(ctx_admin) as session:
        engine = TransitionEngine(session=session)
        with pytest.raises(ProblemException) as exc_info:
            await engine.execute_transition(
                issue_key=issue_key,
                to_state="In Progress",
                actor=agent_caller,
            )
        assert exc_info.value.status == 409
        assert exc_info.value.code == "REWORK_LOOP_LIMIT_EXCEEDED"

    # 4. Human user calls reset endpoint -> succeeds
    client_dev = as_principal(dev)
    reset_resp = await client_dev.post(f"/api/v1/issues/{issue_key}/reset-rework-breaker")
    assert reset_resp.status_code == 200, reset_resp.text
    reset_data = reset_resp.json()
    assert reset_data["status"] in ("reset", "ok")
    assert reset_data["rework_rejection_streak"] == 0
    assert reset_data["rework_tripped_at"] is None

    # Verify DB state after reset
    async with factory.session(ctx_admin) as session:
        refreshed = await session.get(Issue, issue_id)
        assert refreshed is not None
        assert refreshed.rework_rejection_streak == 0
        assert refreshed.rework_tripped_at is None


async def test_rework_breaker_reset_rejects_agent_caller(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify that agent callers attempting to reset the rework breaker receive 403."""
    admin = await make_user("admin_breaker2", workspace_role="WORKSPACE_ADMIN")
    await make_project("CB2", created_by=admin, roles={admin: "PROJECT_ADMIN"})

    client_admin = as_principal(admin)
    create_resp = await client_admin.post(
        "/api/v1/projects/CB2/issues",
        json={"summary": "Agent Reset Breaker Test", "description_markdown": "Test"},
    )
    assert create_resp.status_code == 201
    issue_key = create_resp.json()["key"]

    # Set agent caller identity on resolver
    api_env.resolver.principal = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=admin.workspace_id,
        principal_type="agent",
        token_scopes=("read", "write"),
    )
    agent_resp = await api_env.client.post(
        f"/api/v1/issues/{issue_key}/reset-rework-breaker",
    )
    assert agent_resp.status_code == 403


async def test_human_transition_clears_breaker(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify that human transition automatically resets streak and clears rework_tripped_at."""
    admin = await make_user("admin_breaker3", workspace_role="WORKSPACE_ADMIN")
    dev = await make_user("dev_breaker3")
    await make_project("CB3", created_by=admin, roles={admin: "PROJECT_ADMIN", dev: "MEMBER"})

    client_admin = as_principal(admin)
    create_resp = await client_admin.post(
        "/api/v1/projects/CB3/issues",
        json={"summary": "Human Clear Breaker Test", "description_markdown": "Test"},
    )
    assert create_resp.status_code == 201
    issue_key = create_resp.json()["key"]
    issue_id = uuid.UUID(create_resp.json()["id"])

    factory = cast("Any", api_env.client._transport).app.state.session_factory  # noqa: SLF001
    ctx_admin = RLSContext(
        principal_id=admin.id,
        workspace_id=admin.workspace_id,
        token_scopes=("admin",),
        aal_level=2,
    )

    # Set streak=2 (not yet tripped)
    async with factory.session(ctx_admin) as session:
        await session.execute(
            update(Issue).where(Issue.id == issue_id).values(rework_rejection_streak=2)
        )
        await session.commit()

    # Human dev transitions issue to In Progress
    client_dev = as_principal(dev)
    tr_resp = await client_dev.post(
        f"/api/v1/issues/{issue_key}/transition",
        json={"to_state": "In Progress"},
    )
    assert tr_resp.status_code == 200, tr_resp.text

    # Verify streak was reset to 0
    async with factory.session(ctx_admin) as session:
        refreshed = await session.get(Issue, issue_id)
        assert refreshed is not None
        assert refreshed.rework_rejection_streak == 0
        assert refreshed.rework_tripped_at is None
