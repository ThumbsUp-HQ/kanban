# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tool search_knowledge: Permission-filtered search across Docs, Pages, and Stickies (S11.3)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from mcp.context import current_internal_client, current_subject_token
from mcp.errors import KbMcpError, McpErrorCode
from mcp.registry import Surface, ToolSpec

if TYPE_CHECKING:
    from mcp.internal_client import KanbanApiClient

__all__ = [
    "create_search_knowledge_tool",
    "search_knowledge_handler",
]

_TOOL_NAME: Final[str] = "search_knowledge"
_DESCRIPTION: Final[str] = (
    "Permission-filtered hybrid search across Docs, Pages, and Stickies "
    "with heading-anchored snippets."
)
_MAX_QUERY_LEN: Final[int] = 500
_MAX_SNIPPET_LEN: Final[int] = 300
_SNIPPET_TRUNCATE_LEN: Final[int] = 297

_INPUT_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "minLength": 1,
            "maxLength": 500,
            "description": "Lexical or semantic search query (1..500 chars)",
        },
        "kinds": {
            "type": "array",
            "items": {"type": "string", "enum": ["doc", "page", "sticky"]},
            "description": "Entity kinds to search (default: [doc, page, sticky])",
        },
        "project": {
            "type": "string",
            "description": "Optional project identifier or UUID scope filter",
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 50,
            "default": 20,
            "description": "Max search hits to return (1..50, default 20)",
        },
        "cursor": {
            "type": "string",
            "description": "Opaque pagination cursor from previous search",
        },
    },
    "required": ["query"],
    "additionalProperties": False,
}


async def search_knowledge_handler(  # noqa: C901, PLR0912
    arguments: dict[str, Any],
    *,
    client: KanbanApiClient | None = None,
    subject_token: str | None = None,
) -> dict[str, Any]:
    """Execute search_knowledge tool invocation."""
    query = arguments.get("query")
    if not isinstance(query, str) or not (1 <= len(query.strip()) <= _MAX_QUERY_LEN):
        msg = f"Query parameter is required and must be between 1 and {_MAX_QUERY_LEN} characters"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    kinds = arguments.get("kinds")
    if kinds is not None:
        if not isinstance(kinds, list) or not all(k in ("doc", "page", "sticky") for k in kinds):
            msg = "Kinds must be an array of 'doc', 'page', or 'sticky'"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
    else:
        kinds = ["doc", "page", "sticky"]

    project = arguments.get("project")
    limit = arguments.get("limit", 20)
    cursor = arguments.get("cursor")

    active_client = client or current_internal_client.get()
    active_token = subject_token or current_subject_token.get()

    if active_client is None:
        msg = "Internal API client is unavailable"
        raise KbMcpError(McpErrorCode.UPSTREAM_UNAVAILABLE, msg)

    payload: dict[str, Any] = {
        "query": query.strip(),
        "kinds": kinds,
        "limit": limit,
    }
    if project:
        payload["project"] = str(project)
    if cursor:
        payload["cursor"] = str(cursor)

    resp = await active_client.request(
        "POST",
        "/api/v1/search/knowledge",
        json_data=payload,
        subject_token=active_token,
    )

    if not isinstance(resp, dict):
        return {"total": 0, "items": []}

    items_raw = resp.get("items", [])
    formatted_items: list[dict[str, Any]] = []

    for it in items_raw:
        if not isinstance(it, dict):
            continue
        kind = it.get("kind", "doc")
        key = it.get("key") or str(it.get("id", ""))
        title = it.get("title", "")
        anchor = it.get("anchor")
        if anchor and not str(anchor).startswith("#"):
            anchor = f"#{anchor}"

        snippet = it.get("snippet", "")
        if len(snippet) > _MAX_SNIPPET_LEN:
            snippet = snippet[:_SNIPPET_TRUNCATE_LEN] + "..."

        hit: dict[str, Any] = {
            "kind": kind,
            "key": key,
            "title": title,
        }
        if anchor:
            hit["anchor"] = anchor
        hit["snippet"] = snippet
        formatted_items.append(hit)

    out: dict[str, Any] = {
        "total": resp.get("total", len(formatted_items)),
        "items": formatted_items,
    }
    if resp.get("next_cursor"):
        out["next_cursor"] = resp["next_cursor"]
    return out


def create_search_knowledge_tool(client: KanbanApiClient | None = None) -> ToolSpec:
    """Construct ToolSpec for search_knowledge."""

    async def _handler(arguments: dict[str, Any], **kwargs: object) -> dict[str, Any]:
        raw_client = kwargs.get("client") or kwargs.get("internal_client")
        active_client = client or (raw_client if hasattr(raw_client, "request") else None)
        raw_token = kwargs.get("subject_token")
        active_token = str(raw_token) if raw_token is not None else None
        return await search_knowledge_handler(
            arguments,
            client=active_client,  # type: ignore[arg-type]
            subject_token=active_token,
        )

    return ToolSpec(
        name=_TOOL_NAME,
        description=_DESCRIPTION,
        input_schema=_INPUT_SCHEMA,
        surface=Surface.DOCS,
        handler=_handler,
    )
