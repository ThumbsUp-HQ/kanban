# Copyright 2026 Kanban Platform Contributors
"""Test client-side EntityResolver memoization, batching, and error propagation."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from mcp.errors import KbMcpError, McpErrorCode
from mcp.resolver import EntityResolver, ResolvedRef


class DummyApiClient:
    """Mock client for testing EntityResolver."""

    def __init__(
        self, responses: dict[tuple[str, str, str | None], dict[str, Any] | Exception]
    ) -> None:
        """Initialize dummy client with preset mapping."""
        self.responses = responses
        self.call_count = 0
        self.calls: list[dict[str, Any]] = []

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        subject_token: str | None = None,
        mcp_session_id: str | None = None,
    ) -> dict[str, Any]:
        """Simulate API request returning resolved ref or raising error."""
        del subject_token, mcp_session_id
        self.call_count += 1
        p = params or {}
        self.calls.append({"method": method, "path": path, "params": p})
        key = (p["kind"], p["ref"], p.get("project"))
        if key in self.responses:
            val = self.responses[key]
            if isinstance(val, Exception):
                raise val
            return val
        raise KbMcpError(McpErrorCode.NOT_FOUND, f"Entity not found: {key}")


@pytest.mark.asyncio
async def test_resolver_memoization_caches_repeated_calls() -> None:
    """Verify EntityResolver memoizes queries within its instance and does not repeat requests."""
    client = DummyApiClient(
        {
            ("project", "KAN", None): {
                "id": "11111111-1111-1111-1111-111111111111",
                "kind": "project",
                "key": "KAN",
                "title": "Kanban Core",
            }
        }
    )
    resolver = EntityResolver(client)  # type: ignore[arg-type]

    first = await resolver.resolve("project", "KAN")
    assert first == ResolvedRef(
        id="11111111-1111-1111-1111-111111111111",
        kind="project",
        key="KAN",
        title="Kanban Core",
    )
    assert client.call_count == 1

    second = await resolver.resolve("project", "KAN")
    assert second == first
    assert client.call_count == 1  # Memoized, zero network calls!


@pytest.mark.asyncio
async def test_resolver_batch_resolve_many_deduplicates() -> None:
    """Verify resolve_many dedupes identical refs while preserving order and count."""
    client = DummyApiClient(
        {
            ("issue", "KAN-1", "KAN"): {
                "id": "22222222-2222-2222-2222-222222222222",
                "kind": "issue",
                "key": "KAN-1",
                "title": "Issue 1",
            },
            ("issue", "KAN-2", "KAN"): {
                "id": "33333333-3333-3333-3333-333333333333",
                "kind": "issue",
                "key": "KAN-2",
                "title": "Issue 2",
            },
        }
    )
    resolver = EntityResolver(client)  # type: ignore[arg-type]

    batch = [
        ("issue", "KAN-1", "KAN"),
        ("issue", "KAN-2", "KAN"),
        ("issue", "KAN-1", "KAN"),  # Duplicate
    ]
    results = await resolver.resolve_many(batch)
    assert len(results) == 3
    assert results[0].key == "KAN-1"
    assert results[1].key == "KAN-2"
    assert results[2].key == "KAN-1"
    assert client.call_count == 2  # Only 2 distinct calls executed


@pytest.mark.asyncio
async def test_resolver_propagates_kb_mcp_error() -> None:
    """Verify resolver propagates upstream errors unchanged."""
    client = DummyApiClient(
        {
            ("module", "disabled-mod", "KAN"): KbMcpError(
                McpErrorCode.MODULES_DISABLED,
                "Project KAN has modules disabled",
            )
        }
    )
    resolver = EntityResolver(client)  # type: ignore[arg-type]

    with pytest.raises(KbMcpError) as exc_info:
        await resolver.resolve("module", "disabled-mod", project="KAN")
    assert exc_info.value.code == McpErrorCode.MODULES_DISABLED


@pytest.mark.asyncio
async def test_resolver_handles_non_dict_response() -> None:
    """Verify resolver raises UPSTREAM_ERROR when response is not a dict."""
    mock_client = AsyncMock()
    mock_client.request.return_value = "invalid-string-response"
    resolver = EntityResolver(mock_client)

    with pytest.raises(KbMcpError) as exc_info:
        await resolver.resolve("project", "KAN")
    assert exc_info.value.code == McpErrorCode.UPSTREAM_ERROR
