"""Unit tests for objects access manifest endpoint, agent kill-switch, and timing (S3.4)."""

from __future__ import annotations

import json
import os
import statistics
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from database.models import ActivityRecord
from database.session import RLSSessionFactory
from database.testing.pg_harness import build_dsn
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.api.v1.objects_access import agent_kill_switch, get_object_access_manifest
from kanban.app import create_app
from kanban.security.permissions import Capability
from kanban.tests.security.helpers import (
    add_acl_entry,
    add_group_member,
    add_role_binding,
    create_agent,
    create_group,
    create_project,
    create_registered_object,
    create_user,
    create_workspace,
    rebuild_era,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class _TestPrincipalResolver:
    """Configurable resolver returning a dynamic PrincipalContext for tests."""

    def __init__(self, principal: PrincipalContext | None = None) -> None:
        self.principal = principal

    async def resolve(self, request: Any) -> PrincipalContext | None:  # noqa: ANN401
        del request
        return self.principal


@dataclass(frozen=True, slots=True)
class _TestSetupData:
    ws_id: uuid.UUID
    admin_id: uuid.UUID
    viewer_id: uuid.UUID
    outsider_id: uuid.UUID
    agent_id: uuid.UUID
    issue_id: uuid.UUID
    sec_id: uuid.UUID


async def _setup_test_entities(session: AsyncSession) -> _TestSetupData:
    """Seed test workspace, users, agent, project, and registered objects."""
    ws_id = await create_workspace(session, name="Platform Engineering")

    admin_id = await create_user(session, ws_id, handle="@admin_user", display_name="Admin User")
    viewer_id = await create_user(session, ws_id, handle="@viewer_user", display_name="Viewer User")
    outsider_id = await create_user(
        session, ws_id, handle="@outsider_user", display_name="Outsider User"
    )
    guest_id = await create_user(
        session,
        ws_id,
        handle="@guest_ext",
        display_name="Guest Partner",
        email="partner@vendor.example",
    )
    agent_id = await create_agent(session, ws_id, "Codebot (openai/gpt-4o)", principal_type="AGENT")

    g_core = await create_group(
        session,
        ws_id,
        "Core Platform Team",
        external_source="LDAP",
        external_id="cn=core,dc=corp",
    )
    g_contractors = await create_group(session, ws_id, "Third-Party Contractors")

    u_core = await create_user(session, ws_id, handle="@core_member", display_name="Core Member")
    await add_group_member(session, ws_id, g_core, u_core)

    proj_id = await create_project(
        session, ws_id, identifier="KAN", name="Kanban", created_by_id=admin_id
    )

    issue_id = await create_registered_object(
        session,
        ws_id,
        kind="issue",
        key="KAN-1",
        title="Primary Task",
        project_id=proj_id,
        created_by_id=admin_id,
    )
    sec_id = await create_registered_object(
        session,
        ws_id,
        kind="issue",
        key="SEC-1",
        title="Confidential Secret",
        project_id=proj_id,
        created_by_id=admin_id,
    )

    await add_role_binding(session, ws_id, admin_id, role="WORKSPACE_ADMIN", scope_type="workspace")
    await add_role_binding(
        session, ws_id, viewer_id, role="WORKSPACE_MEMBER", scope_type="workspace"
    )
    await add_role_binding(session, ws_id, guest_id, role="WORKSPACE_GUEST", scope_type="workspace")
    await add_role_binding(
        session, ws_id, admin_id, role="PROJECT_ADMIN", scope_type="project", project_id=proj_id
    )
    await add_role_binding(
        session, ws_id, viewer_id, role="VIEWER", scope_type="project", project_id=proj_id
    )
    await add_role_binding(
        session, ws_id, agent_id, role="VIEWER", scope_type="project", project_id=proj_id
    )
    await add_role_binding(
        session, ws_id, g_core, role="MEMBER", scope_type="project", project_id=proj_id
    )

    # Direct ALLOW ACL for group
    await add_acl_entry(
        session,
        ws_id,
        issue_id,
        g_core,
        effect="ALLOW",
        capability_mask=Capability.VIEW | Capability.COMMENT,
    )
    # Out of boundary direct grant on issue_id to guest
    await add_acl_entry(
        session, ws_id, issue_id, guest_id, effect="ALLOW", capability_mask=Capability.VIEW
    )
    # Ephemeral principal grant for out-of-boundary redaction
    ephemeral_id = await create_agent(
        session, ws_id, "Ephemeral Script Token", principal_type="SCRIPT_EPHEMERAL"
    )
    await add_acl_entry(
        session, ws_id, issue_id, ephemeral_id, effect="ALLOW", capability_mask=Capability.VIEW
    )
    # Direct DENY on issue_id to contractors
    await add_acl_entry(
        session, ws_id, issue_id, g_contractors, effect="DENY", capability_mask=Capability.EDIT
    )

    await add_acl_entry(
        session, ws_id, sec_id, outsider_id, effect="DENY", capability_mask=Capability.ALL
    )

    await rebuild_era(session, ws_id)
    await session.commit()

    return _TestSetupData(
        ws_id=ws_id,
        admin_id=admin_id,
        viewer_id=viewer_id,
        outsider_id=outsider_id,
        agent_id=agent_id,
        issue_id=issue_id,
        sec_id=sec_id,
    )


async def _verify_access_and_kill_switch(
    client: httpx.AsyncClient,
    resolver: _TestPrincipalResolver,
    data: _TestSetupData,
    db_session: AsyncSession,
) -> None:
    """Verify co-viewer GET, 403 on VIEW-only kill switch, and ADMIN kill switch execution."""
    # Step A: Co-viewer GET returns 200
    resolver.principal = PrincipalContext(
        principal_id=data.viewer_id, workspace_id=data.ws_id, token_scopes=("session",)
    )
    res_a = await client.get(f"/api/v1/objects/{data.issue_id}/access")
    assert res_a.status_code == 200
    data_a = res_a.json()
    assert "pill_label" in data_a
    assert any(u["handle"] == "@viewer_user" for u in data_a["users"])
    assert any(ag["display_name"] == "Codebot (openai/gpt-4o)" for ag in data_a["agents"])
    assert len(data_a["groups"]) >= 1
    assert len(data_a["deny_overrides"]) >= 1
    assert data_a["redacted_count"] >= 1
    assert len(data_a["redacted_entries"]) >= 1

    # Step B: VIEW-only caller kill-switch returns 403 INSUFFICIENT_CAPABILITY
    res_b = await client.post(f"/api/v1/objects/{data.issue_id}/access/agent-kill-switch")
    assert res_b.status_code == 403
    assert res_b.json()["code"] == "INSUFFICIENT_CAPABILITY"

    # Step C: Caller lacking VIEW kill-switch returns 404 NOT_FOUND
    resolver.principal = PrincipalContext(
        principal_id=data.outsider_id, workspace_id=data.ws_id, token_scopes=("session",)
    )
    res_c = await client.post(f"/api/v1/objects/{data.issue_id}/access/agent-kill-switch")
    assert res_c.status_code == 404
    assert res_c.json()["code"] == "NOT_FOUND"

    # Step C2: 404 response on unreadable GET
    res_404 = await client.get(f"/api/v1/objects/{data.sec_id}/access")
    assert res_404.status_code == 404
    assert res_404.json()["code"] == "NOT_FOUND"

    # Write contract-sample.json QA proof
    contract_payload = {
        "description": (
            "Captured HTTP wire contract samples for KANBA-59 (KB-P2-11) "
            "access manifest and anti-enumeration endpoints"
        ),
        "endpoints": {
            "get_object_access_manifest": {
                "route": "GET /api/v1/objects/{object_id}/access",
                "responses": {
                    "200_OK": {
                        "status_code": 200,
                        "description": (
                            "Full AccessManifest serialization including users, "
                            "groups, agents, deny_overrides, and redacted_entries"
                        ),
                        "payload": data_a,
                    },
                    "404_NOT_FOUND": {
                        "status_code": 404,
                        "description": (
                            "RFC 9457 Problem Details for non-existent or unreadable "
                            "object (jitter-equalized anti-enumeration)"
                        ),
                        "payload": res_404.json(),
                    },
                },
            },
            "agent_kill_switch": {
                "route": "POST /api/v1/objects/{object_id}/access/agent-kill-switch",
                "responses": {
                    "403_INSUFFICIENT_CAPABILITY": {
                        "status_code": 403,
                        "description": (
                            "RFC 9457 Problem Details when caller lacks SHARE "
                            "or ADMIN capability to invoke kill-switch"
                        ),
                        "payload": res_b.json(),
                    }
                },
            },
        },
    }
    contract_file = (
        Path(__file__).resolve().parents[3]  # noqa: ASYNC240
        / "docs"
        / "qa"
        / "KANBA-59"
        / "contract-sample.json"
    )
    contract_file.parent.mkdir(parents=True, exist_ok=True)
    contract_file.write_text(json.dumps(contract_payload, indent=2), encoding="utf-8")

    # Step D: ADMIN caller executes kill-switch
    resolver.principal = PrincipalContext(
        principal_id=data.admin_id, workspace_id=data.ws_id, token_scopes=("session",)
    )
    res_d = await client.post(f"/api/v1/objects/{data.issue_id}/access/agent-kill-switch")
    assert res_d.status_code == 200
    data_d = res_d.json()
    assert data_d["agents"] == []
    assert any(
        override["principal_type"] == "AGENT" and "VIEW" in override["denied_capabilities"]
        for override in data_d["deny_overrides"]
    )

    act_stmt = (
        select(ActivityRecord)
        .where(
            ActivityRecord.object_id == data.issue_id,
            ActivityRecord.event_type == "AGENT_ACCESS_KILLED",
        )
        .order_by(ActivityRecord.recorded_at.desc())
    )
    act_record = (await db_session.execute(act_stmt)).scalar_one_or_none()
    assert act_record is not None
    assert act_record.actor_id == data.admin_id

    # Agent subsequent access receives 404
    resolver.principal = PrincipalContext(
        principal_id=data.agent_id, workspace_id=data.ws_id, token_scopes=("session",)
    )
    res_agent = await client.get(f"/api/v1/objects/{data.issue_id}/access")
    assert res_agent.status_code == 404


async def _run_timing_equalization(
    client: httpx.AsyncClient,
    resolver: _TestPrincipalResolver,
    data: _TestSetupData,
) -> None:
    """Execute 100 alternating requests asserting <= 5.0ms delta and indistinguishable 404s."""
    resolver.principal = PrincipalContext(
        principal_id=data.outsider_id, workspace_id=data.ws_id, token_scopes=("session",)
    )

    times_nonexistent: list[float] = []
    times_unreadable: list[float] = []

    for _ in range(50):
        rand_uuid = uuid.uuid4()
        t0 = time.perf_counter()
        r_nonexistent = await client.get(f"/api/v1/objects/{rand_uuid}/access")
        t1 = time.perf_counter()
        assert r_nonexistent.status_code == 404
        times_nonexistent.append((t1 - t0) * 1000.0)

        t2 = time.perf_counter()
        r_unreadable = await client.get(f"/api/v1/objects/{data.sec_id}/access")
        t3 = time.perf_counter()
        assert r_unreadable.status_code == 404
        times_unreadable.append((t3 - t2) * 1000.0)

        hdrs_a = {
            k.lower(): v
            for k, v in r_nonexistent.headers.items()
            if k.lower() not in ("x-request-id", "date")
        }
        hdrs_b = {
            k.lower(): v
            for k, v in r_unreadable.headers.items()
            if k.lower() not in ("x-request-id", "date")
        }
        assert hdrs_a == hdrs_b

        body_a = {
            k: v for k, v in r_nonexistent.json().items() if k not in ("request_id", "instance")
        }
        body_b = {
            k: v for k, v in r_unreadable.json().items() if k not in ("request_id", "instance")
        }
        assert body_a == body_b
        assert body_a["code"] == "NOT_FOUND"

    median_a = statistics.median(times_nonexistent)
    median_b = statistics.median(times_unreadable)
    p95_a = sorted(times_nonexistent)[int(0.95 * len(times_nonexistent))]
    p95_b = sorted(times_unreadable)[int(0.95 * len(times_unreadable))]
    delta_median = abs(median_a - median_b)

    proof_dir = Path("docs/qa/KANBA-59")
    proof_dir.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240
    stats_path = proof_dir / "timing-equalization.txt"
    stats_text = (
        "KANBA-59 / KB-P2-11 Timing Equalization Statistical Verification (S3.4)\n"
        "=========================================================================\n"
        f"Samples per class:      50 alternating pairs (100 requests total)\n"
        f"Floor Duration:         25.0 ms\n"
        f"Class A (Non-existent): Median = {median_a:.3f} ms | p95 = {p95_a:.3f} ms\n"
        f"Class B (Unreadable):   Median = {median_b:.3f} ms | p95 = {p95_b:.3f} ms\n"
        f"Median Delta:           {delta_median:.3f} ms (Mandate: <= 5.0 ms)\n"
        f"Anti-enumeration Check: PASS (Indistinguishable 404 status, headers & body)\n"
    )
    stats_path.write_text(stats_text, encoding="utf-8")

    assert delta_median <= 5.0, (
        f"Timing equalization exceeded tolerance: delta={delta_median:.2f}ms > 5.0ms"
    )


@pytest.mark.committed_db
@pytest.mark.asyncio
async def test_case_8_objects_access_and_kill_switch(
    committed_db_session: AsyncSession,
    pg_worker_db: AsyncEngine,
) -> None:
    """Test Case 8: Endpoint, agent kill-switch, and statistical timing equalization (S3.4)."""
    data = await _setup_test_entities(committed_db_session)

    db_name = pg_worker_db.url.database or "kanban_test"
    socket_dir = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")
    app_dsn = build_dsn(database=db_name, host=socket_dir, user="kanban_app")

    app_engine = create_async_engine(app_dsn, pool_size=5, max_overflow=0)

    try:
        factory = RLSSessionFactory(app_engine)
        resolver = _TestPrincipalResolver()

        app = create_app()
        app.state.session_factory = factory
        app.state.principal_resolver = resolver

        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await _verify_access_and_kill_switch(client, resolver, data, committed_db_session)
            await _run_timing_equalization(client, resolver, data)
    finally:
        await app_engine.dispose()


@pytest.mark.asyncio
async def test_objects_access_handlers_direct_unit(
    db_session: AsyncSession,
) -> None:
    """Direct unit execution of objects_access route handlers for comprehensive branch coverage."""
    ws_id = await create_workspace(db_session, name="Handler Unit WS")
    admin_id = await create_user(db_session, ws_id, handle="@h_admin", display_name="Admin")
    viewer_id = await create_user(db_session, ws_id, handle="@h_viewer", display_name="Viewer")
    outsider_id = await create_user(
        db_session, ws_id, handle="@h_outsider", display_name="Outsider"
    )
    agent_id = await create_agent(db_session, ws_id, "Handler Agent", principal_type="AGENT")

    proj_id = await create_project(
        db_session, ws_id, identifier="HND", name="Handler Proj", created_by_id=admin_id
    )
    issue_id = await create_registered_object(
        db_session,
        ws_id,
        kind="issue",
        key="HND-1",
        title="Task",
        project_id=proj_id,
        created_by_id=admin_id,
    )

    await add_role_binding(
        db_session, ws_id, admin_id, role="PROJECT_ADMIN", scope_type="project", project_id=proj_id
    )
    await add_role_binding(
        db_session, ws_id, viewer_id, role="VIEWER", scope_type="project", project_id=proj_id
    )

    # Add direct ALLOW ACL for agent
    await add_acl_entry(
        db_session, ws_id, issue_id, agent_id, effect="ALLOW", capability_mask=Capability.VIEW
    )
    await rebuild_era(db_session, ws_id)

    # Add second agent after ERA rebuild so it is found via acl_stmt
    # but not era_has_access (hits line 102)
    agent_2 = await create_agent(db_session, ws_id, "Direct Agent 2", principal_type="AGENT")
    await add_acl_entry(
        db_session, ws_id, issue_id, agent_2, effect="ALLOW", capability_mask=Capability.VIEW
    )

    admin_ctx = PrincipalContext(
        principal_id=admin_id, workspace_id=ws_id, token_scopes=("session",)
    )
    viewer_ctx = PrincipalContext(
        principal_id=viewer_id, workspace_id=ws_id, token_scopes=("session",)
    )
    outsider_ctx = PrincipalContext(
        principal_id=outsider_id, workspace_id=ws_id, token_scopes=("session",)
    )

    # 1. get_object_access_manifest directly
    manifest = await get_object_access_manifest(issue_id, admin_ctx, db_session)
    assert manifest.pill_label == "Project + 2"

    # 2. agent_kill_switch lacking VIEW -> 404
    with pytest.raises(ProblemException) as exc_404:
        await agent_kill_switch(issue_id, outsider_ctx, db_session)
    assert exc_404.value.status == 404

    # 3. agent_kill_switch with VIEW only -> 403
    with pytest.raises(ProblemException) as exc_403:
        await agent_kill_switch(issue_id, viewer_ctx, db_session)
    assert exc_403.value.status == 403

    # 4. agent_kill_switch with non-existent object record but valid caps (hits line 71)
    with patch("kanban.api.v1.objects_access.evaluate_capabilities", return_value=Capability.ALL):
        with pytest.raises(ProblemException) as exc_rec:
            await agent_kill_switch(uuid.uuid4(), admin_ctx, db_session)
        assert exc_rec.value.status == 404

    # 5. agent_kill_switch execute directly with admin_ctx
    res_manifest = await agent_kill_switch(issue_id, admin_ctx, db_session)
    assert res_manifest.agents == []
