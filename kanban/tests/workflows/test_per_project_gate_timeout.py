# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Feature unit tests for per-project and per-hook gate timeouts up to 600s (KAN-437).

Tests cover:
1. Pure precedence resolution in resolve_effective_gate_timeout_ms (hook -> project -> agent)
2. Range boundaries [1000, 600000] ms and clamping
3. Project API: create and patch validation (422 on <1000 or >600000), clearing with null
4. Hook API: create and update validation (422 on <1000 or >600000), clearing with null
5. AsyncGate invocation deadline_at computation and gate_sweeper future-deadline protection
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from database.models.agent_definition import AgentDefinition
from database.models.principals import Principal
from database.models.projects import Project, WorkflowState
from database.models.workflow import WorkflowHookInvocation, WorkflowTransitionHook
from kanban.api.v1.schemas.projects import ProjectCreate, ProjectPatch
from kanban.workflows.gate_sweeper import GateTimeoutSweeper
from kanban.workflows.gate_types import resolve_effective_gate_timeout_ms
from kanban.workflows.hooks_service import (
    WorkflowHookCreateRequest,
    WorkflowHookUpdateRequest,
)
from kanban.workflows.manifest import compute_hook_manifest_sha256

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


def test_resolve_effective_gate_timeout_ms_precedence() -> None:
    """Precedence must be hook -> project -> agent -> fallback (60000)."""
    # 1. Fallback default
    assert resolve_effective_gate_timeout_ms(None, None, None) == 60000
    assert resolve_effective_gate_timeout_ms(None, None, None, fallback_default_ms=45000) == 45000

    # 2. Agent definition overrides fallback
    assert resolve_effective_gate_timeout_ms(None, None, 120000) == 120000

    # 3. Project default overrides agent definition
    assert resolve_effective_gate_timeout_ms(None, 180000, 120000) == 180000

    # 4. Hook override takes highest precedence
    assert resolve_effective_gate_timeout_ms(600000, 180000, 120000) == 600000


def test_resolve_effective_gate_timeout_ms_clamping() -> None:
    """All timeout values must be strictly clamped between 1000 and 600000 ms."""
    assert resolve_effective_gate_timeout_ms(500, None, None) == 1000
    assert resolve_effective_gate_timeout_ms(1_000_000, None, None) == 600000
    assert resolve_effective_gate_timeout_ms(None, 200, None) == 1000
    assert resolve_effective_gate_timeout_ms(None, 900_000, None) == 600000
    assert resolve_effective_gate_timeout_ms(None, None, 100) == 1000
    assert resolve_effective_gate_timeout_ms(None, None, 800_000) == 600000


def test_project_schema_gate_timeout_validation() -> None:
    """Project create and patch schemas must enforce [1000, 600000] and allow None."""
    # Valid bounds
    req1 = ProjectCreate(name="P1", identifier="PONE", default_gate_timeout_ms=1000)
    assert req1.default_gate_timeout_ms == 1000
    req2 = ProjectCreate(name="P2", identifier="PTWO", default_gate_timeout_ms=600000)
    assert req2.default_gate_timeout_ms == 600000
    req3 = ProjectCreate(name="P3", identifier="PTHREE", default_gate_timeout_ms=None)
    assert req3.default_gate_timeout_ms is None

    # Invalid bounds (<1000 or >600000)
    with pytest.raises(ValidationError):
        ProjectCreate(name="Bad1", identifier="BAD1", default_gate_timeout_ms=999)

    with pytest.raises(ValidationError):
        ProjectCreate(name="Bad2", identifier="BAD2", default_gate_timeout_ms=600001)

    # Patch schema
    patch1 = ProjectPatch(default_gate_timeout_ms=300000)
    assert patch1.default_gate_timeout_ms == 300000
    patch_clear = ProjectPatch(default_gate_timeout_ms=None)
    assert patch_clear.default_gate_timeout_ms is None
    assert "default_gate_timeout_ms" in patch_clear.model_fields_set

    with pytest.raises(ValidationError):
        ProjectPatch(default_gate_timeout_ms=500)

    with pytest.raises(ValidationError):
        ProjectPatch(default_gate_timeout_ms=700000)


def test_workflow_hook_schema_gate_timeout_validation() -> None:
    """Workflow hook schemas must enforce [1000, 600000] and allow None."""
    hook_req1 = WorkflowHookCreateRequest(
        name="Hook 1",
        from_state="In Progress",
        to_state="Done",
        hook_kind="agent_interceptor",
        timeout_ms=1000,
    )
    assert hook_req1.timeout_ms == 1000

    hook_req2 = WorkflowHookCreateRequest(
        name="Hook 2",
        from_state="In Progress",
        to_state="Done",
        hook_kind="agent_interceptor",
        timeout_ms=600000,
    )
    assert hook_req2.timeout_ms == 600000

    hook_req3 = WorkflowHookCreateRequest(
        name="Hook 3",
        from_state="In Progress",
        to_state="Done",
        hook_kind="agent_interceptor",
        timeout_ms=None,
    )
    assert hook_req3.timeout_ms is None

    with pytest.raises(ValidationError):
        WorkflowHookCreateRequest(
            name="Bad Hook 1",
            from_state="In Progress",
            to_state="Done",
            hook_kind="agent_interceptor",
            timeout_ms=500,
        )

    with pytest.raises(ValidationError):
        WorkflowHookCreateRequest(
            name="Bad Hook 2",
            from_state="In Progress",
            to_state="Done",
            hook_kind="agent_interceptor",
            timeout_ms=600001,
        )

    # Update hook schema
    update_req = WorkflowHookUpdateRequest(timeout_ms=450000)
    assert update_req.timeout_ms == 450000
    update_clear = WorkflowHookUpdateRequest(timeout_ms=None)
    assert update_clear.timeout_ms is None
    assert "timeout_ms" in update_clear.model_fields_set

    with pytest.raises(ValidationError):
        WorkflowHookUpdateRequest(timeout_ms=999)

    with pytest.raises(ValidationError):
        WorkflowHookUpdateRequest(timeout_ms=650000)


async def test_gate_sweeper_future_deadline_not_expired(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Gate sweeper must not expire running invocations whose deadline_at is in the future."""
    session = api_env.seed
    ws_id = api_env.workspace_id
    admin = await make_user("sw_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("SWP", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # Patch project default gate timeout
    proj = await session.get(Project, proj_id)
    assert proj is not None
    proj.default_gate_timeout_ms = 300000
    await session.commit()

    # Get states
    stmt = select(WorkflowState.name, WorkflowState.id).where(WorkflowState.project_id == proj_id)
    states = {str(r[0]): r[1] for r in (await session.execute(stmt)).all()}
    in_prog_id = states["In Progress"]
    done_id = states["Done"]

    # Provision agent definition with 60s timeout
    agent_p = Principal(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        principal_type="AGENT",
        display_name="Sweeper Agent",
    )
    session.add(agent_p)
    await session.flush()

    agent_def = AgentDefinition(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        principal_id=agent_p.id,
        slug="sweeper-agent",
        display_name="Sweeper Agent",
        harness_kind="in_app_sdk",
        provider_kind="gemini",
        model_id="gemini-3.8-flash",
        timeout_ms=60000,
    )
    session.add(agent_def)

    # Create hook with 600,000 ms override (10 minutes)
    manifest_sha = compute_hook_manifest_sha256(
        hook_kind="agent_interceptor",
        wasm_module_sha256=None,
        agent_definition_id=agent_def.id,
        allowed_mutable_fields=[],
        failure_policy="fail_closed",
        from_state_id=in_prog_id,
        to_state_id=done_id,
    )
    hook = WorkflowTransitionHook(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        project_id=proj_id,
        from_state_id=in_prog_id,
        to_state_id=done_id,
        sort_rank="10",
        name="ten_min_gate",
        hook_kind="agent_interceptor",
        is_enabled=True,
        agent_definition_id=agent_def.id,
        allowed_mutable_fields=[],
        failure_policy="fail_closed",
        manifest_sha256=manifest_sha,
        timeout_ms=600000,
    )
    session.add(hook)
    await session.commit()

    # Create issue in In Progress
    create_resp = await client.post(
        "/api/v1/projects/SWP/issues",
        json={
            "summary": "Sweeper Issue",
            "description_markdown": "Test",
            "state_id": str(in_prog_id),
        },
    )
    assert create_resp.status_code == 201
    issue_key = create_resp.json()["key"]

    # Trigger transition to Done -> enters pending_async with 600s deadline
    t_resp = await client.post(
        f"/api/v1/issues/{issue_key}/transitions",
        json={"to_state": "Done"},
    )
    assert t_resp.status_code == 202
    exec_id = uuid.UUID(t_resp.json()["execution_id"])

    await session.rollback()
    inv = (
        await session.execute(
            select(WorkflowHookInvocation).where(
                WorkflowHookInvocation.execution_id == exec_id,
                WorkflowHookInvocation.hook_id == hook.id,
            )
        )
    ).scalar_one()

    # Invariant: deadline_at must be populated to started_at + 600,000 ms (10 minutes)
    assert inv.deadline_at is not None
    assert int((inv.deadline_at - inv.started_at).total_seconds()) == 600

    # At 8 minutes (480s), sweeper does NOT expire the running invocation
    clock_8m = inv.started_at + dt.timedelta(minutes=8)
    swept_8m = await GateTimeoutSweeper.run_once(session, now=clock_8m)
    assert swept_8m == 0

    await session.refresh(inv)
    assert inv.status == "running"

    # At 10 minutes + 1s (601s), sweeper expires the invocation
    clock_10m1s = inv.started_at + dt.timedelta(seconds=601)
    swept_expired = await GateTimeoutSweeper.run_once(session, now=clock_10m1s)
    assert swept_expired == 1

    await session.refresh(inv)
    assert inv.status == "timed_out"
