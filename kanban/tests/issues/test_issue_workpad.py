# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration and unit tests for Silent Per-Issue Agent Workpad Slot (KAN-71).

Covers:
  - get_issue_workpad and put_issue_workpad: initial empty state, body storage,
    CAS revision increment.
  - CAS conflict: mismatched expected_revision raises 412 PRECONDITION_FAILED.
  - Surrogate validation: lone surrogate rejection raises 422 INVALID_UTF8_SURROGATE.
  - Size bounding: bodies exceeding 65536 bytes raise 422 WORKPAD_PAYLOAD_TOO_LARGE.
  - Zero notifications: updates emit no comments or notification activity.
  - API endpoints: GET /api/v1/issues/{key}/workpad and PUT with If-Match.
  - Silent begin-work: use_workpad=True updates workpad without human comment noise.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, cast

import pytest

from database.session import RLSContext
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.issues.workpad_service import (
    MAX_WORKPAD_BYTES,
    get_issue_workpad,
    put_issue_workpad,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


async def test_workpad_service_crud_and_cas(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify workpad service lifecycle: empty default, put, CAS match, and CAS rejection."""
    admin = await make_user("admin_wp", workspace_role="WORKSPACE_ADMIN")
    dev = await make_user("dev_wp")
    await make_project("WP1", created_by=admin, roles={admin: "PROJECT_ADMIN", dev: "MEMBER"})

    client_admin = as_principal(admin)
    create_resp = await client_admin.post(
        "/api/v1/projects/WP1/issues",
        json={"summary": "Workpad Service Test", "description_markdown": "Test description"},
    )
    assert create_resp.status_code == 201
    issue_key = create_resp.json()["key"]
    issue_id = uuid.UUID(create_resp.json()["id"])

    factory = cast("Any", api_env.client._transport).app.state.session_factory  # noqa: SLF001
    ctx = RLSContext(
        principal_id=dev.id,
        workspace_id=dev.workspace_id,
        token_scopes=("read", "write"),
        aal_level=1,
    )
    caller = PrincipalContext(
        principal_id=dev.id,
        workspace_id=dev.workspace_id,
        token_scopes=("read", "write"),
    )

    async with factory.session(ctx) as session:
        # 1. Initial read on unwritten workpad returns empty slot
        initial = await get_issue_workpad(session, caller, issue_key)
        assert initial.body_markdown == ""
        assert initial.revision == 0
        assert initial.issue_id == issue_id

        # 2. First write creates workpad with revision 1
        wp1 = await put_issue_workpad(
            session, caller, issue_key, "# Scratchpad\nStep 1", expected_revision=None
        )
        assert wp1.body_markdown == "# Scratchpad\nStep 1"
        assert wp1.revision == 1

        # 3. Subsequent write with matching expected_revision succeeds and increments revision to 2
        wp2 = await put_issue_workpad(
            session, caller, issue_key, "# Scratchpad\nStep 2", expected_revision=1
        )
        assert wp2.body_markdown == "# Scratchpad\nStep 2"
        assert wp2.revision == 2

        # 4. Write with stale expected_revision=1 raises PRECONDITION_FAILED (412)
        with pytest.raises(ProblemException) as exc_info:
            await put_issue_workpad(
                session, caller, issue_key, "# Scratchpad\nStep 3", expected_revision=1
            )
        assert exc_info.value.status == 412
        assert exc_info.value.code == "PRECONDITION_FAILED"


async def test_workpad_service_surrogate_rejection_and_bounds(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify rejection of lone surrogates and payloads exceeding 65536 bytes."""
    admin = await make_user("admin_wp2", workspace_role="WORKSPACE_ADMIN")
    dev = await make_user("dev_wp2")
    await make_project("WP2", created_by=admin, roles={admin: "PROJECT_ADMIN", dev: "MEMBER"})

    client_admin = as_principal(admin)
    create_resp = await client_admin.post(
        "/api/v1/projects/WP2/issues",
        json={"summary": "Workpad Bounds Test", "description_markdown": "Test body"},
    )
    assert create_resp.status_code == 201
    issue_key = create_resp.json()["key"]

    factory = cast("Any", api_env.client._transport).app.state.session_factory  # noqa: SLF001
    ctx = RLSContext(
        principal_id=dev.id,
        workspace_id=dev.workspace_id,
        token_scopes=("read", "write"),
        aal_level=1,
    )
    caller = PrincipalContext(
        principal_id=dev.id,
        workspace_id=dev.workspace_id,
        token_scopes=("read", "write"),
    )

    async with factory.session(ctx) as session:
        # Lone surrogate
        with pytest.raises(ProblemException) as exc_surr:
            await put_issue_workpad(session, caller, issue_key, "Invalid \ud800 surrogate")
        assert exc_surr.value.status == 422
        assert exc_surr.value.code == "INVALID_UTF8_SURROGATE"

        # Oversized payload
        oversized = "a" * (MAX_WORKPAD_BYTES + 10)
        with pytest.raises(ProblemException) as exc_size:
            await put_issue_workpad(session, caller, issue_key, oversized)
        assert exc_size.value.status == 422
        assert exc_size.value.code == "WORKPAD_PAYLOAD_TOO_LARGE"


@pytest.mark.usefixtures("api_env")
async def test_workpad_api_endpoints_and_silence(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify HTTP GET/PUT on workpad slot and ensure zero comment noise is generated."""
    admin = await make_user("admin_wp3", workspace_role="WORKSPACE_ADMIN")
    dev = await make_user("dev_wp3")
    await make_project("WP3", created_by=admin, roles={admin: "PROJECT_ADMIN", dev: "MEMBER"})

    client_admin = as_principal(admin)
    create_resp = await client_admin.post(
        "/api/v1/projects/WP3/issues",
        json={"summary": "Workpad API Test", "description_markdown": "Initial"},
    )
    assert create_resp.status_code == 201
    issue_key = create_resp.json()["key"]

    # Dev writes to workpad
    client_dev = as_principal(dev)
    put_resp = await client_dev.put(
        f"/api/v1/issues/{issue_key}/workpad",
        json={"body_markdown": "# Plan\n1. Run tests"},
    )
    assert put_resp.status_code == 200, put_resp.text
    put_data = put_resp.json()
    assert put_data["revision"] == 1
    assert put_data["body_markdown"] == "# Plan\n1. Run tests"
    assert "body_sha256" in put_data

    # Dev updates with If-Match header
    put_cas_resp = await client_dev.put(
        f"/api/v1/issues/{issue_key}/workpad",
        json={"body_markdown": "# Plan\n1. Run tests\n2. Ship"},
        headers={"If-Match": '"1"'},
    )
    assert put_cas_resp.status_code == 200
    assert put_cas_resp.json()["revision"] == 2

    # Dev gets workpad
    get_resp = await client_dev.get(f"/api/v1/issues/{issue_key}/workpad")
    assert get_resp.status_code == 200
    assert get_resp.json()["revision"] == 2
    assert get_resp.json()["body_markdown"] == "# Plan\n1. Run tests\n2. Ship"

    # Verify zero comments exist on the issue
    comm_resp = await client_dev.get(f"/api/v1/issues/{issue_key}/comments")
    assert comm_resp.status_code == 200
    assert len(comm_resp.json().get("items", [])) == 0


@pytest.mark.usefixtures("api_env")
async def test_begin_work_with_use_workpad(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify begin-work with use_workpad=True updates workpad and suppresses comments."""
    admin = await make_user("admin_wp4", workspace_role="WORKSPACE_ADMIN")
    dev = await make_user("dev_wp4")
    await make_project("WP4", created_by=admin, roles={admin: "PROJECT_ADMIN", dev: "MEMBER"})

    client_admin = as_principal(admin)
    create_resp = await client_admin.post(
        "/api/v1/projects/WP4/issues",
        json={"summary": "Begin Work Workpad Test", "description_markdown": "Test"},
    )
    assert create_resp.status_code == 201
    issue_key = create_resp.json()["key"]

    client_dev = as_principal(dev)
    bw_resp = await client_dev.post(
        f"/api/v1/issues/{issue_key}/begin-work",
        json={
            "plan_markdown": "### Investigation Plan\n- Audit ratelimit\n- Add breaker",
            "use_workpad": True,
        },
    )
    assert bw_resp.status_code == 200, bw_resp.text

    # Read workpad: plan was saved silently
    wp_resp = await client_dev.get(f"/api/v1/issues/{issue_key}/workpad")
    assert wp_resp.status_code == 200
    assert "Audit ratelimit" in wp_resp.json()["body_markdown"]

    # Verify comments list is completely empty
    comm_resp = await client_dev.get(f"/api/v1/issues/{issue_key}/comments")
    assert comm_resp.status_code == 200
    assert len(comm_resp.json().get("items", [])) == 0
