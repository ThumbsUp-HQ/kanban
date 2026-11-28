# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Regression: wait=true gate-hold on a wildcard Done hook under real RLS."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from database.models.projects import WorkflowState
from kanban.tests.workflows.test_async_gate import create_agent_definition, create_agent_hook

if TYPE_CHECKING:
    import uuid
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


@pytest.mark.parametrize("route", ["complete-work"])
async def test_wait_true_wildcard_done_gate(
    route: str,
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """A non-admin MEMBER caller dispatching a Done gate must get the hold, not a 500 (42501)."""
    owner = await make_user("w_owner", workspace_role="WORKSPACE_ADMIN")
    admin = await make_user("w_member", workspace_role="WORKSPACE_MEMBER")
    proj = await make_project(
        "WGP", created_by=owner, roles={owner: "PROJECT_ADMIN", admin: "MEMBER"}
    )
    client = as_principal(admin)
    rows = (
        await api_env.seed.execute(
            select(WorkflowState.name, WorkflowState.id).where(WorkflowState.project_id == proj)
        )
    ).all()
    states = {str(r[0]): r[1] for r in rows}
    agent_def, _ = await create_agent_definition(api_env.seed, api_env.workspace_id, proj)
    await create_agent_hook(
        api_env.seed, api_env.workspace_id, proj, agent_def.id, to_state_id=states["Done"]
    )
    created = await client.post(
        "/api/v1/projects/WGP/issues",
        json={"summary": "g", "description_markdown": "b", "state_id": str(states["In Progress"])},
    )
    assert created.status_code == 201, created.text
    key = created.json()["key"]
    await api_env.seed.rollback()
    bw = await client.post(f"/api/v1/issues/{key}/begin-work", json={"plan_markdown": "plan"})
    assert bw.status_code == 200, bw.text
    await api_env.seed.rollback()
    body: dict[str, object] = (
        {"to_state": "Done"} if route == "transition" else {"summary_markdown": "done"}
    )
    resp = await client.post(
        f"/api/v1/issues/{key}/{route}?wait=true&wait_timeout_ms=600", json=body
    )

    assert resp.status_code == 202, resp.text
    assert resp.json()["status"] == "pending_agent_gate"
