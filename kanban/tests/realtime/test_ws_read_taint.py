# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Security and unit tests for propagating MCP read-taint to WebSocket subscriptions (KAN-326).

Covers:
  1. Subscribing to project channel propagates session & credential taint to mcp_read_taint.
  2. Subscribing to issue channel resolves parent project and records project read-taint.
  3. Subscribing to doc channel resolves parent project and records project read-taint.
  4. Subscribing with X-KB-MCP-Session propagates taint to the hashed MCP session key.
  5. Subscribing to untrusted content channel marks contains_untrusted_content=True.
  6. Exfiltration canary: WS subscription to confidential project blocks subsequent write
     to broader project with 409 CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED.
  7. Monotonicity: Unsubscribing does NOT clear read-taint from mcp_read_taint.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from starlette.requests import Request

from database.session import RLSContext, RLSSessionFactory
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.security.read_taint import TaintGuard
from kanban.tests.realtime.conftest import (
    AsyncWebSocketTestClient,
    build_realtime_test_app,
    create_auth_session,
    create_realtime_test_fixtures,
)
from kanban.tests.security.helpers import (
    add_role_binding,
    create_project,
    create_user,
    create_workspace,
    rebuild_era,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

    from kanban.auth.sessions.service import SessionService

pytestmark = pytest.mark.committed_db


@pytest.mark.asyncio
async def test_ws_subscribe_project_propagates_read_taint(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Subscribing to project:<UUID> records session and credential taint in mcp_read_taint."""
    factory = RLSSessionFactory(pg_worker_db)
    app, _hub = build_realtime_test_app(factory, session_service)

    # 1. Setup fixtures
    ws_id = uuid.uuid4()
    user_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    await create_realtime_test_fixtures(
        factory,
        ws_id=ws_id,
        maya_id=user_id,
        proj_id=proj_id,
    )

    # 2. Create authenticated session
    issued = await create_auth_session(
        factory, session_service, principal_id=user_id, workspace_id=ws_id
    )
    headers = {
        "Cookie": f"__Host-kb_session={issued.cookie_val}",
        "Origin": "https://kanban.example",
    }
    client = AsyncWebSocketTestClient(app, headers=headers)
    await client.connect()

    # 4. Subscribe to project channel
    req_id = "sub-proj-1"
    sub_frame = json.dumps(
        {"op": "subscribe", "req_id": req_id, "channels": [f"project:{proj_id}"]}
    )
    await client.send_text(sub_frame)

    ack = await client.receive_json()
    assert ack.get("type") == "subscribe_ack"
    assert ack.get("req_id") == req_id
    assert f"project:{proj_id}" in ack.get("channels", [])

    await client.close()

    # 5. Query mcp_read_taint table to verify records
    ctx = RLSContext(principal_id=user_id, workspace_id=ws_id)
    async with factory.session(ctx) as session:
        stmt = text(
            "SELECT taint_key, key_kind, project_id, contains_untrusted_content "
            "FROM mcp_read_taint WHERE workspace_id = :ws_id AND project_id = :proj_id"
        )
        rows = (await session.execute(stmt, {"ws_id": ws_id, "proj_id": proj_id})).fetchall()

    assert len(rows) == 2, f"Expected 2 taint entries (session and credential), got {len(rows)}"

    kinds = {r[1] for r in rows}
    assert kinds == {"session", "credential"}

    # Verify session key is sha256(session_id)
    session_key_expected = hashlib.sha256(str(issued.session_id).encode("utf-8")).digest()
    token_bytes = issued.token
    cred_key_expected = hashlib.sha256(token_bytes).digest()

    keys = {bytes(r[0]) for r in rows}
    assert session_key_expected in keys
    assert cred_key_expected in keys


@pytest.mark.asyncio
async def test_ws_subscribe_issue_propagates_parent_project_read_taint(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Subscribing to issue:<UUID> records taint for the parent project."""
    factory = RLSSessionFactory(pg_worker_db)
    app, _hub = build_realtime_test_app(factory, session_service)

    ws_id = uuid.uuid4()
    user_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    issue_id = uuid.uuid4()
    await create_realtime_test_fixtures(
        factory,
        ws_id=ws_id,
        maya_id=user_id,
        proj_id=proj_id,
        issue_id=issue_id,
    )

    issued = await create_auth_session(
        factory, session_service, principal_id=user_id, workspace_id=ws_id
    )
    headers = {
        "Cookie": f"__Host-kb_session={issued.cookie_val}",
        "Origin": "https://kanban.example",
    }
    client = AsyncWebSocketTestClient(app, headers=headers)
    await client.connect()

    req_id = "sub-issue-1"
    sub_frame = json.dumps({"op": "subscribe", "req_id": req_id, "channels": [f"issue:{issue_id}"]})
    await client.send_text(sub_frame)

    ack = await client.receive_json()
    assert ack.get("type") == "subscribe_ack"
    assert f"issue:{issue_id}" in ack.get("channels", [])

    await client.close()

    ctx = RLSContext(principal_id=user_id, workspace_id=ws_id)
    async with factory.session(ctx) as session:
        stmt = text(
            "SELECT taint_key, key_kind, project_id "
            "FROM mcp_read_taint WHERE workspace_id = :ws_id AND project_id = :proj_id"
        )
        rows = (await session.execute(stmt, {"ws_id": ws_id, "proj_id": proj_id})).fetchall()

    assert len(rows) == 2
    session_key_expected = hashlib.sha256(str(issued.session_id).encode("utf-8")).digest()
    keys = {bytes(r[0]) for r in rows}
    assert session_key_expected in keys


@pytest.mark.asyncio
async def test_ws_subscribe_with_mcp_session_propagates_to_mcp_session_key(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Subscribing with X-KB-MCP-Session header propagates taint to that MCP session key."""
    factory = RLSSessionFactory(pg_worker_db)
    app, _hub = build_realtime_test_app(factory, session_service)

    ws_id = uuid.uuid4()
    user_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    await create_realtime_test_fixtures(
        factory,
        ws_id=ws_id,
        maya_id=user_id,
        proj_id=proj_id,
    )

    issued = await create_auth_session(
        factory, session_service, principal_id=user_id, workspace_id=ws_id
    )
    mcp_session_raw = "mcp-agent-session-xyz-987"
    client = AsyncWebSocketTestClient(
        app,
        headers={
            "Cookie": f"__Host-kb_session={issued.cookie_val}",
            "Origin": "https://kanban.example",
            "X-KB-MCP-Session": mcp_session_raw,
        },
    )
    await client.connect()

    req_id = "sub-mcp-1"
    sub_frame = json.dumps(
        {"op": "subscribe", "req_id": req_id, "channels": [f"project:{proj_id}"]}
    )
    await client.send_text(sub_frame)

    ack = await client.receive_json()
    assert ack.get("type") == "subscribe_ack"

    await client.close()

    mcp_key_expected = hashlib.sha256(mcp_session_raw.encode("utf-8")).digest()

    ctx = RLSContext(principal_id=user_id, workspace_id=ws_id)
    async with factory.session(ctx) as session:
        stmt = text(
            "SELECT taint_key, key_kind, project_id "
            "FROM mcp_read_taint WHERE workspace_id = :ws_id AND taint_key = :mcp_key"
        )
        row = (await session.execute(stmt, {"ws_id": ws_id, "mcp_key": mcp_key_expected})).first()

    assert row is not None
    assert row[1] == "session"
    assert row[2] == proj_id


@pytest.mark.asyncio
async def test_ws_unsubscribe_does_not_clear_read_taint(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Unsubscribing does not clear recorded read taint (high-water mark monotonicity)."""
    factory = RLSSessionFactory(pg_worker_db)
    app, _hub = build_realtime_test_app(factory, session_service)

    ws_id = uuid.uuid4()
    user_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    await create_realtime_test_fixtures(
        factory,
        ws_id=ws_id,
        maya_id=user_id,
        proj_id=proj_id,
    )

    issued = await create_auth_session(
        factory, session_service, principal_id=user_id, workspace_id=ws_id
    )
    headers = {
        "Cookie": f"__Host-kb_session={issued.cookie_val}",
        "Origin": "https://kanban.example",
    }
    client = AsyncWebSocketTestClient(app, headers=headers)
    await client.connect()

    # 1. Subscribe
    sub_msg = {"op": "subscribe", "req_id": "sub-1", "channels": [f"project:{proj_id}"]}
    await client.send_text(json.dumps(sub_msg))
    ack_sub = await client.receive_json()
    assert ack_sub.get("type") == "subscribe_ack"

    # 2. Unsubscribe
    unsub_msg = {"op": "unsubscribe", "req_id": "unsub-1", "channels": [f"project:{proj_id}"]}
    await client.send_text(json.dumps(unsub_msg))
    ack_unsub = await client.receive_json()
    assert ack_unsub.get("type") == "unsubscribe_ack"

    await client.close()

    # 3. Verify taint remains in database
    ctx = RLSContext(principal_id=user_id, workspace_id=ws_id)
    async with factory.session(ctx) as session:
        stmt = text(
            "SELECT count(*) FROM mcp_read_taint "
            "WHERE workspace_id = :ws_id AND project_id = :proj_id"
        )
        count = (await session.execute(stmt, {"ws_id": ws_id, "proj_id": proj_id})).scalar()

    assert count == 2, "Read taint must persist monotonically after unsubscribe"


@pytest.mark.asyncio
async def test_ws_subscribe_doc_propagates_read_taint(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Subscribing to doc:<UUID> records taint for the doc's project in mcp_read_taint."""
    factory = RLSSessionFactory(pg_worker_db)
    app, _hub = build_realtime_test_app(factory, session_service)

    ws_id = uuid.uuid4()
    user_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    await create_realtime_test_fixtures(
        factory,
        ws_id=ws_id,
        maya_id=user_id,
        proj_id=proj_id,
    )

    # Insert doc attached to project
    ctx_admin = RLSContext(principal_id=user_id, workspace_id=ws_id)
    async with factory.session(ctx_admin) as session:
        await session.execute(
            text(
                "INSERT INTO objects "
                "(id, workspace_id, project_id, object_type, canonical_key, display_title, "
                "created_by_id) "
                "VALUES (:id, :ws_id, :proj_id, 'doc', 'doc-1', "
                "'Confidential Architecture Doc', :user_id)"
            ),
            {"id": doc_id, "ws_id": ws_id, "proj_id": proj_id, "user_id": user_id},
        )
        await session.execute(
            text(
                "INSERT INTO docs "
                "(id, workspace_id, project_id, title, hierarchy_path, provenance_tier) "
                "VALUES (:id, :ws_id, :proj_id, 'Confidential Architecture Doc', "
                "'doc_1', 'trusted_member')"
            ),
            {"id": doc_id, "ws_id": ws_id, "proj_id": proj_id},
        )
        await session.commit()

    issued = await create_auth_session(
        factory, session_service, principal_id=user_id, workspace_id=ws_id
    )
    headers = {
        "Cookie": f"__Host-kb_session={issued.cookie_val}",
        "Origin": "https://kanban.example",
    }
    client = AsyncWebSocketTestClient(app, headers=headers)
    await client.connect()

    req_id = "sub-doc-1"
    sub_frame = json.dumps({"op": "subscribe", "req_id": req_id, "channels": [f"doc:{doc_id}"]})
    await client.send_text(sub_frame)

    ack = await client.receive_json()
    assert ack.get("type") == "subscribe_ack"
    assert f"doc:{doc_id}" in ack.get("channels", [])

    await client.close()

    ctx = RLSContext(principal_id=user_id, workspace_id=ws_id)
    async with factory.session(ctx) as session:
        stmt = text(
            "SELECT count(*) FROM mcp_read_taint "
            "WHERE workspace_id = :ws_id AND project_id = :proj_id"
        )
        count = (await session.execute(stmt, {"ws_id": ws_id, "proj_id": proj_id})).scalar()

    assert count == 2, (
        "Doc subscription must record session and credential taint for parent project"
    )


@pytest.mark.asyncio
async def test_ws_read_taint_blocks_subsequent_cross_scope_write(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Exfiltration Canary: WS subscription to secret project blocks write to broader."""
    factory = RLSSessionFactory(pg_worker_db)
    app, _hub = build_realtime_test_app(factory, session_service)

    # 1. Setup workspace & projects via security helpers under superuser/admin context
    bootstrap_ws = uuid.uuid4()
    bootstrap_user = uuid.uuid4()
    ctx_boot = RLSContext(principal_id=bootstrap_user, workspace_id=bootstrap_ws)
    async with factory.session(ctx_boot) as session:
        ws_id = await create_workspace(session, name="Sec Test WS")
        admin_id = await create_user(session, ws_id, handle="@admin", display_name="Admin User")
        await add_role_binding(
            session, ws_id, admin_id, role="WORKSPACE_ADMIN", scope_type="workspace"
        )

        adam_id = await create_user(session, ws_id, handle="@adam", display_name="Adam Engineer")
        maya_id = await create_user(session, ws_id, handle="@maya", display_name="Maya Engineer")

        sec_proj_id = await create_project(
            session, ws_id, identifier="SEC", name="Secret Project", created_by_id=admin_id
        )
        pub_proj_id = await create_project(
            session, ws_id, identifier="PUB", name="Public Project", created_by_id=admin_id
        )

        # Adam in both projects
        await add_role_binding(
            session, ws_id, adam_id, role="MEMBER", scope_type="project", project_id=sec_proj_id
        )
        await add_role_binding(
            session, ws_id, adam_id, role="MEMBER", scope_type="project", project_id=pub_proj_id
        )

        # Maya ONLY in Public Project (so PUB has broader audience)
        await add_role_binding(
            session, ws_id, maya_id, role="MEMBER", scope_type="project", project_id=pub_proj_id
        )

        await session.commit()
        await rebuild_era(session, ws_id)

    # 2. Adam connects to WebSocket and subscribes to Secret Project
    adam_session = await create_auth_session(
        factory, session_service, principal_id=adam_id, workspace_id=ws_id
    )
    headers = {
        "Cookie": f"__Host-kb_session={adam_session.cookie_val}",
        "Origin": "https://kanban.example",
    }
    client = AsyncWebSocketTestClient(app, headers=headers)
    await client.connect()

    sub_frame = json.dumps(
        {"op": "subscribe", "req_id": "sub-sec", "channels": [f"project:{sec_proj_id}"]}
    )
    await client.send_text(sub_frame)
    ack = await client.receive_json()
    assert ack.get("type") == "subscribe_ack"

    await client.close()

    # 3. Adam attempts an MCP write to Public Project with active session
    token_bytes = adam_session.token
    mock_request = Request(
        scope={
            "type": "http",
            "method": "POST",
            "path": f"/api/v1/projects/{pub_proj_id}/issues",
            "headers": [
                (b"x-kb-mcp-session", str(adam_session.session_id).encode("utf-8")),
                (b"x-kb-subject-token", token_bytes),
            ],
            "app": app,
        }
    )
    caller = PrincipalContext(
        principal_id=adam_id,
        workspace_id=ws_id,
        token_scopes=("mcp",),
    )

    ctx_adam = RLSContext(principal_id=adam_id, workspace_id=ws_id)
    async with factory.session(ctx_adam) as session:
        guard = TaintGuard(mock_request, session, caller)
        with pytest.raises(ProblemException) as exc_info:
            await guard.check_write(target_projects=pub_proj_id, tool_name="create_issue")

        assert exc_info.value.code == "CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED"
        assert exc_info.value.status == 409
