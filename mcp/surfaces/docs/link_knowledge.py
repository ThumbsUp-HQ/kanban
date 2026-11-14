# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tool link_knowledge: Connect Docs/Pages/Stickies to Issues, Cycles, Modules (S11.3)."""

from __future__ import annotations

import contextlib
import uuid
from typing import TYPE_CHECKING, Any, Final

from mcp.context import current_internal_client, current_subject_token
from mcp.errors import KbMcpError, McpErrorCode
from mcp.registry import Surface, ToolSpec

if TYPE_CHECKING:
    from mcp.internal_client import KanbanApiClient

__all__ = [
    "ALLOWED_KNOWLEDGE_LINK_TYPES",
    "ALLOWED_TARGET_KINDS",
    "create_link_knowledge_tool",
    "link_knowledge_handler",
]

_TOOL_NAME: Final[str] = "link_knowledge"
_DESCRIPTION: Final[str] = (
    "Connect Docs, Pages, or Stickies to Issues, Cycles, Modules, "
    "or Projects with typed object links."
)

ALLOWED_KNOWLEDGE_LINK_TYPES: Final[frozenset[str]] = frozenset(
    {"RELATES_TO", "VERIFIED_BY_DOC", "DERIVED_FROM_STICKY"}
)
ALLOWED_TARGET_KINDS: Final[frozenset[str]] = frozenset({"issue", "cycle", "module", "project"})

_INPUT_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "source": {
            "type": "string",
            "description": "Source doc key, page path, or sticky UUID",
        },
        "target": {
            "type": "string",
            "description": "Target issue key, cycle ref, module ref, or project key",
        },
        "target_kind": {
            "type": "string",
            "enum": ["issue", "cycle", "module", "project"],
            "description": "Target entity kind",
        },
        "link_type": {
            "type": "string",
            "enum": ["RELATES_TO", "VERIFIED_BY_DOC", "DERIVED_FROM_STICKY"],
            "default": "RELATES_TO",
            "description": "Typed link relationship kind",
        },
        "action": {
            "type": "string",
            "enum": ["add", "remove"],
            "default": "add",
            "description": "Action: add or remove the link",
        },
    },
    "required": ["source", "target", "target_kind"],
    "additionalProperties": False,
}


async def _resolve_source_id(  # noqa: C901
    client: KanbanApiClient,
    source: str,
    subject_token: str | None,
) -> str:
    clean = source.strip().lstrip("/")
    try:
        uuid.UUID(clean)
    except ValueError:
        pass
    else:
        return clean

    if clean.startswith("pages/"):
        page_path = clean.removeprefix("pages/")
        try:
            resp = await client.request(
                "GET", f"/api/v1/pages/{page_path}", subject_token=subject_token
            )
            if isinstance(resp, dict) and "id" in resp:
                return str(resp["id"])
        except KbMcpError:
            pass
    if "/" in clean:
        try:
            resp = await client.request(
                "GET", f"/api/v1/pages/{clean}", subject_token=subject_token
            )
            if isinstance(resp, dict) and "id" in resp:
                return str(resp["id"])
        except KbMcpError:
            pass
    clean_doc = clean.removeprefix("docs/")
    try:
        resp = await client.request("GET", f"/api/v1/docs/{clean_doc}", subject_token=subject_token)
        if isinstance(resp, dict) and "id" in resp:
            return str(resp["id"])
    except KbMcpError:
        pass
    return clean


async def link_knowledge_handler(  # noqa: C901, PLR0912, PLR0915
    arguments: dict[str, Any],
    *,
    client: KanbanApiClient | None = None,
    subject_token: str | None = None,
) -> dict[str, Any]:
    """Execute link_knowledge tool invocation."""
    source = arguments.get("source")
    if not source or not isinstance(source, str):
        msg = "Parameter 'source' is required"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    target = arguments.get("target")
    if not target or not isinstance(target, str):
        msg = "Parameter 'target' is required"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    target_kind = arguments.get("target_kind")
    if not target_kind or target_kind not in ALLOWED_TARGET_KINDS:
        msg = f"Parameter 'target_kind' must be one of: {sorted(ALLOWED_TARGET_KINDS)}"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    link_type = arguments.get("link_type", "RELATES_TO")
    if link_type not in ALLOWED_KNOWLEDGE_LINK_TYPES:
        msg = f"Link type '{link_type}' is not allowed for knowledge links"
        raise KbMcpError(McpErrorCode.LINK_TYPE_NOT_ALLOWED, msg)

    action = arguments.get("action", "add")
    if action not in ("add", "remove"):
        msg = f"Action '{action}' is invalid. Must be 'add' or 'remove'"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    active_client = client or current_internal_client.get()
    active_token = subject_token or current_subject_token.get()

    if active_client is None:
        msg = "Internal API client is unavailable"
        raise KbMcpError(McpErrorCode.UPSTREAM_UNAVAILABLE, msg)

    # Matrix checks
    clean_source = source.strip().lstrip("/")
    if link_type == "VERIFIED_BY_DOC":
        # Sticky cannot be VERIFIED_BY_DOC
        is_uuid = False
        try:
            uuid.UUID(clean_source)
            is_uuid = True
        except ValueError:
            pass
        if is_uuid:
            sticky_check = None
            with contextlib.suppress(KbMcpError):
                sticky_check = await active_client.request(
                    "GET", f"/api/v1/stickies/{clean_source}", subject_token=active_token
                )
            if isinstance(sticky_check, dict) and "color_token" in sticky_check:
                msg = (
                    "Link type 'VERIFIED_BY_DOC' is not allowed from a sticky note "
                    f"'{clean_source}'"
                )
                raise KbMcpError(McpErrorCode.LINK_TYPE_NOT_ALLOWED, msg)

    source_id = await _resolve_source_id(active_client, clean_source, active_token)

    if action == "add":
        payload = {
            "target": str(target).strip(),
            "link_type": link_type,
        }
        await active_client.request(
            "POST",
            f"/api/v1/objects/{source_id}/links",
            json_data=payload,
            subject_token=active_token,
        )
        return {
            "status": "linked",
            "source": clean_source,
            "target": str(target).strip(),
            "link_type": link_type,
        }

    # Handle removal of edge
    links_resp = await active_client.request(
        "GET",
        f"/api/v1/objects/{source_id}/links",
        subject_token=active_token,
    )
    link_id_to_delete: str | None = None
    if isinstance(links_resp, dict):
        outbound = links_resp.get("outbound", [])
        if isinstance(outbound, list):
            for edge in outbound:
                if not isinstance(edge, dict):
                    continue
                e_type = edge.get("type") or edge.get("link_type")
                target_obj = edge.get("target", {})
                t_key = target_obj.get("key") if isinstance(target_obj, dict) else str(target_obj)
                t_id = target_obj.get("id") if isinstance(target_obj, dict) else ""
                if e_type == link_type and target in (t_key, t_id):
                    link_id_to_delete = str(edge.get("id", ""))
                    break

    if link_id_to_delete:
        await active_client.request(
            "DELETE",
            f"/api/v1/links/{link_id_to_delete}",
            subject_token=active_token,
        )

    return {
        "status": "unlinked",
        "source": clean_source,
        "target": str(target).strip(),
        "link_type": link_type,
    }


def create_link_knowledge_tool(client: KanbanApiClient | None = None) -> ToolSpec:
    """Construct ToolSpec for link_knowledge."""

    async def _handler(arguments: dict[str, Any], **kwargs: object) -> dict[str, Any]:
        raw_client = kwargs.get("client") or kwargs.get("internal_client")
        active_client = client or (raw_client if hasattr(raw_client, "request") else None)
        raw_token = kwargs.get("subject_token")
        active_token = str(raw_token) if raw_token is not None else None
        return await link_knowledge_handler(
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
