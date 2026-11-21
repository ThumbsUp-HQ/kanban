# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Implementation of the create_ticket MCP tool (KB-P4-05)."""

from __future__ import annotations

from typing import Any, Final

from mcp.context import get_current_mcp_context
from mcp.errors import KbMcpError, McpErrorCode
from mcp.help import build_help
from mcp.lod import extract_issue_sequence
from mcp.protocol import format_cli_example
from mcp.registry import Surface

__all__ = [
    "CREATE_TICKET_SCHEMA",
    "create_ticket",
]

_MAX_NODES_PER_CALL: Final[int] = 50
_MAX_CHILDREN_PER_NODE: Final[int] = 49
_MAX_DEPTH: Final[int] = 6
_MAX_SUMMARY_LEN: Final[int] = 500
_MAX_DESCRIPTION_BYTES: Final[int] = 1048576
_SURROGATE_MIN: Final[int] = 0xD800
_SURROGATE_MAX: Final[int] = 0xDFFF

_CREATE_TICKET_CLI_EXAMPLE: Final[str] = format_cli_example(
    Surface.AGENT, "create_ticket", {"project": "KAN", "summary": "<summary>"}
)

CREATE_TICKET_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "$defs": {
        "child": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 500,
                },
                "description_markdown": {
                    "type": "string",
                },
                "state": {
                    "type": "string",
                },
                "priority": {
                    "type": "string",
                },
                "assignees": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 20,
                },
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 20,
                },
                "cycle": {
                    "type": "string",
                },
                "modules": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 20,
                },
                "start_date": {
                    "type": "string",
                    "format": "date",
                },
                "due_date": {
                    "type": "string",
                    "format": "date",
                },
                "children": {
                    "type": "array",
                    "maxItems": 49,
                    "items": {"$ref": "#/$defs/child"},
                },
            },
            "required": ["summary"],
            "additionalProperties": False,
        },
    },
    "properties": {
        "project": {
            "type": "string",
            "description": "Project ref (root only; inherited by children)",
        },
        "summary": {
            "type": "string",
            "minLength": 1,
            "maxLength": 500,
            "description": "Summary",
        },
        "description_markdown": {
            "type": "string",
            "description": "Description",
        },
        "state": {
            "type": "string",
            "description": "State name or UUID",
        },
        "priority": {
            "type": "string",
            "description": "Priority slug",
        },
        "assignees": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 20,
            "description": "Assignees",
        },
        "labels": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 20,
            "description": "Labels",
        },
        "cycle": {
            "type": "string",
            "description": "Cycle",
        },
        "modules": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 20,
            "description": "Modules",
        },
        "parent": {
            "type": "string",
            "description": "Parent issue ref (root only; omit in children)",
        },
        "start_date": {
            "type": "string",
            "format": "date",
            "description": "Start date",
        },
        "due_date": {
            "type": "string",
            "format": "date",
            "description": "Due date",
        },
        "children": {
            "type": "array",
            "maxItems": 49,
            "items": {"$ref": "#/$defs/child"},
            "description": (
                "Child sub-issues (inherit root project and enclosing parent; "
                "omit project and parent)"
            ),
        },
    },
    "required": ["project", "summary"],
    "additionalProperties": False,
}

_ALLOWED_ROOT_KEYS: Final[frozenset[str]] = frozenset(CREATE_TICKET_SCHEMA["properties"].keys())
_ALLOWED_CHILD_KEYS: Final[frozenset[str]] = frozenset(
    CREATE_TICKET_SCHEMA["$defs"]["child"]["properties"].keys()
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
    if any(_SURROGATE_MIN <= ord(c) <= _SURROGATE_MAX for c in summary):
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, "INVALID_UTF8_SURROGATE")
    if len(summary.strip()) > _MAX_SUMMARY_LEN:
        msg = f"summary length ({len(summary.strip())}) exceeds maximum of {_MAX_SUMMARY_LEN}"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    desc = node.get("description_markdown")
    if desc is not None:
        if not isinstance(desc, str):
            raise KbMcpError(
                McpErrorCode.VALIDATION_FAILED, "description_markdown must be a string"
            )
        if any(_SURROGATE_MIN <= ord(c) <= _SURROGATE_MAX for c in desc):
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, "INVALID_UTF8_SURROGATE")
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


def _validate_child_key(k: str, allowed_keys: frozenset[str]) -> None:
    """Validate invalid child keys and raise self-correcting progressive disclosure error."""
    if k == "project":
        raise KbMcpError(
            McpErrorCode.VALIDATION_FAILED,
            "Parameter 'project' is only allowed on the root ticket",
            hint=(
                "Omit 'project' inside children[]; "
                "child issues automatically inherit the root project."
            ),
            cli_example=_CREATE_TICKET_CLI_EXAMPLE,
        )
    if k == "parent":
        raise KbMcpError(
            McpErrorCode.VALIDATION_FAILED,
            "Parameter 'parent' is only allowed on the root ticket",
            hint=(
                "Omit 'parent' inside children[]; "
                "each child's parent is its enclosing node in children[]."
            ),
            cli_example=_CREATE_TICKET_CLI_EXAMPLE,
        )
    raise KbMcpError(
        McpErrorCode.VALIDATION_FAILED,
        f"Unknown parameter '{k}'",
        hint=f"Allowed parameters: {', '.join(sorted(allowed_keys))}",
    )


def _validate_children(children: object, depth: int) -> None:
    """Validate children list bounds and recursively validate each child node."""
    if not isinstance(children, list):
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, "children must be an array")
    if len(children) > _MAX_CHILDREN_PER_NODE:
        msg = f"children cannot exceed {_MAX_CHILDREN_PER_NODE} items per node"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
    if children and depth >= _MAX_DEPTH:
        msg = f"Tree depth ({depth + 1}) exceeds maximum hierarchy depth of {_MAX_DEPTH}"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
    for child in children:
        if not isinstance(child, dict):
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, "child nodes must be JSON objects")
        _validate_tree_node(child, is_root=False, depth=depth + 1)


def _validate_tree_node(node: dict[str, Any], *, is_root: bool, depth: int = 1) -> None:
    """Recursively validate tree nodes against structural and bounds constraints."""
    if depth > _MAX_DEPTH:
        msg = f"Tree depth ({depth}) exceeds maximum hierarchy depth of {_MAX_DEPTH}"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    allowed_keys = _ALLOWED_ROOT_KEYS if is_root else _ALLOWED_CHILD_KEYS
    for k in node:
        if k not in allowed_keys:
            if not is_root:
                _validate_child_key(k, allowed_keys)
            raise KbMcpError(
                McpErrorCode.VALIDATION_FAILED,
                f"Unknown parameter '{k}'",
                hint=f"Allowed parameters: {', '.join(sorted(allowed_keys))}",
            )

    _validate_node_scalars(node)

    children = node.get("children")
    if children is not None:
        _validate_children(children, depth)


async def create_ticket(arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute create_ticket MCP tool to atomically create a ticket or parent-child tree."""
    ctx = get_current_mcp_context()
    if ctx is None or ctx.client is None:
        msg = "MCP request context unavailable"
        raise KbMcpError(McpErrorCode.INTERNAL, msg)

    project_arg = arguments.get("project")
    summary_arg = arguments.get("summary")
    if project_arg == "help" or summary_arg == "help":
        target_project: str | None = None
        if (
            summary_arg == "help"
            and isinstance(project_arg, str)
            and project_arg.strip()
            and project_arg.strip() != "help"
        ):
            target_project = project_arg.strip()
        return await build_help(
            "create_ticket",
            project=target_project,
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
    root_key = str(root_raw.get("key", ""))
    root_seq = extract_issue_sequence(root_raw, root_key)

    return {
        "created": res.get("created", 1),
        "root": {
            "key": root_key,
            "issue_key": root_key,
            "sequence_number": root_seq,
            "summary": str(root_raw.get("summary", "")),
            "state": str(root_raw.get("state", "")),
            "priority": str(root_raw.get("priority", "")),
        },
        "children": [
            {
                "key": c_key,
                "issue_key": c_key,
                "sequence_number": extract_issue_sequence(c, c_key),
                "summary": str(c.get("summary", "")),
                "parent": str(c.get("parent", "")),
            }
            for c in (children_raw if isinstance(children_raw, list) else [])
            if isinstance(c, dict)
            for c_key in [str(c.get("key", ""))]
        ],
    }
