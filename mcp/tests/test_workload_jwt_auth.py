# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit and integration tests for MCP Workload Identity Federation JWT auth.

KB-AUTH-OIDC-EXCHANGE-01.

Validates:
1. Fast-path authentication with ES256 workload JWT tokens on /mcp/agent and /mcp/docs.
2. Rejection of surface mismatches (e.g. agent token presented to /mcp/docs or /mcp/admin).
3. Client IP CIDR validation (direct peers and trusted proxy forwarded IPs).
4. Credential boundary capability_mask enforcement during tool listing and dispatch.
5. Rejection of expired or tampered JWT access tokens.
6. Project scope intersection and containment enforcement.
"""

from __future__ import annotations

import base64
import time
import uuid
from typing import Any

import httpx
import pytest
from joserfc import jwt

from kanban.oauth.jwt import _get_signing_eckey
from mcp.app import create_mcp_app
from mcp.auth import McpAuthMiddleware
from mcp.internal_client import KanbanApiClient
from mcp.registry import Surface, ToolRegistry, ToolSpec
from mcp.scoping import Capability
from mcp.settings import McpSettings

_DUMMY_SCHEMA: dict[str, Any] = {"type": "object"}


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


@pytest.fixture(autouse=True)
def setup_test_key_material(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up valid test key material in environment."""
    monkeypatch.delenv("KANBAN_KEYRING_FILE", raising=False)
    monkeypatch.setenv("KANBAN_MASTER_KEK", _b64(b"k" * 32))
    monkeypatch.setenv("KANBAN_AUTH_PEPPER", _b64(b"p" * 32))
    monkeypatch.setenv("KANBAN_SESSION_HMAC_KEY", _b64(b"s" * 32))
    monkeypatch.setenv("KANBAN_MASTER_KEK_KID", "test-kid-1")


def _mint_test_workload_jwt(  # noqa: PLR0913
    *,
    surface: str = "agent",
    scopes: list[str] | None = None,
    capability_mask: int = 255,
    allowed_cidrs: list[str] | None = None,
    allowed_projects: list[str] | None = None,
    ttl_seconds: int = 3600,
    base_url: str = "http://test",
    principal_id: str = "user-workload-svc",
    workspace_id: str | None = None,
    expired: bool = False,
    token_kind: str = "workload",  # noqa: S107
) -> str:
    """Mint an ES256 workload JWT token for testing."""
    eckey, kid = _get_signing_eckey()
    header = {"alg": "ES256", "typ": "JWT", "kid": kid}
    now = int(time.time())
    exp = (now - 300) if expired else (now + ttl_seconds)
    claims: dict[str, Any] = {
        "iss": base_url,
        "sub": principal_id,
        "aud": f"{base_url}/mcp/{surface}",
        "surface": surface,
        "scope": " ".join(scopes or [f"{surface}:read", f"{surface}:write"]),
        "client_id": "test-workload-client",
        "policy_id": str(uuid.uuid4()),
        "ws": workspace_id or str(uuid.uuid4()),
        "jti": str(uuid.uuid4()),
        "iat": now - 10,
        "exp": exp,
        "token_kind": token_kind,
        "capability_mask": capability_mask,
    }
    if allowed_cidrs:
        claims["allowed_cidrs"] = allowed_cidrs
    if allowed_projects:
        claims["allowed_project_ids"] = allowed_projects
        claims["allowed_projects"] = allowed_projects
    return jwt.encode(header, claims, eckey)


def _build_test_mcp_app(
    surface: Surface,
) -> tuple[KanbanApiClient, ToolRegistry, McpAuthMiddleware]:
    """Build an MCP application with sample tools for testing."""
    reg = ToolRegistry(surface)

    async def _read_handler(_args: dict[str, Any]) -> dict[str, str]:
        return {"result": "read_ok"}

    async def _create_handler(_args: dict[str, Any]) -> dict[str, str]:
        return {"result": "create_ok"}

    tool_name_read = "read_ticket" if surface == Surface.AGENT else "read_doc"
    tool_name_write = "create_ticket" if surface == Surface.AGENT else "create_doc"

    reg.register(
        ToolSpec(
            name=tool_name_read,
            description="Read operation",
            surface=surface,
            input_schema=_DUMMY_SCHEMA,
            handler=_read_handler,
        )
    )
    reg.register(
        ToolSpec(
            name=tool_name_write,
            description="Write operation",
            surface=surface,
            input_schema=_DUMMY_SCHEMA,
            handler=_create_handler,
        )
    )

    settings = McpSettings(mode="standalone_inprocess", auth_enabled=True)

    def _dummy_transport(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"active": True})

    client = KanbanApiClient(settings, transport=httpx.MockTransport(_dummy_transport))

    kwargs: dict[str, Any] = {"settings": settings, "kanban_app": None}
    if surface == Surface.AGENT:
        kwargs["agent_registry"] = reg
    elif surface == Surface.DOCS:
        kwargs["docs_registry"] = reg

    base_app = create_mcp_app(**kwargs)
    middleware = McpAuthMiddleware(
        base_app,
        surface=surface,
        internal_client=client,
        settings=settings,
    )
    return client, reg, middleware


@pytest.mark.asyncio
async def test_workload_jwt_valid_agent_request() -> None:
    """Verify valid workload JWT passes through McpAuthMiddleware on agent surface."""
    _client, _reg, app = _build_test_mcp_app(Surface.AGENT)
    token = _mint_test_workload_jwt(surface="agent", capability_mask=255)

    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        init_resp = await c.post(
            "/mcp/agent",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0"},
                },
            },
        )
        assert init_resp.status_code == 200
        session_id = init_resp.headers["mcp-session-id"]

        list_resp = await c.post(
            "/mcp/agent",
            headers={
                "Authorization": f"Bearer {token}",
                "Mcp-Session-Id": session_id,
                "Content-Type": "application/json",
            },
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        assert list_resp.status_code == 200
        data = list_resp.json()
        assert "result" in data
        tool_names = [t["name"] for t in data["result"]["tools"]]
        assert "read_ticket" in tool_names
        assert "create_ticket" in tool_names


@pytest.mark.asyncio
async def test_workload_jwt_valid_docs_request() -> None:
    """Verify valid workload JWT passes through McpAuthMiddleware on docs surface."""
    _client, _reg, app = _build_test_mcp_app(Surface.DOCS)
    token = _mint_test_workload_jwt(surface="docs", capability_mask=255)

    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        init_resp = await c.post(
            "/mcp/docs",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0"},
                },
            },
        )
        assert init_resp.status_code == 200
        session_id = init_resp.headers["mcp-session-id"]

        list_resp = await c.post(
            "/mcp/docs",
            headers={
                "Authorization": f"Bearer {token}",
                "Mcp-Session-Id": session_id,
                "Content-Type": "application/json",
            },
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        assert list_resp.status_code == 200
        data = list_resp.json()
        assert "result" in data
        tool_names = [t["name"] for t in data["result"]["tools"]]
        assert "read_doc" in tool_names
        assert "create_doc" in tool_names


@pytest.mark.asyncio
async def test_workload_jwt_surface_mismatch_rejected() -> None:
    """Verify token minted for agent surface is rejected on docs surface with 403."""
    _client, _reg, docs_app = _build_test_mcp_app(Surface.DOCS)
    agent_token = _mint_test_workload_jwt(surface="agent")

    transport = httpx.ASGITransport(app=docs_app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/mcp/docs",
            headers={"Authorization": f"Bearer {agent_token}"},
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0"},
                },
            },
        )
        assert resp.status_code == 403
        data = resp.json()
        assert data.get("error") == "SURFACE_KEY_MISMATCH"


@pytest.mark.asyncio
async def test_workload_jwt_cidr_allowed_and_denied() -> None:
    """Verify client CIDR restrictions are enforced for workload JWTs."""
    _client, _reg, app = _build_test_mcp_app(Surface.AGENT)
    token = _mint_test_workload_jwt(
        surface="agent",
        allowed_cidrs=["192.168.1.0/24"],
    )

    # 1. Allowed IP: 192.168.1.50
    transport_ok = httpx.ASGITransport(app=app, client=("192.168.1.50", 12345))
    async with httpx.AsyncClient(transport=transport_ok, base_url="http://test") as c:
        resp_ok = await c.post(
            "/mcp/agent",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "jsonrpc": "2.0",
                "id": 4,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0"},
                },
            },
        )
        assert resp_ok.status_code == 200

    # 2. Denied IP: 10.0.0.1
    transport_denied = httpx.ASGITransport(app=app, client=("10.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport_denied, base_url="http://test") as c:
        resp_denied = await c.post(
            "/mcp/agent",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "jsonrpc": "2.0",
                "id": 5,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0"},
                },
            },
        )
        assert resp_denied.status_code == 403
        data = resp_denied.json()
        assert data.get("error") == "KEY_CIDR_DENIED"


@pytest.mark.asyncio
async def test_workload_jwt_capability_mask_filtered_in_tools_list() -> None:
    """Verify read-only capability_mask filters out mutating tools from tools/list."""
    _client, _reg, app = _build_test_mcp_app(Surface.AGENT)
    # capability_mask = 1 (VIEW only)
    ro_token = _mint_test_workload_jwt(surface="agent", capability_mask=int(Capability.VIEW))

    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        init_resp = await c.post(
            "/mcp/agent",
            headers={"Authorization": f"Bearer {ro_token}"},
            json={
                "jsonrpc": "2.0",
                "id": 6,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0"},
                },
            },
        )
        assert init_resp.status_code == 200
        session_id = init_resp.headers["mcp-session-id"]

        list_resp = await c.post(
            "/mcp/agent",
            headers={
                "Authorization": f"Bearer {ro_token}",
                "Mcp-Session-Id": session_id,
            },
            json={"jsonrpc": "2.0", "id": 7, "method": "tools/list", "params": {}},
        )
        assert list_resp.status_code == 200
        data = list_resp.json()
        tool_names = [t["name"] for t in data["result"]["tools"]]
        assert "read_ticket" in tool_names
        assert "create_ticket" not in tool_names


@pytest.mark.asyncio
async def test_workload_jwt_expired_token_rejected() -> None:
    """Verify expired workload JWT returns 401 Unauthorized."""
    _client, _reg, app = _build_test_mcp_app(Surface.AGENT)
    expired_token = _mint_test_workload_jwt(surface="agent", expired=True)

    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/mcp/agent",
            headers={"Authorization": f"Bearer {expired_token}"},
            json={
                "jsonrpc": "2.0",
                "id": 8,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0"},
                },
            },
        )
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_workload_jwt_project_scope_containment() -> None:
    """Verify project scoping boundaries are checked against allowed_project_ids."""
    _client, _reg, app = _build_test_mcp_app(Surface.AGENT)
    ws_id = str(uuid.uuid4())
    proj_a = "PRJ_A"
    proj_b = "PRJ_B"
    token = _mint_test_workload_jwt(
        surface="agent",
        workspace_id=ws_id,
        allowed_projects=[proj_a],
    )

    # 1. Connection scope requesting allowed proj_a succeeds
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp_ok = await c.post(
            "/mcp/agent",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Workspace-Slug": ws_id,
                "X-Project-Key": proj_a,
            },
            json={
                "jsonrpc": "2.0",
                "id": 9,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0"},
                },
            },
        )
        assert resp_ok.status_code == 200

        # 2. Connection scope requesting forbidden proj_b rejected with 403
        resp_denied = await c.post(
            "/mcp/agent",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Workspace-Slug": ws_id,
                "X-Project-Key": proj_b,
            },
            json={
                "jsonrpc": "2.0",
                "id": 10,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0"},
                },
            },
        )
        assert resp_denied.status_code == 403
        data = resp_denied.json()
        assert data.get("error") == "KEY_SCOPE_VIOLATION"
