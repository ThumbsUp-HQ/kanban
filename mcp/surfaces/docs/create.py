# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tool create: Creation of Docs, child Pages, and Stickies with inline links (S11.3, KAN-18)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Final

from mcp.context import current_internal_client, current_subject_token, get_current_mcp_context
from mcp.errors import KbMcpError, McpErrorCode
from mcp.registry import Surface, ToolSpec

if TYPE_CHECKING:
    from mcp.internal_client import KanbanApiClient

__all__ = [
    "ALLOWED_STICKY_COLORS",
    "create_docs_create_tool",
    "create_handler",
]

_TOOL_NAME: Final[str] = "create"
_DESCRIPTION: Final[str] = (
    "Create a Doc, child Page under parent, or Sticky note, "
    "optionally attaching typed object links inline."
)

ALLOWED_STICKY_COLORS: Final[frozenset[str]] = frozenset(
    {"amber", "mint", "sky", "lavender", "coral", "slate"}
)

_MAX_TITLE_LEN: Final[int] = 200
_MAX_BODY_BYTES: Final[int] = 1_048_576  # 1 MiB
_MAX_STICKY_BYTES: Final[int] = 65_536  # 64 KiB
_MAX_PAGE_DEPTH: Final[int] = 10

_UUID_REGEX: Final[re.Pattern[str]] = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

_INPUT_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "type": {
            "type": "string",
            "enum": ["DOC", "STICKY", "doc", "sticky"],
            "description": "Entity type to create: DOC or STICKY",
        },
        "title": {
            "type": "string",
            "minLength": 1,
            "maxLength": 200,
            "description": "Document, page, or sticky title (1..200 characters)",
        },
        "project": {
            "type": "string",
            "description": "Project key or UUID scope filter",
        },
        "content": {
            "type": "string",
            "default": "",
            "description": "Markdown body content",
        },
        "parent": {
            "type": "string",
            "description": "Parent doc key or page path for child Page (forbidden for STICKY)",
        },
        "color": {
            "type": "string",
            "enum": ["amber", "mint", "sky", "lavender", "coral", "slate"],
            "default": "amber",
            "description": "Palette color token for STICKY (default 'amber')",
        },
        "links": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Object references to link inline (e.g. ['KAN-1', '+KAN-2'])",
        },
    },
    "required": ["type", "title"],
    "additionalProperties": False,
}


def _parse_link_target(raw: str) -> tuple[str, str]:
    """Parse link target and optional link_type prefix."""
    clean = raw.strip()
    for known_type in ("VERIFIED_BY_DOC", "RELATES_TO", "DERIVED_FROM_STICKY"):
        if clean.startswith(f"{known_type}:"):
            return clean.removeprefix(f"{known_type}:").strip(), known_type
    return clean, "RELATES_TO"


async def _sync_inline_links(  # noqa: C901
    client: KanbanApiClient,
    source_id: str,
    links: list[Any] | dict[str, Any],
    subject_token: str | None,
) -> list[dict[str, Any]]:
    """Synchronize inline links on target Universal Object Graph node."""
    operations: list[tuple[str, str, str]] = []

    if isinstance(links, dict):
        for t in links.get("add", []):
            target_str, link_type = _parse_link_target(str(t))
            operations.append(("add", target_str, link_type))
    elif isinstance(links, list):
        for item in links:
            if isinstance(item, dict):
                action = item.get("action", "add").lower()
                target_str, link_type = _parse_link_target(str(item.get("target", "")))
                if "link_type" in item:
                    link_type = str(item["link_type"])
                operations.append((action, target_str, link_type))
            elif isinstance(item, str):
                s = item.strip()
                if s.startswith("+"):
                    s = s[1:].strip()
                target_str, link_type = _parse_link_target(s)
                operations.append(("add", target_str, link_type))

    results: list[dict[str, Any]] = []
    for action, target, link_type in operations:
        if not target:
            continue
        if action == "add":
            try:
                await client.request(
                    "POST",
                    f"/api/v1/objects/{source_id}/links",
                    json_data={"target": target, "link_type": link_type},
                    subject_token=subject_token,
                )
                results.append({"action": "added", "target": target, "link_type": link_type})
            except KbMcpError as err:
                results.append({"action": "failed", "target": target, "error": err.message})

    return results


async def create_handler(  # noqa: C901, PLR0912, PLR0915
    arguments: dict[str, Any],
    *,
    client: KanbanApiClient | None = None,
    subject_token: str | None = None,
) -> dict[str, Any]:
    """Execute create tool invocation."""
    raw_type = arguments.get("type")
    if not raw_type or not isinstance(raw_type, str):
        msg = "Parameter 'type' ('DOC' or 'STICKY') is required"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    entity_type = raw_type.strip().upper()
    if entity_type not in ("DOC", "STICKY"):
        msg = f"Invalid entity type '{raw_type}'. Must be 'DOC' or 'STICKY'"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    raw_title = arguments.get("title")
    if (
        not raw_title
        or not isinstance(raw_title, str)
        or not (1 <= len(raw_title.strip()) <= _MAX_TITLE_LEN)
    ):
        msg = f"Parameter 'title' is required (1..{_MAX_TITLE_LEN} characters)"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
    title = raw_title.strip()

    project = arguments.get("project")
    if not project:
        ctx = get_current_mcp_context()
        if ctx is not None and getattr(ctx, "connection_scope", None):
            project = getattr(ctx.connection_scope, "project_key", None)

    parent = arguments.get("parent")
    raw_content = arguments.get("content", "")
    content = str(raw_content) if raw_content is not None else ""

    active_client = client or current_internal_client.get()
    active_token = subject_token or current_subject_token.get()

    if active_client is None:
        msg = "Internal API client is unavailable"
        raise KbMcpError(McpErrorCode.UPSTREAM_UNAVAILABLE, msg)

    # -------------------------------------------------------------------------
    # STICKY CREATION
    # -------------------------------------------------------------------------
    if entity_type == "STICKY":
        if parent is not None:
            msg = "Sticky notes do not support 'parent' hierarchy"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        if not project:
            msg = "Parameter 'project' is required for creating a sticky note"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        clean_project = str(project).strip()
        raw_color = arguments.get("color", "amber")
        color = str(raw_color).strip().lower() if raw_color else "amber"
        if color not in ALLOWED_STICKY_COLORS:
            msg = f"Invalid color '{raw_color}'. Must be one of: {sorted(ALLOWED_STICKY_COLORS)}"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        # Content construction for sticky
        if content:
            if content.strip().startswith(f"# {title}") or content.strip().startswith(title):
                body = content
            else:
                body = f"# {title}\n\n{content}"
        else:
            body = f"# {title}"

        body_bytes = len(body.encode("utf-8"))
        if body_bytes > _MAX_STICKY_BYTES:
            msg = f"Sticky body ({body_bytes} bytes) exceeds limit of {_MAX_STICKY_BYTES} bytes"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        create_sticky_payload = {
            "body_markdown": body,
            "color_token": color,
        }
        resp = await active_client.request(
            "POST",
            f"/api/v1/projects/{clean_project}/stickies",
            json_data=create_sticky_payload,
            subject_token=active_token,
        )
        if not isinstance(resp, dict):
            msg = "Failed to create sticky note upstream"
            raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

        sticky_id = str(resp.get("id", ""))
        s_color = str(resp.get("color_token", color))
        etag = str(resp.get("body_sha256") or resp.get("etag", "")).strip().strip('"')

        attached_links: list[dict[str, Any]] = []
        if arguments.get("links"):
            attached_links = await _sync_inline_links(
                active_client,
                sticky_id,
                arguments["links"],
                active_token,
            )

        sticky_out: dict[str, Any] = {
            "status": "created",
            "kind": "sticky",
            "id": sticky_id,
            "color": s_color,
            "title": title,
            "promotion_recommended": bool(resp.get("promotion_recommended", False)),
            "etag": etag,
        }
        if attached_links:
            sticky_out["links"] = attached_links
        return sticky_out

    # -------------------------------------------------------------------------
    # DOC / PAGE CREATION
    # -------------------------------------------------------------------------
    if len(content.encode("utf-8")) > _MAX_BODY_BYTES:
        msg = f"Content exceeds maximum allowed size of {_MAX_BODY_BYTES} bytes"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if parent:
        clean_parent = str(parent).strip().lstrip("/")
        depth_guess = len(clean_parent.split("/"))
        if depth_guess >= _MAX_PAGE_DEPTH:
            msg = (
                f"Maximum page hierarchy depth ({_MAX_PAGE_DEPTH}) exceeded "
                f"under parent '{clean_parent}'"
            )
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        target_parent = (
            clean_parent.removeprefix("docs/") if clean_parent.startswith("docs/") else clean_parent
        )
        page_payload = {
            "title": title,
            "body_markdown": content,
        }
        create_resp = await active_client.request(
            "POST",
            f"/api/v1/docs/{target_parent}/pages",
            json_data=page_payload,
            subject_token=active_token,
        )
        kind = "page"
    else:
        doc_payload: dict[str, Any] = {
            "title": title,
            "body_markdown": content,
        }
        if project:
            clean_proj = str(project).strip()
            if _UUID_REGEX.match(clean_proj):
                doc_payload["project_id"] = clean_proj
            else:
                proj_resp = await active_client.request(
                    "GET", f"/api/v1/projects/{clean_proj}", subject_token=active_token
                )
                if isinstance(proj_resp, dict) and "id" in proj_resp:
                    doc_payload["project_id"] = str(proj_resp["id"])
                else:
                    msg = f"Project '{clean_proj}' not found"
                    raise KbMcpError(McpErrorCode.NOT_FOUND, msg)

        create_resp = await active_client.request(
            "POST",
            "/api/v1/docs",
            json_data=doc_payload,
            subject_token=active_token,
        )
        kind = "doc"

    if not isinstance(create_resp, dict):
        msg = f"Failed to create {kind} upstream"
        raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

    created_id = str(create_resp.get("id") or create_resp.get("canonical_key", ""))
    key = str(create_resp.get("canonical_key", created_id))
    version_seq = create_resp.get("version_seq", 1)
    etag = str(create_resp.get("body_sha256") or create_resp.get("etag") or "").strip().strip('"')

    attached_links = []
    if arguments.get("links"):
        attached_links = await _sync_inline_links(
            active_client,
            created_id,
            arguments["links"],
            active_token,
        )

    out: dict[str, Any] = {
        "status": "created",
        "kind": kind,
        "id": created_id,
        "key": key,
        "title": title,
        "version_seq": version_seq,
        "etag": etag,
    }
    if attached_links:
        out["links"] = attached_links
    return out


def create_docs_create_tool(client: KanbanApiClient | None = None) -> ToolSpec:
    """Construct ToolSpec for unified docs create tool."""

    async def _handler(arguments: dict[str, Any], **kwargs: object) -> dict[str, Any]:
        raw_client = kwargs.get("client") or kwargs.get("internal_client")
        active_client = client or (raw_client if hasattr(raw_client, "request") else None)
        raw_token = kwargs.get("subject_token")
        active_token = str(raw_token) if raw_token is not None else None
        return await create_handler(
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
