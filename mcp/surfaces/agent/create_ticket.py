# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Implementation of the create_ticket MCP tool (KB-P4-05)."""

from __future__ import annotations

from typing import Any, Final

from mcp.context import get_current_mcp_context
from mcp.errors import KbMcpError, McpErrorCode
from mcp.help import build_help

__all__ = [
    "CREATE_TICKET_SCHEMA",
    "create_ticket",
]

_MAX_NODES_PER_CALL: Final[int] = 50
_MAX_CHILDREN_PER_NODE: Final[int] = 49
_MAX_DEPTH: Final[int] = 6
_MAX_SUMMARY_LEN: Final[int] = 500
_MAX_DESCRIPTION_BYTES: Final[int] = 1048576

CREATE_TICKET_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "project": {"type": "string", "description": "Project key or identifier (required)"},
        "summary": {
            "type": "string",
            "minLength": 1,
            "maxLength": 500,
            "description": "Issue summary (required, 1..500 characters)",
        },
        "description_markdown": {
            "type": "string",
            "description": "Markdown description (<= 1,048,576 bytes UTF-8)",
        },
        "state": {
            "type": "string",
            "description": "Workflow state name or UUID (default: project default state)",
        },
        "priority": {
            "type": "string",
            "description": "Priority slug or UUID (e.g. 'high')",
        },
        "assignees": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 20,
            "description": "Assignees: @handle, 'Vendor QA' (free text), or UUID",
        },
        "labels": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 20,
            "description": "Project label names or UUIDs",
        },
        "cycle": {
            "type": "string",
            "description": "Cycle name, key, or UUID",
        },
        "modules": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 20,
            "description": "Module names or UUIDs (omitted -> project defaults if enabled)",
        },
        "parent": {
            "type": "string",
            "description": "Existing parent issue key or UUID",
        },
        "start_date": {
            "type": "string",
            "format": "date",
            "description": "Start date (YYYY-MM-DD)",
        },
        "due_date": {
            "type": "string",
            "format": "date",
            "description": "Due date (YYYY-MM-DD)",
        },
        "children": {
            "type": "array",
            "maxItems": 49,
            "items": {"$ref": "#"},
            "description": "Child sub-issues to create recursively (max 49 direct children)",
        },
    },
    "required": ["project", "summary"],
    "additionalProperties": False,
}

_ALLOWED_ROOT_KEYS: Final[frozenset[str]] = frozenset(CREATE_TICKET_SCHEMA["properties"].keys())
_ALLOWED_CHILD_KEYS: Final[frozenset[str]] = frozenset(
    k for k in CREATE_TICKET_SCHEMA["properties"] if k != "project"
)


def _count_tree_nodes(node: dict[str, Any]) -> int:
    """Count total issues in the tree structure."""
    children = node.get("children", [])
    if not isinstance(children, list):
        return 1
    return 1 + sum(_count_tree_nodes(c) for c in children if isinstance(c, dict))


def _compute_tree_height(node: dict[str, Any]) -> int:
    """Compute maximum height of the tree structure."""
    children = node.get("children", [])
    if not isinstance(children, list) or not children:
        return 1
    child_heights = [_compute_tree_height(c) for c in children if isinstance(c, dict)]
    return 1 + max(child_heights) if child_heights else 1


def _validate_node_scalars(node: dict[str, Any]) -> None:
    """Validate summary, description, and date scalar properties."""
    if "summary" not in node:
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, "Missing required parameter 'summary'")

    summary = node["summary"]
    if not isinstance(summary, str) or not summary.strip():
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, "summary must be a non-empty string")
    if len(summary.strip()) > _MAX_SUMMARY_LEN:
        msg = f"summary length ({len(summary.strip())}) exceeds maximum of {_MAX_SUMMARY_LEN}"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    desc = node.get("description_markdown")
    if desc is not None:
        if not isinstance(desc, str):
            raise KbMcpError(
                McpErrorCode.VALIDATION_FAILED, "description_markdown must be a string"
            )
        if len(desc.encode("utf-8")) > _MAX_DESCRIPTION_BYTES:
            raise KbMcpError(
                McpErrorCode.VALIDATION_FAILED,
                f"description_markdown exceeds maximum of {_MAX_DESCRIPTION_BYTES} bytes",
            )

    start_date = node.get("start_date")
    due_date = node.get("due_date")
    if start_date is not None and due_date is not None and str(due_date) < str(start_date):
        raise KbMcpError(
            McpErrorCode.VALIDATION_FAILED, "due_date cannot be earlier than start_date"
        )


def _validate_tree_node(node: dict[str, Any], *, is_root: bool) -> None:
    """Recursively validate tree nodes against structural and bounds constraints."""
    allowed_keys = _ALLOWED_ROOT_KEYS if is_root else _ALLOWED_CHILD_KEYS
    for k in node:
        if k not in allowed_keys:
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, f"Unknown parameter '{k}'")

    _validate_node_scalars(node)

    children = node.get("children")
    if children is not None:
        if not isinstance(children, list):
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, "children must be an array")
        if len(children) > _MAX_CHILDREN_PER_NODE:
            msg = f"children cannot exceed {_MAX_CHILDREN_PER_NODE} items per node"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
        for child in children:
            if not isinstance(child, dict):
                raise KbMcpError(McpErrorCode.VALIDATION_FAILED, "child nodes must be JSON objects")
            _validate_tree_node(child, is_root=False)


async def create_ticket(arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute create_ticket MCP tool to atomically create a ticket or parent-child tree."""
    ctx = get_current_mcp_context()
    if ctx is None or ctx.client is None:
        msg = "MCP request context unavailable"
        raise KbMcpError(McpErrorCode.INTERNAL, msg)

    project_arg = arguments.get("project")
    summary_arg = arguments.get("summary")
    if project_arg == "help" or summary_arg == "help":
        return await build_help(
            "create_ticket",
            client=ctx.client,
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )

    if "project" not in arguments:
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, "Missing required parameter 'project'")

    if not isinstance(project_arg, str) or not project_arg.strip():
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, "project must be a non-empty string")

    _validate_tree_node(arguments, is_root=True)

    total_nodes = _count_tree_nodes(arguments)
    if total_nodes > _MAX_NODES_PER_CALL:
        msg = f"Total nodes per call ({total_nodes}) exceeds maximum of {_MAX_NODES_PER_CALL}"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    tree_height = _compute_tree_height(arguments)
    if tree_height > _MAX_DEPTH:
        msg = f"Tree depth ({tree_height}) exceeds maximum hierarchy depth of {_MAX_DEPTH}"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    project = project_arg.strip()
    payload = dict(arguments)
    payload.pop("project", None)

    res = await ctx.client.request(
        "POST",
        f"/api/v1/projects/{project}/issue-trees",
        json_data=payload,
        subject_token=ctx.subject_token,
        mcp_session_id=ctx.session_id,
    )

    if not isinstance(res, dict):
        msg = "Unexpected response from issue tree creation"
        raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

    root_raw = res.get("root", {})
    children_raw = res.get("children", [])

    return {
        "created": res.get("created", 1),
        "root": {
            "key": str(root_raw.get("key", "")),
            "summary": str(root_raw.get("summary", "")),
            "state": str(root_raw.get("state", "")),
            "priority": str(root_raw.get("priority", "")),
        },
        "children": [
            {
                "key": str(c.get("key", "")),
                "summary": str(c.get("summary", "")),
                "parent": str(c.get("parent", "")),
            }
            for c in (children_raw if isinstance(children_raw, list) else [])
            if isinstance(c, dict)
        ],
    }
