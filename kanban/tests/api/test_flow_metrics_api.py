# Copyright 2026 Kanban Platform Contributors
# Licensed under Apache-2.0
"""API integration tests for flow telemetry studio (KAN-79, KB-FLOW-METRICS-01).

Tests:
    1. Positive flow metrics retrieval: GET /api/v1/projects/{project_ref}/analytics/flow (200)
    2. Query parameter boundaries: window_days, horizon_days, target_items, seed (200)
    3. Input validation: window_days=0 (422), window_days=400 (422), target_items=0 (422)
    4. Security & RLS isolation: non-viewer receives 404 NOT_FOUND (anti-enumeration)
    5. Contract recording for forensic QA verification
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

if TYPE_CHECKING:
    import uuid
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser
    from kanban.tests.contract import ContractRecorder

pytestmark = pytest.mark.committed_db


async def test_get_flow_metrics_success_and_contract(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Validate 200 OK response structure and record contract sample."""
    admin = await make_user("admin_flow1", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("FLW1", created_by=admin)
    client = as_principal(admin)

    # Fetch states
    st_rows = (
        await api_env.seed.execute(
            text("SELECT id, state_group FROM workflow_states WHERE project_id = :p"),
            {"p": proj_id},
        )
    ).all()
    st_map = {r[1]: r[0] for r in st_rows}
    started_id = st_map.get("started", st_rows[0][0])
    completed_id = st_map.get("completed", st_rows[-1][0])

    # Create issue via API
    iss_resp = await client.post(
        "/api/v1/projects/FLW1/issues",
        json={"summary": "Seed Flow Work Item"},
    )
    assert iss_resp.status_code == 201
    iss_data = iss_resp.json()
    iss_key = iss_data["key"]

    # Transition: unstarted -> started -> completed
    tr1 = await client.post(
        f"/api/v1/issues/{iss_key}/transitions",
        json={"to_state": str(started_id)},
    )
    assert tr1.status_code == 200
    tr2 = await client.post(
        f"/api/v1/issues/{iss_key}/transitions",
        json={"to_state": str(completed_id)},
    )
    assert tr2.status_code == 200
    await api_env.seed.commit()

    resp = await client.get(
        "/api/v1/projects/FLW1/analytics/flow",
        params={
            "window_days": 30,
            "horizon_days": 14,
            "target_items": 10,
            "seed": 42,
        },
    )
    assert resp.status_code == 200
    contract_recorder.record("get_flow_metrics_200", resp.request, resp)

    data = resp.json()
    assert data["project_key"] == "FLW1"
    assert data["window_days"] == 30
    assert len(data["cfd"]["points"]) == 30
    assert "cycle_lead_time" in data
    assert "aging_wip" in data
    assert "monte_carlo" in data
    assert data["monte_carlo"]["trials"] == 10000


async def test_get_flow_metrics_validation_errors(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Validate 422 responses on invalid query parameters."""
    admin = await make_user("admin_flow2", workspace_role="WORKSPACE_ADMIN")
    _ = await make_project("FLW2", created_by=admin)
    client = as_principal(admin)

    # Validate window_days lower bound
    resp1 = await client.get("/api/v1/projects/FLW2/analytics/flow?window_days=0")
    assert resp1.status_code == 422

    # Validate window_days upper bound
    resp2 = await client.get("/api/v1/projects/FLW2/analytics/flow?window_days=500")
    assert resp2.status_code == 422

    # Validate target_items lower bound
    resp3 = await client.get("/api/v1/projects/FLW2/analytics/flow?target_items=0")
    assert resp3.status_code == 422

    # Validate target_items upper bound
    resp4 = await client.get("/api/v1/projects/FLW2/analytics/flow?target_items=20000")
    assert resp4.status_code == 422

    # Validate horizon_days lower bound
    resp5 = await client.get("/api/v1/projects/FLW2/analytics/flow?horizon_days=0")
    assert resp5.status_code == 422


async def test_get_flow_metrics_security_and_rls(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Validate 404 NOT_FOUND for unauthorized callers (anti-enumeration)."""
    admin = await make_user("admin_flow3", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("FLW3", created_by=admin)

    # Separate outsider in another workspace
    outsider = await make_user("outsider_flow3")
    client = as_principal(outsider)

    resp = await client.get("/api/v1/projects/FLW3/analytics/flow")
    assert resp.status_code == 404

    resp_uuid = await client.get(f"/api/v1/projects/{proj_id}/analytics/flow")
    assert resp_uuid.status_code == 404
