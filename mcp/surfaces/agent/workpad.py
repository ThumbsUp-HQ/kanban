# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Implementation of the update_workpad MCP tool (KB-AGENT-WORKPAD-01, KAN-71)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from mcp.context import get_current_mcp_context
from mcp.errors import KbMcpError, McpErrorCode
from mcp.help import build_help

if TYPE_CHECKING:
    from mcp.internal_client import KanbanApiClient

__all__ = [
    "UPDATE_WORKPAD_SCHEMA",
    "update_workpad",
]

_MAX_IDENTIFIER_LEN: Final[int] = 200
_MAX_BODY_BYTES: Final[int] = 65536

UPDATE_WORKPAD_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "identifier": {
            "type": "string",
        },
        "body_markdown": {
            "type": "string",
        },
        "revision": {
            "type": "integer",
        },
    },
    "required": ["identifier", "body_markdown"],
    "additionalProperties": False,
}

_ALLOWED_KEYS: Final[frozenset[str]] = frozenset(UPDATE_WORKPAD_SCHEMA["properties"].keys())


def _validate_update_workpad_arguments(arguments: dict[str, Any]) -> None:
    """Strictly validate update_workpad arguments against schema constraints."""
    if arguments.get("identifier") == "help":
        return

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

    if "body_markdown" not in arguments:
        msg = "Missing required parameter 'body_markdown'"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    body = arguments["body_markdown"]
    if not isinstance(body, str):
        msg = "body_markdown must be a string"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
    if len(body.encode("utf-8")) > _MAX_BODY_BYTES:
        msg = f"body_markdown exceeds maximum allowed size of {_MAX_BODY_BYTES} bytes"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)


async def update_workpad(
    arguments: dict[str, Any],
    client: KanbanApiClient | None = None,
) -> dict[str, Any]:
    """Execute update_workpad tool updating the silent per-issue agent workpad slot."""
    _validate_update_workpad_arguments(arguments)
    identifier = arguments["identifier"].strip()

    ctx = get_current_mcp_context()
    active_client = client or (ctx.client if ctx else None)
    if active_client is None:
        msg = "MCP request context or client unavailable"
        raise KbMcpError(McpErrorCode.INTERNAL, msg)

    subject_token = ctx.subject_token if ctx else None
    session_id = ctx.session_id if ctx else None

    if identifier == "help":
        return await build_help(
            "update_workpad",
            client=active_client,
            subject_token=subject_token,
            mcp_session_id=session_id,
        )

    payload: dict[str, Any] = {
        "body_markdown": arguments["body_markdown"],
    }
    if "revision" in arguments and arguments["revision"] is not None:
        payload["revision"] = arguments["revision"]

    headers: dict[str, str] = {}
    if "revision" in arguments and arguments["revision"] is not None:
        headers["If-Match"] = str(arguments["revision"])

    resp_data = await active_client.request(
        "PUT",
        f"/api/v1/issues/{identifier}/workpad",
        json_data=payload,
        headers=headers or None,
        subject_token=subject_token,
        mcp_session_id=session_id,
    )

    if not isinstance(resp_data, dict):
        msg = "Invalid response from upstream update-workpad endpoint"
        raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

    return resp_data
