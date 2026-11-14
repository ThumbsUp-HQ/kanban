# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tool manage_stickies: Project stickies lifecycle and promotion signals (S11.3)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from mcp.context import current_internal_client, current_subject_token
from mcp.errors import KbMcpError, McpErrorCode
from mcp.registry import Surface, ToolSpec

if TYPE_CHECKING:
    from mcp.internal_client import KanbanApiClient

__all__ = [
    "ALLOWED_STICKY_COLORS",
    "create_manage_stickies_tool",
    "manage_stickies_handler",
]

_TOOL_NAME: Final[str] = "manage_stickies"
_DESCRIPTION: Final[str] = (
    "Manage Project Stickies: list, create, edit, recolor, and inspect promotion recommendation."
)

ALLOWED_STICKY_COLORS: Final[frozenset[str]] = frozenset(
    {"amber", "mint", "sky", "lavender", "coral", "slate"}
)
_MAX_STICKY_BYTES: Final[int] = 65_536  # 64 KiB

_INPUT_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["list", "create", "edit", "recolor", "help"],
            "description": "Lifecycle action to perform",
        },
        "project": {
            "type": "string",
            "description": "Project key or UUID (required except for action='help')",
        },
        "sticky": {
            "type": "string",
            "description": "Sticky UUID for edit or recolor",
        },
        "body_markdown": {
            "type": "string",
            "description": "Markdown body content (<= 65,536 bytes)",
        },
        "color": {
            "type": "string",
            "enum": ["amber", "mint", "sky", "lavender", "coral", "slate"],
            "description": "Palette color token",
        },
    },
    "required": ["action"],
    "additionalProperties": False,
}


def _extract_sticky_title(body: str | None, default_color: str) -> str:
    """Derive display title from first line of Markdown or default color."""
    if not body:
        return f"Sticky {default_color}"
    first_line = body.strip().splitlines()[0] if body.strip() else ""
    clean = first_line.lstrip("#").strip()
    return clean[:80] if clean else f"Sticky {default_color}"


async def manage_stickies_handler(  # noqa: C901, PLR0912, PLR0915
    arguments: dict[str, Any],
    *,
    client: KanbanApiClient | None = None,
    subject_token: str | None = None,
) -> dict[str, Any]:
    """Execute manage_stickies tool invocation."""
    action = arguments.get("action")
    if not isinstance(action, str):
        msg = "Parameter 'action' is required"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    action_lower = action.strip().lower()
    if action_lower not in ("list", "create", "edit", "recolor", "help"):
        msg = f"Unknown action '{action}'. Must be one of: list, create, edit, recolor, help"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if action_lower == "help":
        return {
            "tool": _TOOL_NAME,
            "actions": ["list", "create", "edit", "recolor"],
            "colors": sorted(ALLOWED_STICKY_COLORS),
            "max_body_bytes": _MAX_STICKY_BYTES,
        }

    project = arguments.get("project")
    if not project or not isinstance(project, str):
        msg = "Parameter 'project' is required"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    color = arguments.get("color")
    if color is not None:
        if not isinstance(color, str) or color.strip().lower() not in ALLOWED_STICKY_COLORS:
            msg = f"Invalid color '{color}'. Must be one of: {sorted(ALLOWED_STICKY_COLORS)}"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
        color = color.strip().lower()

    body_markdown = arguments.get("body_markdown")
    if body_markdown is not None:
        if not isinstance(body_markdown, str):
            body_markdown = str(body_markdown)
        body_len = len(body_markdown.encode("utf-8"))
        if body_len > _MAX_STICKY_BYTES:
            msg = f"Sticky body ({body_len} bytes) exceeds limit of {_MAX_STICKY_BYTES} bytes"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    active_client = client or current_internal_client.get()
    active_token = subject_token or current_subject_token.get()

    if active_client is None:
        msg = "Internal API client is unavailable"
        raise KbMcpError(McpErrorCode.UPSTREAM_UNAVAILABLE, msg)

    # List action handler
    if action_lower == "list":
        resp = await active_client.request(
            "GET",
            f"/api/v1/projects/{project}/stickies",
            subject_token=active_token,
        )
        stickies_list: list[dict[str, Any]] = []
        if isinstance(resp, list):
            for s in resp:
                if not isinstance(s, dict):
                    continue
                s_color = s.get("color_token", "amber")
                s_body = s.get("body_markdown", "")
                title = _extract_sticky_title(s_body, s_color)
                stickies_list.append(
                    {
                        "id": str(s.get("id")),
                        "color": s_color,
                        "title": title,
                        "promotion_recommended": bool(s.get("promotion_recommended", False)),
                    }
                )
        return {
            "project": str(project),
            "stickies": stickies_list,
        }

    # Create action handler
    if action_lower == "create":
        create_payload = {
            "body_markdown": body_markdown or "",
            "color_token": color or "amber",
        }
        resp = await active_client.request(
            "POST",
            f"/api/v1/projects/{project}/stickies",
            json_data=create_payload,
            subject_token=active_token,
        )
        if not isinstance(resp, dict):
            msg = "Failed to create sticky upstream"
            raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

        s_id = str(resp.get("id", ""))
        s_color = str(resp.get("color_token", color or "amber"))
        s_body = str(resp.get("body_markdown", body_markdown or ""))
        return {
            "status": "created",
            "id": s_id,
            "color": s_color,
            "title": _extract_sticky_title(s_body, s_color),
            "promotion_recommended": bool(resp.get("promotion_recommended", False)),
        }

    # Edit or recolor action handler
    sticky_id = arguments.get("sticky")
    if not sticky_id or not isinstance(sticky_id, str):
        msg = f"Parameter 'sticky' (UUID) is required for action='{action_lower}'"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    patch_payload: dict[str, Any] = {}
    if action_lower == "edit":
        if body_markdown is None:
            msg = "Parameter 'body_markdown' is required for action='edit'"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
        patch_payload["body_markdown"] = body_markdown
        if color:
            patch_payload["color_token"] = color
    elif action_lower == "recolor":
        if not color:
            msg = "Parameter 'color' is required for action='recolor'"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
        patch_payload["color_token"] = color

    req_headers: dict[str, str] = {}
    if action_lower == "edit":
        req_headers["If-Match"] = "*"

    resp = await active_client.request(
        "PATCH",
        f"/api/v1/stickies/{sticky_id}",
        json_data=patch_payload,
        headers=req_headers,
        subject_token=active_token,
    )
    if not isinstance(resp, dict):
        msg = "Failed to update sticky upstream"
        raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

    res_color = str(resp.get("color_token", color or "amber"))
    res_body = str(resp.get("body_markdown", ""))
    return {
        "status": "updated" if action_lower == "edit" else "recolored",
        "id": str(resp.get("id", sticky_id)),
        "color": res_color,
        "title": _extract_sticky_title(res_body, res_color),
        "promotion_recommended": bool(resp.get("promotion_recommended", False)),
    }


def create_manage_stickies_tool(client: KanbanApiClient | None = None) -> ToolSpec:
    """Construct ToolSpec for manage_stickies."""

    async def _handler(arguments: dict[str, Any], **kwargs: object) -> dict[str, Any]:
        raw_client = kwargs.get("client") or kwargs.get("internal_client")
        active_client = client or (raw_client if hasattr(raw_client, "request") else None)
        raw_token = kwargs.get("subject_token")
        active_token = str(raw_token) if raw_token is not None else None
        return await manage_stickies_handler(
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
