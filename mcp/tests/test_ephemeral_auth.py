# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Feature unit tests for ephemeral kb_agt_eph_* MCP tokens (KB-P4-13)."""

# ruff: noqa: ARG001, PLR0911, PLR0915, TC002

from __future__ import annotations

import asyncio
import base64
import os
import time
import uuid
from typing import Any, Final, cast

import httpx
import pytest
import yaml
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from database.session import RLSSessionFactory
from kanban.api.deps import PrincipalContext
from kanban.app import create_app
from kanban.security.ephemeral_mcp_tokens import (
    EPHEMERAL_TOKEN_PREFIX,
    mint_ephemeral_token,
)
from kanban.settings import Settings
from kanban.tests.security.helpers import (
    add_role_binding,
    create_agent,
    create_project,
    create_user,
    create_workspace,
    rebuild_era,
)
from mcp.app import create_mcp_app
from mcp.registry import Surface, ToolRegistry, ToolSpec
from mcp.settings import McpSettings
from mcp.tests.test_auth import *  # noqa: F403

_DUMMY_SCHEMA: Final[dict[str, Any]] = {"type": "object"}


def _generate_test_eph_token() -> str:
    rand = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii").rstrip("=")
    return f"{EPHEMERAL_TOKEN_PREFIX}{rand}"


async def _init_session(client: httpx.AsyncClient, surface_path: str, token: str) -> str:
    """Initialize streamable HTTP session and return session id."""
    res = await client.post(
        surface_path,
        headers={"Authorization": f"Bearer {token}"},
        json={
            "jsonrpc": "2.0",
            "id": 999,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0"},
            },
        },
    )
    assert res.status_code == 200
    return res.headers["mcp-session-id"]


def _build_test_registries() -> tuple[ToolRegistry, ToolRegistry, ToolRegistry]:
    """Construct full agent, docs, and admin registries with read and write tools."""
    # 1. Agent surface
    agent_reg = ToolRegistry(Surface.AGENT)

    async def _search_tickets_handler(args: dict[str, Any]) -> dict[str, Any]:
        return {"items": [{"key": "KAN-1", "title": "Test Ticket 1"}]}

    async def _read_ticket_handler(args: dict[str, Any]) -> dict[str, Any]:
        ident = args.get("identifier", "KAN-1")
        return {"key": ident, "title": f"Ticket {ident}", "state": "In Progress"}

    async def _agent_write_handler(args: dict[str, Any]) -> dict[str, Any]:
        return {"status": "created"}

    agent_reg.register(
        ToolSpec(
            name="search_tickets",
            description="Search tickets",
            surface=Surface.AGENT,
            input_schema=_DUMMY_SCHEMA,
            handler=_search_tickets_handler,
        )
    )
    agent_reg.register(
        ToolSpec(
            name="read_ticket",
            description="Read ticket",
            surface=Surface.AGENT,
            input_schema=_DUMMY_SCHEMA,
            handler=_read_ticket_handler,
        )
    )
    agent_reg.register(
        ToolSpec(
            name="create_ticket",
            description="Create ticket",
            surface=Surface.AGENT,
            input_schema=_DUMMY_SCHEMA,
            handler=_agent_write_handler,
        )
    )
    agent_reg.register(
        ToolSpec(
            name="add_comment",
            description="Add comment",
            surface=Surface.AGENT,
            input_schema=_DUMMY_SCHEMA,
            handler=_agent_write_handler,
        )
    )
    agent_reg.register(
        ToolSpec(
            name="transition_ticket",
            description="Transition ticket",
            surface=Surface.AGENT,
            input_schema=_DUMMY_SCHEMA,
            handler=_agent_write_handler,
        )
    )

    # 2. Docs surface
    docs_reg = ToolRegistry(Surface.DOCS)

    async def _search_handler(args: dict[str, Any]) -> dict[str, Any]:
        return {"items": [{"slug": "docs/kan-spec", "title": "KAN Spec"}]}

    async def _create_handler(args: dict[str, Any]) -> dict[str, Any]:
        return {"status": "created"}

    async def _update_handler(args: dict[str, Any]) -> dict[str, Any]:
        return {"status": "updated"}

    docs_reg.register(
        ToolSpec(
            name="search",
            description="Search knowledge",
            surface=Surface.DOCS,
            input_schema=_DUMMY_SCHEMA,
            handler=_search_handler,
        )
    )
    docs_reg.register(
        ToolSpec(
            name="create",
            description="Create doc",
            surface=Surface.DOCS,
            input_schema=_DUMMY_SCHEMA,
            handler=_create_handler,
        )
    )
    docs_reg.register(
        ToolSpec(
            name="update",
            description="Update doc",
            surface=Surface.DOCS,
            input_schema=_DUMMY_SCHEMA,
            handler=_update_handler,
        )
    )

    # 3. Admin surface
    admin_reg = ToolRegistry(Surface.ADMIN)

    async def _admin_handler(args: dict[str, Any]) -> dict[str, Any]:
        return {"status": "ok"}

    admin_reg.register(
        ToolSpec(
            name="audit_links",
            description="Audit links",
            surface=Surface.ADMIN,
            input_schema=_DUMMY_SCHEMA,
            handler=_admin_handler,
        )
    )

    return agent_reg, docs_reg, admin_reg


class _MockStatefulIntrospectService:
    """Mock stateful introspection and consumption tracking service."""

    def __init__(
        self,
        token: str,
        *,
        max_calls: int = 3,
        allowed_tools: list[str] | None = None,
        ttl_seconds: float = 60.0,
    ) -> None:
        self.token = token
        self.max_calls = max_calls
        self.calls_used = 0
        self.allowed_tools = allowed_tools or [
            "search_tickets",
            "read_ticket",
            "search",
        ]
        self.created_at = time.time()
        self.expires_at = self.created_at + ttl_seconds
        self.revoked = False
        self.introspect_calls = 0
        self.principal_id = str(uuid.uuid4())
        self.agent_principal_id = str(uuid.uuid4())
        self.workspace_id = str(uuid.uuid4())
        self.project_id = str(uuid.uuid4())
        self.execution_id = str(uuid.uuid4())

    def handle_data(self, data: dict[str, Any]) -> dict[str, Any]:
        self.introspect_calls += 1
        req_token = data.get("token")
        surface = data.get("surface", "agent")
        consume_call = data.get("consume_call", False)
        tool_name = data.get("tool_name")

        if req_token != self.token:
            return {"active": False, "reason": "SURFACE_KEY_MISMATCH"}

        now = time.time()
        if self.revoked or now >= self.expires_at:
            return {"active": False, "reason": "TOKEN_EXPIRED_OR_REVOKED"}

        surface_tools = ["search_tickets", "read_ticket"] if surface == "agent" else ["search"]

        if not consume_call:
            if self.calls_used >= self.max_calls:
                return {
                    "active": False,
                    "reason": "EPHEMERAL_CALL_BUDGET_EXCEEDED",
                    "token_kind": "ephemeral",
                    "surface": surface,
                    "scopes": ["agent:read", "docs:read"],
                    "principal_id": self.principal_id,
                    "agent_principal_id": self.agent_principal_id,
                    "workspace_id": self.workspace_id,
                    "project_id": self.project_id,
                    "execution_id": self.execution_id,
                    "allowed_tools": [t for t in self.allowed_tools if t in surface_tools],
                    "calls_used": self.calls_used,
                    "max_calls": self.max_calls,
                }
            return {
                "active": True,
                "token_kind": "ephemeral",
                "surface": surface,
                "scopes": ["agent:read", "docs:read"],
                "principal_id": self.principal_id,
                "agent_principal_id": self.agent_principal_id,
                "workspace_id": self.workspace_id,
                "project_id": self.project_id,
                "execution_id": self.execution_id,
                "allowed_tools": [t for t in self.allowed_tools if t in surface_tools],
                "calls_used": self.calls_used,
                "max_calls": self.max_calls,
            }

        # Consuming call
        if tool_name not in self.allowed_tools:
            return {
                "active": False,
                "reason": "EPHEMERAL_TOOL_FORBIDDEN",
                "allowed_tools": self.allowed_tools,
            }

        if self.calls_used >= self.max_calls:
            return {
                "active": False,
                "reason": "EPHEMERAL_CALL_BUDGET_EXCEEDED",
                "calls_used": self.calls_used,
                "max_calls": self.max_calls,
                "workspace_id": self.workspace_id,
                "project_id": self.project_id,
            }

        self.calls_used += 1
        return {
            "active": True,
            "token_kind": "ephemeral",
            "surface": surface,
            "scopes": ["agent:read", "docs:read"],
            "calls_used": self.calls_used,
            "max_calls": self.max_calls,
        }


def _create_mock_kanban_app(service: _MockStatefulIntrospectService) -> Starlette:
    async def introspect_endpoint(request: Request) -> JSONResponse:
        body = await request.json()
        return JSONResponse(service.handle_data(body))

    return Starlette(
        routes=[
            Route("/internal/v1/mcp/introspect", introspect_endpoint, methods=["POST"]),
        ]
    )


@pytest.mark.asyncio
async def test_case_1_positive_read_only_lookup_and_tools_list_filtering() -> None:
    """Test Case 1: Positive read-only lookup and tools/list filtering.

    Validates behavior on /mcp/agent and /mcp/docs.
    """
    token = _generate_test_eph_token()
    mock_service = _MockStatefulIntrospectService(token, max_calls=3)
    mock_kanban_app = _create_mock_kanban_app(mock_service)

    settings = McpSettings(mode="standalone_inprocess", auth_enabled=True)
    agent_reg, docs_reg, admin_reg = _build_test_registries()

    app = create_mcp_app(
        settings,
        kanban_app=mock_kanban_app,
        agent_registry=agent_reg,
        docs_registry=docs_reg,
        admin_registry=admin_reg,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Initialize session on /mcp/agent
        agent_session = await _init_session(client, "/mcp/agent", token)

        # 2. tools/list on /mcp/agent: MUST list only [search_tickets, read_ticket]
        list_agent = await client.post(
            "/mcp/agent",
            headers={"Authorization": f"Bearer {token}", "mcp-session-id": agent_session},
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        assert list_agent.status_code == 200
        agent_tools = [t["name"] for t in list_agent.json()["result"]["tools"]]
        assert sorted(agent_tools) == ["read_ticket", "search_tickets"]
        # Verify 0 calls consumed by tools/list
        assert mock_service.calls_used == 0

        # 3. Initialize session on /mcp/docs
        docs_session = await _init_session(client, "/mcp/docs", token)

        # 4. tools/list on /mcp/docs: MUST list only [search]
        list_docs = await client.post(
            "/mcp/docs",
            headers={"Authorization": f"Bearer {token}", "mcp-session-id": docs_session},
            json={"jsonrpc": "2.0", "id": 4, "method": "tools/list"},
        )
        assert list_docs.status_code == 200
        docs_tools = [t["name"] for t in list_docs.json()["result"]["tools"]]
        assert sorted(docs_tools) == ["search"]
        assert mock_service.calls_used == 0

        # 5. Call 1: search_tickets
        c1 = await client.post(
            "/mcp/agent",
            headers={"Authorization": f"Bearer {token}", "mcp-session-id": agent_session},
            json={
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"name": "search_tickets", "arguments": {"query": "*"}},
            },
        )
        assert c1.status_code == 200
        assert mock_service.calls_used == 1

        # 6. Call 2: read_ticket("KAN-1")
        c2 = await client.post(
            "/mcp/agent",
            headers={"Authorization": f"Bearer {token}", "mcp-session-id": agent_session},
            json={
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {"name": "read_ticket", "arguments": {"identifier": "KAN-1"}},
            },
        )
        assert c2.status_code == 200
        assert mock_service.calls_used == 2

        # 7. Call 3: search(id="docs/kan-spec") on /mcp/docs
        c3 = await client.post(
            "/mcp/docs",
            headers={"Authorization": f"Bearer {token}", "mcp-session-id": docs_session},
            json={
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {"name": "search", "arguments": {"id": "docs/kan-spec"}},
            },
        )
        assert c3.status_code == 200
        assert mock_service.calls_used == 3


@pytest.mark.asyncio
async def test_case_2_call_budget_exceeded_and_concurrency() -> None:
    """Test Case 2: Call-budget hard caps, 4th call error format, and 10 concurrent requests."""
    token = _generate_test_eph_token()
    mock_service = _MockStatefulIntrospectService(token, max_calls=3)
    mock_kanban_app = _create_mock_kanban_app(mock_service)

    settings = McpSettings(mode="standalone_inprocess", auth_enabled=True)
    agent_reg, docs_reg, admin_reg = _build_test_registries()

    app = create_mcp_app(
        settings,
        kanban_app=mock_kanban_app,
        agent_registry=agent_reg,
        docs_registry=docs_reg,
        admin_registry=admin_reg,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        session_id = await _init_session(client, "/mcp/agent", token)

        # 1. Exhaust budget with 3 calls
        for i in range(1, 4):
            res = await client.post(
                "/mcp/agent",
                headers={"Authorization": f"Bearer {token}", "mcp-session-id": session_id},
                json={
                    "jsonrpc": "2.0",
                    "id": i,
                    "method": "tools/call",
                    "params": {"name": "read_ticket", "arguments": {"identifier": f"KAN-{i}"}},
                },
            )
            assert res.status_code == 200
            assert res.json()["result"].get("isError") is not True

        assert mock_service.calls_used == 3

        # 2. Call 4: fails immediately with EPHEMERAL_CALL_BUDGET_EXCEEDED
        res_4 = await client.post(
            "/mcp/agent",
            headers={"Authorization": f"Bearer {token}", "mcp-session-id": session_id},
            json={
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "read_ticket", "arguments": {"identifier": "KAN-4"}},
            },
        )
        assert res_4.status_code == 200
        res_data = res_4.json()["result"]
        assert res_data["isError"] is True
        error_text = res_data["content"][0]["text"]
        parsed_err = yaml.safe_load(error_text)
        assert parsed_err["error"]["code"] == "EPHEMERAL_CALL_BUDGET_EXCEEDED"
        assert parsed_err["error"]["budget"]["max_calls"] == 3
        assert parsed_err["error"]["budget"]["calls_used"] == 3

        # 3. 0s cache delay on revocation: revoke token and verify immediate invalidation
        token_rev = _generate_test_eph_token()
        mock_service_rev = _MockStatefulIntrospectService(token_rev, max_calls=5)
        mock_kanban_app_rev = _create_mock_kanban_app(mock_service_rev)
        app_rev = create_mcp_app(
            settings,
            kanban_app=mock_kanban_app_rev,
            agent_registry=agent_reg,
            docs_registry=docs_reg,
            admin_registry=admin_reg,
        )
        t_rev = httpx.ASGITransport(app=app_rev)
        async with httpx.AsyncClient(transport=t_rev, base_url="http://test") as c_rev:
            s_rev = await _init_session(c_rev, "/mcp/agent", token_rev)

            # First call succeeds
            ok_res = await c_rev.post(
                "/mcp/agent",
                headers={"Authorization": f"Bearer {token_rev}", "mcp-session-id": s_rev},
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "read_ticket", "arguments": {"identifier": "KAN-1"}},
                },
            )
            assert ok_res.status_code == 200
            assert ok_res.json()["result"].get("isError") is not True

            # Revoke immediately
            mock_service_rev.revoked = True

            # Next call must fail immediately (0s delay, cache bypass for ephemeral)
            fail_res = await c_rev.post(
                "/mcp/agent",
                headers={"Authorization": f"Bearer {token_rev}", "mcp-session-id": s_rev},
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "read_ticket", "arguments": {"identifier": "KAN-1"}},
                },
            )
            # Ephemeral token bypasses cache, so auth middleware hits introspect,
            # returns active=false, resulting in 401
            assert fail_res.status_code == 401

        # 4. 10 concurrent asyncio.gather calls on max_calls=5
        token_conc = _generate_test_eph_token()
        mock_service_conc = _MockStatefulIntrospectService(token_conc, max_calls=5)
        mock_kanban_app_conc = _create_mock_kanban_app(mock_service_conc)
        app_conc = create_mcp_app(
            settings,
            kanban_app=mock_kanban_app_conc,
            agent_registry=agent_reg,
            docs_registry=docs_reg,
            admin_registry=admin_reg,
        )
        t_conc = httpx.ASGITransport(app=app_conc)
        async with httpx.AsyncClient(transport=t_conc, base_url="http://test") as c_conc:
            s_conc = await _init_session(c_conc, "/mcp/agent", token_conc)

            async def _do_call(idx: int) -> dict[str, Any]:
                res = await c_conc.post(
                    "/mcp/agent",
                    headers={"Authorization": f"Bearer {token_conc}", "mcp-session-id": s_conc},
                    json={
                        "jsonrpc": "2.0",
                        "id": idx,
                        "method": "tools/call",
                        "params": {"name": "read_ticket", "arguments": {"identifier": "KAN-1"}},
                    },
                )
                assert res.status_code == 200
                return cast("dict[str, Any]", res.json()["result"])

            results = await asyncio.gather(*[_do_call(i) for i in range(1, 11)])
            successes = [r for r in results if not r.get("isError")]
            failures = [r for r in results if r.get("isError")]
            assert len(successes) == 5
            assert len(failures) == 5
            for f in failures:
                parsed = yaml.safe_load(f["content"][0]["text"])
                assert parsed["error"]["code"] == "EPHEMERAL_CALL_BUDGET_EXCEEDED"


@pytest.mark.asyncio
async def test_case_3_write_tools_and_surface_isolation() -> None:
    """Test Case 3: Write-tools forbidden, admin surface rejection, and error formatting."""
    token = _generate_test_eph_token()
    mock_service = _MockStatefulIntrospectService(token, max_calls=10)
    mock_kanban_app = _create_mock_kanban_app(mock_service)

    settings = McpSettings(mode="standalone_inprocess", auth_enabled=True)
    agent_reg, docs_reg, admin_reg = _build_test_registries()

    app = create_mcp_app(
        settings,
        kanban_app=mock_kanban_app,
        agent_registry=agent_reg,
        docs_registry=docs_reg,
        admin_registry=admin_reg,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        agent_session = await _init_session(client, "/mcp/agent", token)
        docs_session = await _init_session(client, "/mcp/docs", token)

        # 1. Calling create_ticket -> EPHEMERAL_TOOL_FORBIDDEN
        res_create = await client.post(
            "/mcp/agent",
            headers={"Authorization": f"Bearer {token}", "mcp-session-id": agent_session},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "create_ticket", "arguments": {"title": "Forbidden"}},
            },
        )
        assert res_create.status_code == 200
        res_data = res_create.json()["result"]
        assert res_data["isError"] is True
        parsed = yaml.safe_load(res_data["content"][0]["text"])
        assert parsed["error"]["code"] == "EPHEMERAL_TOOL_FORBIDDEN"
        assert "allowed_tools" in parsed["error"]

        # 2. Calling add_comment -> EPHEMERAL_TOOL_FORBIDDEN
        res_comment = await client.post(
            "/mcp/agent",
            headers={"Authorization": f"Bearer {token}", "mcp-session-id": agent_session},
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "add_comment", "arguments": {"body": "Forbidden comment"}},
            },
        )
        assert res_comment.status_code == 200
        assert res_comment.json()["result"]["isError"] is True
        parsed_comment = yaml.safe_load(res_comment.json()["result"]["content"][0]["text"])
        assert parsed_comment["error"]["code"] == "EPHEMERAL_TOOL_FORBIDDEN"

        # 3. Calling transition_ticket -> EPHEMERAL_TOOL_FORBIDDEN
        res_trans = await client.post(
            "/mcp/agent",
            headers={"Authorization": f"Bearer {token}", "mcp-session-id": agent_session},
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "transition_ticket", "arguments": {"to_state": "Done"}},
            },
        )
        assert res_trans.status_code == 200
        assert res_trans.json()["result"]["isError"] is True
        assert (
            yaml.safe_load(res_trans.json()["result"]["content"][0]["text"])["error"]["code"]
            == "EPHEMERAL_TOOL_FORBIDDEN"
        )

        # 4. Calling create/update on /mcp/docs -> EPHEMERAL_TOOL_FORBIDDEN
        res_create_doc = await client.post(
            "/mcp/docs",
            headers={"Authorization": f"Bearer {token}", "mcp-session-id": docs_session},
            json={
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "create", "arguments": {"type": "DOC", "title": "forbidden"}},
            },
        )
        assert res_create_doc.status_code == 200
        assert res_create_doc.json()["result"]["isError"] is True
        assert (
            yaml.safe_load(res_create_doc.json()["result"]["content"][0]["text"])["error"]["code"]
            == "EPHEMERAL_TOOL_FORBIDDEN"
        )

        # 5. Presenting kb_agt_eph_* on /mcp/admin -> 403 SURFACE_KEY_MISMATCH before network
        admin_res = await client.post(
            "/mcp/admin",
            headers={"Authorization": f"Bearer {token}"},
            json={"jsonrpc": "2.0", "id": 5, "method": "tools/list"},
        )
        assert admin_res.status_code == 403
        assert admin_res.json()["error"] == "SURFACE_KEY_MISMATCH"


@pytest.mark.committed_db
@pytest.mark.asyncio
async def test_case_4_triple_intersection_and_project_pin_confinement(
    committed_db_session: AsyncSession,
) -> None:
    """Test Case 4: Triple-intersection confinement (Invoker ∩ Agent ∩ Project)."""
    # Seed workspace, users, agent, and two projects: KAN and SEC
    ws_id = await create_workspace(committed_db_session, name="WS-Triple-Int")
    adam_id = await create_user(committed_db_session, ws_id, handle="@adam", display_name="Adam")
    agent_id = await create_agent(committed_db_session, ws_id, display_name="agy-gate")

    proj_kan_id = await create_project(
        committed_db_session, ws_id, identifier="KAN", name="Kanban Core", created_by_id=adam_id
    )
    proj_sec_id = await create_project(
        committed_db_session, ws_id, identifier="SEC", name="Security Vault", created_by_id=adam_id
    )

    # Both Adam and agy-gate hold VIEW on KAN and SEC
    await add_role_binding(
        committed_db_session,
        ws_id,
        adam_id,
        role="MEMBER",
        scope_type="project",
        project_id=proj_kan_id,
    )
    await add_role_binding(
        committed_db_session,
        ws_id,
        agent_id,
        role="MEMBER",
        scope_type="project",
        project_id=proj_kan_id,
    )
    await add_role_binding(
        committed_db_session,
        ws_id,
        adam_id,
        role="MEMBER",
        scope_type="project",
        project_id=proj_sec_id,
    )
    await add_role_binding(
        committed_db_session,
        ws_id,
        agent_id,
        role="MEMBER",
        scope_type="project",
        project_id=proj_sec_id,
    )

    # Sequence counter updates
    await committed_db_session.execute(
        text(
            "UPDATE projects SET issue_seq_counter = GREATEST(issue_seq_counter, 1) WHERE id = :p"
        ),
        {"p": proj_kan_id},
    )
    await committed_db_session.execute(
        text(
            "UPDATE projects SET issue_seq_counter = GREATEST(issue_seq_counter, 1) WHERE id = :p"
        ),
        {"p": proj_sec_id},
    )

    # Seed tickets:
    # 1. KAN-1 in KAN
    kan_state_id = (
        await committed_db_session.execute(
            text("SELECT id FROM workflow_states WHERE project_id = :p LIMIT 1"),
            {"p": proj_kan_id},
        )
    ).scalar_one()
    kan_pri_id = (
        await committed_db_session.execute(
            text("SELECT id FROM project_priorities WHERE project_id = :p LIMIT 1"),
            {"p": proj_kan_id},
        )
    ).scalar_one()

    kan_1_id = uuid.uuid4()
    await committed_db_session.execute(
        text(
            "SELECT register_object("
            "'issue'::object_kind, :ws, :proj, 'KAN-1', 'KAN-1 Ticket', :cr, :id)"
        ),
        {"ws": ws_id, "proj": proj_kan_id, "cr": adam_id, "id": kan_1_id},
    )
    await committed_db_session.execute(
        text(
            "INSERT INTO issues (id, object_type, workspace_id, project_id, sequence_id, summary, "
            "description_markdown, state_id, priority_id, created_by_id, original_created_by_id, "
            "board_rank, ancestry_path) "
            "VALUES ("
            ":id, 'issue', :ws, :proj, 1, 'KAN-1 Ticket', 'Spec for KAN', :st, :pri, "
            ":cr, :cr, 'a0', 'top')"
        ),
        {
            "id": kan_1_id,
            "ws": ws_id,
            "proj": proj_kan_id,
            "st": kan_state_id,
            "pri": kan_pri_id,
            "cr": adam_id,
        },
    )

    # 2. SEC-1 in SEC
    sec_state_id = (
        await committed_db_session.execute(
            text("SELECT id FROM workflow_states WHERE project_id = :p LIMIT 1"),
            {"p": proj_sec_id},
        )
    ).scalar_one()
    sec_pri_id = (
        await committed_db_session.execute(
            text("SELECT id FROM project_priorities WHERE project_id = :p LIMIT 1"),
            {"p": proj_sec_id},
        )
    ).scalar_one()

    sec_1_id = uuid.uuid4()
    await committed_db_session.execute(
        text(
            "SELECT register_object("
            "'issue'::object_kind, :ws, :proj, 'SEC-1', 'SEC-1 Secret', :cr, :id)"
        ),
        {"ws": ws_id, "proj": proj_sec_id, "cr": adam_id, "id": sec_1_id},
    )
    await committed_db_session.execute(
        text(
            "INSERT INTO issues (id, object_type, workspace_id, project_id, sequence_id, summary, "
            "description_markdown, state_id, priority_id, created_by_id, original_created_by_id, "
            "board_rank, ancestry_path) "
            "VALUES ("
            ":id, 'issue', :ws, :proj, 1, 'SEC-1 Secret', 'Confidential', :st, :pri, "
            ":cr, :cr, 'a0', 'top')"
        ),
        {
            "id": sec_1_id,
            "ws": ws_id,
            "proj": proj_sec_id,
            "st": sec_state_id,
            "pri": sec_pri_id,
            "cr": adam_id,
        },
    )

    await rebuild_era(committed_db_session, ws_id)

    # Mint ephemeral token pinned strictly to project KAN
    exec_id = uuid.uuid4()
    _rec, eph_token = await mint_ephemeral_token(
        committed_db_session,
        workspace_id=ws_id,
        execution_id=exec_id,
        invoking_principal_id=adam_id,
        agent_principal_id=agent_id,
        project_id=proj_kan_id,
        ttl_seconds=60,
        max_calls=10,
    )
    await committed_db_session.commit()

    # Mount real app
    settings = Settings()
    kanban_fastapi_app = create_app(settings)
    kanban_fastapi_app.state.session_factory = RLSSessionFactory(committed_db_session.bind)  # type: ignore[arg-type]

    class _EphemeralPrincipalResolver:
        def __init__(self, ctx: PrincipalContext) -> None:
            self.ctx = ctx

        async def resolve(self, request: Request) -> PrincipalContext | None:
            tok = request.headers.get("x-kb-subject-token")
            if tok and tok.startswith(EPHEMERAL_TOKEN_PREFIX):
                return self.ctx
            return None

    kanban_fastapi_app.state.principal_resolver = _EphemeralPrincipalResolver(
        PrincipalContext(
            principal_id=adam_id,
            workspace_id=ws_id,
            token_scopes=("agent:read", "docs:read"),
            agent_principal_id=agent_id,
            ephemeral_project_id=proj_kan_id,
            read_only=True,
        )
    )

    mcp_settings = McpSettings(mode="standalone_inprocess", auth_enabled=True)
    mcp_app = create_mcp_app(mcp_settings, kanban_app=kanban_fastapi_app)

    transport = httpx.ASGITransport(app=mcp_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        session_id = await _init_session(client, "/mcp/agent", eph_token)

        # Cross-project ticket lookup (SEC-1) MUST return NOT_FOUND error
        res_sec = await client.post(
            "/mcp/agent",
            headers={"Authorization": f"Bearer {eph_token}", "mcp-session-id": session_id},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "read_ticket", "arguments": {"identifier": "SEC-1"}},
            },
        )
        assert res_sec.status_code == 200
        sec_result = res_sec.json()["result"]
        assert sec_result["isError"] is True
        parsed_sec = yaml.safe_load(sec_result["content"][0]["text"])
        assert parsed_sec["error"]["code"] == "NOT_FOUND"

        # Reading ticket KAN-1 in pinned project MUST succeed
        res_kan = await client.post(
            "/mcp/agent",
            headers={"Authorization": f"Bearer {eph_token}", "mcp-session-id": session_id},
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "read_ticket", "arguments": {"identifier": "KAN-1"}},
            },
        )
        assert res_kan.status_code == 200
        kan_result = res_kan.json()["result"]
        assert kan_result.get("isError") is not True
        parsed_kan = yaml.safe_load(kan_result["content"][0]["text"])
        assert parsed_kan["key"] == "KAN-1"


@pytest.mark.asyncio
async def test_case_5_mtls_mint_boundary(db_session: AsyncSession) -> None:
    """Test Case 5: mTLS mint boundary (mcp-gateway 403, agent-runtime 201)."""
    ws_id = await create_workspace(db_session, name="WS-Mint-Boundary")
    user_id = await create_user(db_session, ws_id, handle="@user-mint", display_name="User Mint")
    agent_id = await create_agent(db_session, ws_id, display_name="agent-mint")
    proj_id = await create_project(db_session, ws_id, identifier="MNT", name="Mint Project")
    exec_id = uuid.uuid4()

    settings = Settings()
    app = create_app(settings)
    app.state.session_factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]

    await db_session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "workspace_id": str(ws_id),
            "execution_id": str(exec_id),
            "invoking_principal_id": str(user_id),
            "agent_principal_id": str(agent_id),
            "project_id": str(proj_id),
            "ttl_seconds": 60,
            "max_calls": 5,
        }

        # 1. mcp-gateway service principal -> 403 Forbidden
        res_gw = await client.post(
            "/internal/v1/mcp/ephemeral-tokens",
            json=payload,
            headers={"X-KB-Service-Principal": "mcp-gateway"},
        )
        assert res_gw.status_code == 403
        assert res_gw.json()["code"] == "FORBIDDEN"

        # 2. agent-runtime service principal -> 201 Created
        res_agt = await client.post(
            "/internal/v1/mcp/ephemeral-tokens",
            json=payload,
            headers={"X-KB-Service-Principal": "agent-runtime"},
        )
        assert res_agt.status_code == 201
        data = res_agt.json()
        assert data["token"].startswith(EPHEMERAL_TOKEN_PREFIX)
        assert data["max_calls"] == 5
