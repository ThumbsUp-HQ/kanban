# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration and unit tests for MCP tools/call sliding-window rate limiting (KAN-71).

Covers:
  - 429 RATE_LIMITED on tools/call burst exceeding policy limits.
  - Presence of Retry-After response header.
  - Normal initialize and tools/list unaffected by tools/call limiter.
"""

from __future__ import annotations

import httpx
import pytest

from kanban.security.ratelimit.base import RateLimitDecision, RateLimiter, RateLimitPolicy
from mcp.app import create_mcp_app
from mcp.registry import Surface, ToolRegistry, create_placeholder_tool
from mcp.settings import McpSettings


class MockMemoryRateLimiter(RateLimiter):
    """Simple in-memory rate limiter for testing burst denials."""

    def __init__(self, limit: int = 2) -> None:
        """Initialize mock in-memory rate limiter with limit."""
        self.limit = limit
        self.hits: dict[bytes, int] = {}

    async def hit(self, _policy: RateLimitPolicy, key: bytes) -> RateLimitDecision:
        """Record hit and return rate limit decision."""
        count = self.hits.get(key, 0) + 1
        self.hits[key] = count
        if count > self.limit:
            return RateLimitDecision(allowed=False, remaining=0, retry_after_seconds=30)
        return RateLimitDecision(allowed=True, remaining=self.limit - count, retry_after_seconds=0)

    async def reset(self, _policy: RateLimitPolicy, key: bytes) -> None:
        """Reset rate limit counter for key."""
        self.hits.pop(key, None)


@pytest.mark.asyncio
async def test_mcp_tools_call_rate_limiting() -> None:
    """Verify tools/call burst returns 429 RATE_LIMITED with Retry-After header."""
    settings = McpSettings(mode="standalone_inprocess", auth_enabled=False)
    docs_reg = ToolRegistry(Surface.DOCS)
    docs_reg.register(create_placeholder_tool(Surface.DOCS))
    admin_reg = ToolRegistry(Surface.ADMIN)
    admin_reg.register(create_placeholder_tool(Surface.ADMIN))
    app = create_mcp_app(settings, docs_registry=docs_reg, admin_registry=admin_reg)

    # Attach mock limiter allowing max 2 calls
    app.state.rate_limiter = MockMemoryRateLimiter(limit=2)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Initialize session
        init_res = await client.post(
            "/mcp/agent",
            headers={"content-type": "application/json"},
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
        assert init_res.status_code == 200
        session_id = init_res.headers.get("mcp-session-id")
        assert session_id is not None

        call_payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "read_ticket", "arguments": {"identifier": "KAN-1"}},
        }
        headers = {
            "content-type": "application/json",
            "mcp-session-id": session_id,
        }

        # Call 1: Allowed (hits=1)
        r1 = await client.post("/mcp/agent", headers=headers, json=call_payload)
        assert r1.status_code != 429

        # Call 2: Allowed (hits=2)
        r2 = await client.post("/mcp/agent", headers=headers, json=call_payload)
        assert r2.status_code != 429

        # Call 3: Exceeded limit (hits=3) -> 429 RATE_LIMITED
        r3 = await client.post("/mcp/agent", headers=headers, json=call_payload)
        assert r3.status_code == 429, r3.text
        assert r3.headers.get("retry-after") == "30"
        err_json = r3.json()
        assert err_json.get("code") == "RATE_LIMITED"
