# Copyright 2026 Kanban Platform Contributors
"""Client-side entity resolver with request-scoped memoization (S11.1)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from mcp.errors import KbMcpError, McpErrorCode

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mcp.internal_client import KanbanApiClient

__all__ = [
    "EntityResolver",
    "ResolvedRef",
]


@dataclass(frozen=True, slots=True)
class ResolvedRef:
    """Resolved entity metadata representing identity, key, and title."""

    id: str
    kind: str
    key: str
    title: str
    canonical_key: str | None = None


class EntityResolver:
    """Request-scoped resolver converting human keys and UUIDs via kanban-api."""

    def __init__(
        self,
        client: KanbanApiClient,
        *,
        subject_token: str | None = None,
        mcp_session_id: str | None = None,
    ) -> None:
        """Initialize resolver with internal API client and caller credentials."""
        self._client: Final[KanbanApiClient] = client
        self._subject_token: Final[str | None] = subject_token
        self._mcp_session_id: Final[str | None] = mcp_session_id
        self._cache: dict[tuple[str, str, str | None, str | None], ResolvedRef] = {}

    async def resolve(
        self,
        kind: str,
        ref: str,
        project: str | None = None,
        workspace: str | None = None,
    ) -> ResolvedRef:
        """Resolve a single entity reference with request-scoped memoization."""
        cache_key = (kind, ref, project, workspace)
        if cache_key in self._cache:
            return self._cache[cache_key]

        params: dict[str, str] = {
            "kind": kind,
            "ref": ref,
        }
        if project is not None:
            params["project"] = project
        if workspace is not None:
            params["workspace"] = workspace

        res = await self._client.request(
            "GET",
            "/api/v1/resolve",
            params=params,
            subject_token=self._subject_token,
            mcp_session_id=self._mcp_session_id,
        )

        if not isinstance(res, dict):
            msg = f"Unexpected non-object response from /api/v1/resolve: {res!r}"
            raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

        canonical_key = res.get("canonical_key")
        resolved = ResolvedRef(
            id=str(res["id"]),
            kind=str(res["kind"]),
            key=str(res["key"]),
            title=str(res["title"]),
            canonical_key=str(canonical_key) if canonical_key is not None else None,
        )
        self._cache[cache_key] = resolved
        return resolved

    async def resolve_many(
        self,
        items: Sequence[tuple[str, str, str | None]],
    ) -> list[ResolvedRef]:
        """Resolve a batch of entity references, deduplicating identical lookups."""
        unique_queries = list(dict.fromkeys(items))
        tasks = [self.resolve(k, r, p) for k, r, p in unique_queries]
        await asyncio.gather(*tasks)
        return [self._cache[(k, r, p, None)] for k, r, p in items]
