# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Implementation of the search_tickets MCP tool (S11.2, KB-P4-04)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from mcp.context import get_current_mcp_context
from mcp.errors import KbMcpError, McpErrorCode
from mcp.lod import project_issue
from mcp.resolver import EntityResolver

if TYPE_CHECKING:
    from mcp.context import McpRequestContext

__all__ = [
    "SEARCH_TICKETS_SCHEMA",
    "search_tickets",
]

_MIN_LIMIT: Final[int] = 1
_MAX_LIMIT: Final[int] = 50
_MAX_ARRAY_ITEMS: Final[int] = 20
_MAX_QUERY_LEN: Final[int] = 500
_MAX_CURSOR_LEN: Final[int] = 200

SEARCH_TICKETS_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "maxLength": 500,
            "description": "Search query",
        },
        "workspace": {
            "type": "string",
            "description": "Workspace slug",
        },
        "project": {
            "type": "string",
            "description": "Project ref",
        },
        "states": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 20,
            "description": "State filters",
        },
        "assignees": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 20,
            "description": "Assignee filters",
        },
        "cycle": {
            "type": "string",
            "description": "Cycle filter",
        },
        "modules": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 20,
            "description": "Module filters",
        },
        "labels": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 20,
            "description": "Label filters",
        },
        "blocked": {
            "type": "boolean",
            "description": "Blocked filter",
        },
        "gate_status": {
            "type": "string",
            "enum": ["pending", "approved", "rejected"],
            "description": "Gate status filter",
        },
        "mode": {
            "type": "string",
            "enum": ["lexical", "hybrid"],
            "default": "lexical",
            "description": "Search mode",
        },
        "lod": {
            "type": "string",
            "enum": ["summary", "standard"],
            "default": "summary",
            "description": "LOD tier",
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 50,
            "default": 20,
            "description": "Max results",
        },
        "cursor": {
            "type": "string",
            "maxLength": 200,
            "description": "Cursor",
        },
    },
    "additionalProperties": False,
}

_ALLOWED_KEYS: Final[frozenset[str]] = frozenset(SEARCH_TICKETS_SCHEMA["properties"].keys())


def _validate_keys(arguments: dict[str, Any]) -> None:
    """Validate argument dictionary keys against allowed property set."""
    for key in arguments:
        if key not in _ALLOWED_KEYS:
            msg = f"Unknown parameter '{key}'"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)


def _validate_paging_and_text(arguments: dict[str, Any]) -> None:
    """Validate limit, query string, and cursor constraints."""
    limit = arguments.get("limit")
    if limit is not None and (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or limit < _MIN_LIMIT
        or limit > _MAX_LIMIT
    ):
        msg = f"limit must be an integer between {_MIN_LIMIT} and {_MAX_LIMIT}"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    query = arguments.get("query")
    if query is not None:
        if not isinstance(query, str):
            msg = "query must be a string"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
        if len(query) > _MAX_QUERY_LEN:
            msg = f"query length ({len(query)}) exceeds maximum of {_MAX_QUERY_LEN}"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    cursor = arguments.get("cursor")
    if cursor is not None:
        if not isinstance(cursor, str):
            msg = "cursor must be a string"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
        if len(cursor) > _MAX_CURSOR_LEN:
            msg = f"cursor length ({len(cursor)}) exceeds maximum of {_MAX_CURSOR_LEN}"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)


def _validate_enums(arguments: dict[str, Any]) -> None:
    """Validate lod, mode, and gate_status enum constraints."""
    lod = arguments.get("lod")
    if lod is not None and lod not in ("summary", "standard"):
        msg = f"Invalid lod '{lod}'. Expected 'summary' or 'standard'"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    mode = arguments.get("mode")
    if mode is not None and mode not in ("lexical", "hybrid"):
        msg = f"Invalid mode '{mode}'. Expected 'lexical' or 'hybrid'"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    gate_status = arguments.get("gate_status")
    if gate_status is not None and gate_status not in ("pending", "approved", "rejected"):
        msg = f"Invalid gate_status '{gate_status}'. Expected 'pending', 'approved', or 'rejected'"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)


def _validate_collections_and_flags(arguments: dict[str, Any]) -> None:
    """Validate array items and boolean flags."""
    for arr_field in ("states", "assignees", "modules", "labels"):
        val = arguments.get(arr_field)
        if val is None:
            continue
        if not isinstance(val, list):
            msg = f"{arr_field} must be an array of strings"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
        if len(val) > _MAX_ARRAY_ITEMS:
            msg = f"{arr_field} exceeds maximum of {_MAX_ARRAY_ITEMS} items"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
        for item in val:
            if not isinstance(item, str):
                msg = f"All items in {arr_field} must be strings"
                raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    blocked = arguments.get("blocked")
    if blocked is not None and not isinstance(blocked, bool):
        msg = "blocked must be a boolean"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)


def _validate_search_arguments(arguments: dict[str, Any]) -> None:
    """Strictly validate input arguments against schema constraints."""
    _validate_keys(arguments)
    _validate_paging_and_text(arguments)
    _validate_enums(arguments)
    _validate_collections_and_flags(arguments)


async def _resolve_project_key(
    resolver: EntityResolver, project_ref: str | None
) -> tuple[bool, str | None]:
    """Resolve project reference, returning (found, project_key)."""
    if project_ref is None:
        return True, None
    try:
        resolved_proj = await resolver.resolve("project", project_ref)
    except KbMcpError as err:
        if err.code == McpErrorCode.NOT_FOUND:
            return False, None
        raise
    else:
        return True, resolved_proj.key


async def _resolve_assignees(resolver: EntityResolver, assignees_raw: list[str]) -> list[str]:
    """Resolve assignee handles or UUIDs, passing 'me' verbatim."""
    assignee_ids: list[str] = []
    for a in assignees_raw:
        if a.strip().lower() == "me":
            assignee_ids.append("me")
        else:
            resolved_user = await resolver.resolve("user", a)
            assignee_ids.append(str(resolved_user.id))
    return assignee_ids


async def _compose_search_filters(
    resolver: EntityResolver,
    arguments: dict[str, Any],
    project_key: str | None,
) -> dict[str, Any]:
    """Resolve entity references into canonical ID filter mappings."""
    filters: dict[str, Any] = {}

    states_raw = arguments.get("states")
    if states_raw:
        resolved_states = [
            await resolver.resolve("state", s, project=project_key) for s in states_raw
        ]
        filters["state_ids"] = [str(st.id) for st in resolved_states]

    assignees_raw = arguments.get("assignees")
    if assignees_raw:
        filters["assignee_ids"] = await _resolve_assignees(resolver, assignees_raw)

    cycle_ref = arguments.get("cycle")
    if cycle_ref is not None:
        resolved_cycle = await resolver.resolve("cycle", cycle_ref, project=project_key)
        filters["cycle_ids"] = [str(resolved_cycle.id)]

    modules_raw = arguments.get("modules")
    if modules_raw:
        resolved_modules = [
            await resolver.resolve("module", m, project=project_key) for m in modules_raw
        ]
        filters["module_ids"] = [str(mod.id) for mod in resolved_modules]

    labels_raw = arguments.get("labels")
    if labels_raw:
        resolved_labels = [
            await resolver.resolve("label", lbl, project=project_key) for lbl in labels_raw
        ]
        filters["label_ids"] = [str(lbl.id) for lbl in resolved_labels]

    if arguments.get("blocked") is not None:
        filters["blocked"] = arguments["blocked"]

    if arguments.get("gate_status") == "pending":
        filters["gate_status"] = "pending"

    return filters


async def _execute_search_request(
    ctx: McpRequestContext,
    payload: dict[str, Any],
    lod: str,
) -> dict[str, Any]:
    """Invoke search API endpoint and project items to specified LOD."""
    if ctx.client is None:
        msg = "Internal API client unavailable"
        raise KbMcpError(McpErrorCode.INTERNAL, msg)
    res = await ctx.client.request(
        "POST",
        "/api/v1/search/issues",
        json_data=payload,
        subject_token=ctx.subject_token,
        mcp_session_id=ctx.session_id,
    )

    if not isinstance(res, dict):
        msg = f"Unexpected response from search API: {res!r}"
        raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

    raw_items = res.get("items", [])
    total = int(res.get("total", 0))
    next_cursor = res.get("next_cursor")

    projected_items = [
        project_issue(it, lod) for it in (raw_items if isinstance(raw_items, list) else [])
    ]

    out: dict[str, Any] = {
        "mode": "lexical",
        "total": total,
        "items": projected_items,
    }
    if next_cursor:
        out["next_cursor"] = next_cursor
    return out


async def search_tickets(arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute search_tickets tool under caller permissions."""
    _validate_search_arguments(arguments)

    gate_status = arguments.get("gate_status")
    if gate_status in ("approved", "rejected"):
        return {
            "mode": "lexical",
            "total": 0,
            "items": [],
            "note": "gate history available in Phase 5",
        }

    ctx = get_current_mcp_context()
    if ctx is None or ctx.client is None:
        msg = "MCP request context unavailable"
        raise KbMcpError(McpErrorCode.INTERNAL, msg)

    resolver = EntityResolver(
        ctx.client,
        subject_token=ctx.subject_token,
        mcp_session_id=ctx.session_id,
    )

    proj_found, project_key = await _resolve_project_key(resolver, arguments.get("project"))
    if not proj_found:
        return {
            "mode": "lexical",
            "total": 0,
            "items": [],
        }

    filters = await _compose_search_filters(resolver, arguments, project_key)

    limit = arguments.get("limit", 20)
    cursor = arguments.get("cursor")
    query = arguments.get("query", "")
    lod = arguments.get("lod", "summary")
    mode = arguments.get("mode", "lexical")

    payload: dict[str, Any] = {
        "query": query,
        "limit": limit,
        "mode": mode,
    }
    if arguments.get("workspace"):
        payload["workspace"] = arguments["workspace"]
    if project_key:
        payload["project"] = project_key
    if filters:
        payload["filters"] = filters
    if cursor:
        payload["cursor"] = cursor

    return await _execute_search_request(ctx, payload, lod)
