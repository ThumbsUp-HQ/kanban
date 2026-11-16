# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Implementation of the link_objects MCP tool (S11.2, S12.1, KB-P4-07)."""

from __future__ import annotations

from typing import Any, Final

from mcp.context import get_current_mcp_context
from mcp.errors import KbMcpError, McpErrorCode
from mcp.help import build_help
from mcp.resolver import EntityResolver

__all__ = [
    "ALLOWED_LINK_TYPES",
    "LINK_OBJECTS_SCHEMA",
    "link_objects",
]

_MAX_REF_LEN: Final[int] = 200

ALLOWED_LINK_TYPES: Final[frozenset[str]] = frozenset(
    {"BLOCKS", "BLOCKED_BY", "RELATES_TO", "DUPLICATES", "DUPLICATED_BY", "VERIFIED_BY_DOC"}
)

LINK_OBJECTS_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "source": {
            "type": "string",
            "description": "Source ref",
        },
        "target": {
            "type": "string",
            "description": "Target ref",
        },
        "link_type": {
            "type": "string",
            "description": "Link kind",
        },
        "action": {
            "type": "string",
            "enum": ["add", "remove"],
            "default": "add",
            "description": "add or remove",
        },
    },
    "required": ["source", "target", "link_type"],
    "additionalProperties": False,
}

_ALLOWED_KEYS: Final[frozenset[str]] = frozenset(LINK_OBJECTS_SCHEMA["properties"].keys())


def _validate_link_objects_arguments(arguments: dict[str, Any]) -> None:  # noqa: C901, PLR0912
    """Strictly validate link_objects arguments against schema constraints."""
    if arguments.get("source") == "help" or arguments.get("action") == "help":
        return

    for key in arguments:
        if key not in _ALLOWED_KEYS:
            msg = f"Unknown parameter '{key}'"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if "source" not in arguments:
        msg = "source is required"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    source = arguments["source"]
    if not isinstance(source, str) or not source.strip():
        msg = "source must be a non-empty string"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
    if len(source) > _MAX_REF_LEN:
        msg = f"source length ({len(source)}) exceeds maximum of {_MAX_REF_LEN}"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if "target" not in arguments:
        msg = "target is required"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    target = arguments["target"]
    if not isinstance(target, str) or not target.strip():
        msg = "target must be a non-empty string"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
    if len(target) > _MAX_REF_LEN:
        msg = f"target length ({len(target)}) exceeds maximum of {_MAX_REF_LEN}"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if source.strip().lower() == target.strip().lower():
        msg = "Self-linking is not allowed"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if "link_type" not in arguments:
        msg = "link_type is required"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    link_type = str(arguments["link_type"]).strip().upper()
    if link_type not in ALLOWED_LINK_TYPES:
        msg = f"Unsupported link_type: {arguments['link_type']}"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    action = arguments.get("action", "add")
    if action not in ("add", "remove"):
        msg = f"Unsupported action: {action}"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)


async def _resolve_key(resolver: EntityResolver, ref: str) -> tuple[str, str]:
    """Resolve reference to (id_or_ref, canonical_key)."""
    for kind in ("issue", "doc"):
        try:
            resolved = await resolver.resolve(kind, ref)
        except KbMcpError:
            continue
        else:
            return (resolved.id, resolved.key)
    return (ref, ref)


async def link_objects(arguments: dict[str, Any]) -> dict[str, Any]:  # noqa: C901, PLR0912, PLR0915
    """Execute link_objects MCP tool to create or delete typed links."""
    ctx = get_current_mcp_context()
    if ctx is None or ctx.client is None:
        msg = "MCP request context or API client is unavailable"
        raise KbMcpError(McpErrorCode.INTERNAL, msg)

    # JIT help progressive disclosure
    if (
        arguments.get("identifier") == "help"
        or arguments.get("action") == "help"
        or arguments.get("source") == "help"
    ):
        return await build_help(
            "link_objects",
            client=ctx.client,
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )

    _validate_link_objects_arguments(arguments)

    source = str(arguments["source"]).strip()
    target = str(arguments["target"]).strip()
    link_type = str(arguments["link_type"]).strip()
    action = str(arguments.get("action", "add")).strip()

    resolver = EntityResolver(
        ctx.client,
        subject_token=ctx.subject_token,
        mcp_session_id=ctx.session_id,
    )

    source_id, source_key = await _resolve_key(resolver, source)
    target_id, target_key = await _resolve_key(resolver, target)

    if source_id == target_id or source_key.lower() == target_key.lower():
        msg = "An object cannot be linked to itself"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if action == "add":
        payload = {
            "target": target_id,
            "link_type": link_type.upper(),
        }
        res = await ctx.client.request(
            "POST",
            f"/api/v1/objects/{source_id}/links",
            json_data=payload,
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
            headers={"X-KB-MCP-Tool": "link_objects"},
        )

        if isinstance(res, dict) and "target" in res and isinstance(res["target"], dict):
            resolved_target_key = res["target"].get("key") or target_key
        else:
            resolved_target_key = target_key

        return {
            "status": "linked",
            "link": {
                "source": source_key,
                "link_type": link_type,
                "type": link_type,
                "target": resolved_target_key,
            },
        }

    # Handle link removal
    links_res = await ctx.client.request(
        "GET",
        f"/api/v1/objects/{source_id}/links",
        subject_token=ctx.subject_token,
        mcp_session_id=ctx.session_id,
    )

    if not isinstance(links_res, dict):
        msg = f"Failed to retrieve links for object '{source}'"
        raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

    outbound = links_res.get("outbound", [])
    target_link_id: str | None = None

    if isinstance(outbound, list):
        for link in outbound:
            if not isinstance(link, dict):
                continue
            if str(link.get("link_type", "")).upper() != link_type.upper():
                continue
            t_obj = link.get("target")
            if isinstance(t_obj, dict):
                t_id = str(t_obj.get("id", ""))
                t_key = str(t_obj.get("key", ""))
                if t_id in (target_id, target) or t_key.lower() in (
                    target_key.lower(),
                    target.lower(),
                ):
                    target_link_id = str(link.get("id"))
                    break

    if target_link_id is None:
        inbound = links_res.get("inbound", [])
        if isinstance(inbound, list):
            for link in inbound:
                if not isinstance(link, dict):
                    continue
                if str(link.get("link_type", "")).upper() != link_type.upper():
                    continue
                s_obj = link.get("source")
                if isinstance(s_obj, dict):
                    s_id = str(s_obj.get("id", ""))
                    s_key = str(s_obj.get("key", ""))
                    if s_id in (target_id, target) or s_key.lower() in (
                        target_key.lower(),
                        target.lower(),
                    ):
                        target_link_id = str(link.get("id"))
                        break

    if target_link_id is None:
        msg = f"No link of type '{link_type}' found between '{source_key}' and '{target_key}'"
        raise KbMcpError(McpErrorCode.NOT_FOUND, msg)

    await ctx.client.request(
        "DELETE",
        f"/api/v1/links/{target_link_id}",
        subject_token=ctx.subject_token,
        mcp_session_id=ctx.session_id,
        headers={"X-KB-MCP-Tool": "link_objects"},
    )

    return {
        "status": "unlinked",
        "link": {
            "source": source_key,
            "link_type": link_type,
            "type": link_type,
            "target": target_key,
        },
    }
