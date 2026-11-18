# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Implementation of the read_ticket MCP tool (S11.2, S3.4, KB-P4-04)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from mcp.context import get_current_mcp_context
from mcp.errors import KbMcpError, McpErrorCode
from mcp.help import build_help
from mcp.lod import project_issue

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mcp.context import McpRequestContext

__all__ = [
    "READ_TICKET_SCHEMA",
    "read_ticket",
]

_MAX_COMMENTS_LIMIT: Final[int] = 50
_MAX_IDENTIFIER_LEN: Final[int] = 200

READ_TICKET_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "identifier": {
            "type": "string",
            "description": "Issue ref",
        },
        "workspace": {
            "type": "string",
            "description": "Workspace",
        },
        "lod": {
            "type": "string",
            "enum": ["summary", "standard", "full"],
            "default": "standard",
            "description": "LOD tier",
        },
        "comments_limit": {
            "type": "integer",
            "minimum": 0,
            "maximum": 50,
            "default": 20,
            "description": "Max comments",
        },
    },
    "required": ["identifier"],
    "additionalProperties": False,
}

_ALLOWED_KEYS: Final[frozenset[str]] = frozenset(READ_TICKET_SCHEMA["properties"].keys())


def _validate_read_arguments(arguments: dict[str, Any]) -> None:
    """Strictly validate read_ticket arguments against schema constraints."""
    for key in arguments:
        if key not in _ALLOWED_KEYS:
            msg = f"Unknown parameter '{key}'"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if "identifier" not in arguments:
        msg = "Missing required parameter 'identifier'"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    identifier = arguments["identifier"]
    if not isinstance(identifier, str) or not identifier.strip():
        msg = "identifier must be a non-empty string"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
    if len(identifier) > _MAX_IDENTIFIER_LEN:
        msg = f"identifier length ({len(identifier)}) exceeds maximum of {_MAX_IDENTIFIER_LEN}"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    lod = arguments.get("lod")
    if lod is not None and lod not in ("summary", "standard", "full"):
        msg = f"Invalid lod '{lod}'. Expected 'summary', 'standard', or 'full'"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    comments_limit = arguments.get("comments_limit")
    if comments_limit is not None and (
        not isinstance(comments_limit, int)
        or isinstance(comments_limit, bool)
        or comments_limit < 0
        or comments_limit > _MAX_COMMENTS_LIMIT
    ):
        msg = f"comments_limit must be an integer between 0 and {_MAX_COMMENTS_LIMIT}"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)


def _extract_principal_name(principal: dict[str, Any]) -> str | None:
    """Extract display name from a principal dictionary."""
    h = principal.get("handle")
    if h:
        return str(h) if str(h).startswith("@") else f"@{h}"
    if principal.get("display_name"):
        return f"@{principal['display_name'].lower().replace(' ', '')}"
    if principal.get("id"):
        return str(principal["id"])
    return None


def _extract_assignee_name(item: object) -> str | None:
    """Extract display handle or string representation for an assignee entry."""
    if isinstance(item, str):
        return item
    if not isinstance(item, dict):
        return None
    if item.get("kind") == "free_text" and item.get("free_text"):
        return str(item["free_text"])
    principal = item.get("principal")
    if isinstance(principal, dict):
        return _extract_principal_name(principal)
    if item.get("handle"):
        h = item["handle"]
        return str(h) if str(h).startswith("@") else f"@{h}"
    return None


def _format_assignees(raw_assignees: Sequence[object]) -> list[str]:
    """Format assignee models into human handles or names."""
    results: list[str] = []
    for item in raw_assignees:
        name = _extract_assignee_name(item)
        if name:
            results.append(name)
    return results


def _format_parent(raw_parent: object) -> object:
    """Format parent reference with privacy masking for restricted parents."""
    if raw_parent is None:
        return None
    if isinstance(raw_parent, dict):
        if raw_parent.get("restricted") is True:
            return {"restricted": True, "label": "🔒 Restricted Parent Issue"}
        return raw_parent.get("key") or raw_parent.get("summary")
    return raw_parent


def _compact_link_endpoint(endpoint: object) -> object:
    if not isinstance(endpoint, dict):
        return endpoint
    if endpoint.get("restricted"):
        return {"restricted": True, "label": endpoint.get("label", "🔒 Restricted Object")}
    compact: dict[str, Any] = {}
    if "key" in endpoint:
        compact["key"] = endpoint["key"]
    if endpoint.get("summary"):
        compact["summary"] = endpoint["summary"]
    return compact or endpoint


def _project_compact_link_entries(
    raw_links: list[object],
    endpoint_key: str,
) -> list[dict[str, Any]]:
    """Project compact link entries for outbound or inbound lists."""
    compact_entries: list[dict[str, Any]] = []
    for item in raw_links:
        if not isinstance(item, dict):
            continue
        entry: dict[str, Any] = {"link_type": item.get("link_type")}
        if endpoint_key in item:
            entry[endpoint_key] = _compact_link_endpoint(item[endpoint_key])
        compact_entries.append(entry)
    return compact_entries


async def _load_links(issue_key: str, ctx: McpRequestContext) -> dict[str, Any] | None:
    """Load object links for an issue, returning None when empty or on failure."""
    if ctx.client is None:
        return None
    try:
        links_res = await ctx.client.request(
            "GET",
            f"/api/v1/objects/{issue_key}/links",
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        if not isinstance(links_res, dict):
            return None
    except KbMcpError:
        return None

    raw_outbound = links_res.get("outbound")
    raw_inbound = links_res.get("inbound")
    outbound_list = raw_outbound if isinstance(raw_outbound, list) else []
    inbound_list = raw_inbound if isinstance(raw_inbound, list) else []

    if not outbound_list and not inbound_list:
        return None

    projected: dict[str, Any] = {}
    if outbound_list:
        compact_out = _project_compact_link_entries(outbound_list, "target")
        if compact_out:
            projected["outbound"] = compact_out

    if inbound_list:
        compact_in = _project_compact_link_entries(inbound_list, "source")
        if compact_in:
            projected["inbound"] = compact_in

    if links_res.get("truncated") is True:
        projected["truncated"] = True

    return projected or None


async def _load_comments(issue_key: str, comments_limit: int, ctx: McpRequestContext) -> list[Any]:
    """Load comments for an issue up to limit."""
    if comments_limit <= 0 or ctx.client is None:
        return []
    try:
        comm_res = await ctx.client.request(
            "GET",
            f"/api/v1/issues/{issue_key}/comments",
            params={"limit": comments_limit},
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        if isinstance(comm_res, dict):
            raw_items = comm_res.get("items", [])
            return raw_items if isinstance(raw_items, list) else []
    except KbMcpError:
        return []
    return []


async def _load_activity(issue_key: str, ctx: McpRequestContext) -> list[Any]:
    """Load activity history for an issue."""
    if ctx.client is None:
        return []
    try:
        act_res = await ctx.client.request(
            "GET",
            f"/api/v1/issues/{issue_key}/activity",
            params={"limit": 50},
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        if isinstance(act_res, dict):
            raw_items = act_res.get("items", [])
            return raw_items if isinstance(raw_items, list) else []
    except KbMcpError:
        return []
    return []


async def read_ticket(arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute read_ticket tool loading issue details, links, comments, and activity."""
    _validate_read_arguments(arguments)

    identifier = arguments["identifier"].strip()
    lod = arguments.get("lod", "standard")
    comments_limit = arguments.get("comments_limit", 20)

    ctx = get_current_mcp_context()
    if ctx is None or ctx.client is None:
        msg = "MCP request context unavailable"
        raise KbMcpError(McpErrorCode.INTERNAL, msg)

    if identifier == "help":
        return await build_help(
            "read_ticket",
            client=ctx.client,
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )

    req_params: dict[str, Any] = {}
    if arguments.get("workspace"):
        req_params["workspace"] = arguments["workspace"]

    try:
        issue_data = await ctx.client.request(
            "GET",
            f"/api/v1/issues/{identifier}",
            params=req_params or None,
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
    except KbMcpError as err:
        if err.code == McpErrorCode.NOT_FOUND:
            raise KbMcpError(McpErrorCode.NOT_FOUND, "ticket not found") from None
        raise

    if not isinstance(issue_data, dict):
        raise KbMcpError(McpErrorCode.NOT_FOUND, "ticket not found")

    issue_key = str(issue_data.get("key", identifier))
    state_val = issue_data.get("state")
    state_str = (
        str(state_val.get("name", "")) if isinstance(state_val, dict) else str(state_val or "")
    )

    pri_val = issue_data.get("priority")
    pri_str = str(pri_val.get("slug", "")) if isinstance(pri_val, dict) else str(pri_val or "")

    links: dict[str, Any] | None = None
    if lod in ("standard", "full"):
        links = await _load_links(issue_key, ctx)

    comments: list[Any] | None = None
    activity: list[Any] | None = None
    if lod == "full":
        comments = await _load_comments(issue_key, comments_limit, ctx)
        activity = await _load_activity(issue_key, ctx)

    labels_raw = issue_data.get("labels", [])
    labels_list = [
        lbl.get("name") if isinstance(lbl, dict) else str(lbl)
        for lbl in (labels_raw if isinstance(labels_raw, list) else [])
        if lbl is not None
    ]

    etag = issue_data.get("description_sha256") or issue_data.get("etag")

    normalized_issue: dict[str, Any] = {
        "key": issue_key,
        "workspace": issue_data.get("workspace"),
        "summary": issue_data.get("summary", ""),
        "state": state_str,
        "priority": pri_str,
        "assignees": _format_assignees(issue_data.get("assignees", [])),
        "description_markdown": issue_data.get("description_markdown", ""),
        "labels": labels_list,
        "cycle": issue_data.get("cycle_id"),
        "modules": issue_data.get("module_ids"),
        "parent": _format_parent(issue_data.get("parent")),
        "start_date": issue_data.get("start_date"),
        "due_date": issue_data.get("due_date"),
        "links": links,
        "etag": etag,
        "access": issue_data.get("access"),
        "access_manifest": issue_data.get("access_manifest"),
        "comments": comments,
        "activity": activity,
        "provenance": issue_data.get("provenance"),
    }

    return project_issue(normalized_issue, lod)
