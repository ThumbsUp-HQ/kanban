# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Implementation of the begin_work MCP tool (S11.2, KB-P4-06)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from mcp.context import get_current_mcp_context
from mcp.errors import KbMcpError, McpErrorCode
from mcp.help import build_help
from mcp.surfaces.agent.read_ticket import _format_assignees

if TYPE_CHECKING:
    from mcp.internal_client import KanbanApiClient

__all__ = [
    "BEGIN_WORK_SCHEMA",
    "begin_work",
]

_MAX_IDENTIFIER_LEN: Final[int] = 200
_MAX_PLAN_BYTES: Final[int] = 65536

BEGIN_WORK_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "identifier": {
            "type": "string",
            "description": "Issue ref",
        },
        "plan_markdown": {
            "type": "string",
            "description": "Plan markdown",
        },
    },
    "required": ["identifier", "plan_markdown"],
    "additionalProperties": False,
}


def _validate_begin_work_arguments(arguments: dict[str, Any]) -> None:
    """Validate begin_work arguments against schema constraints."""
    if "identifier" not in arguments:
        msg = "Missing required argument 'identifier'"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    identifier = arguments["identifier"]
    if not isinstance(identifier, str) or not identifier.strip():
        msg = "Argument 'identifier' must be a non-empty string"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if len(identifier.strip()) > _MAX_IDENTIFIER_LEN:
        msg = f"Argument 'identifier' exceeds maximum length of {_MAX_IDENTIFIER_LEN}"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if identifier.strip() == "help":
        return

    if "plan_markdown" not in arguments:
        msg = "Missing required argument 'plan_markdown'"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    plan = arguments["plan_markdown"]
    if not isinstance(plan, str):
        msg = "Argument 'plan_markdown' must be a string"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    plan_bytes = len(plan.encode("utf-8"))
    if plan_bytes < 1 or plan_bytes > _MAX_PLAN_BYTES:
        msg = f"Argument 'plan_markdown' must be 1..{_MAX_PLAN_BYTES} bytes"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)


async def begin_work(
    arguments: dict[str, Any],
    *,
    client: KanbanApiClient | None = None,
) -> dict[str, Any]:
    """Execute begin_work workflow: assign caller, move state, attach cycle, post plan."""
    _validate_begin_work_arguments(arguments)
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
            "begin_work",
            client=active_client,
            subject_token=subject_token,
            mcp_session_id=session_id,
        )

    plan_markdown = arguments["plan_markdown"]
    payload = {"plan_markdown": plan_markdown}

    resp_data = await active_client.request(
        "POST",
        f"/api/v1/issues/{identifier}/begin-work",
        json_data=payload,
        subject_token=subject_token,
        mcp_session_id=session_id,
    )

    if not isinstance(resp_data, dict):
        msg = "Invalid response from upstream begin-work endpoint"
        raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

    # Check for 202 Accepted pending_agent_gate hold
    if "execution_id" in resp_data and "active_agent" in resp_data:
        return {
            "status": "pending_agent_gate",
            "key": str(resp_data.get("key", identifier)),
            "from_state": str(resp_data.get("from_state", "")),
            "to_state": str(resp_data.get("to_state", "")),
            "execution_id": str(resp_data.get("execution_id", "")),
            "active_agent": str(resp_data.get("active_agent", "")),
            "hint": "transition is held; poll read_ticket for the gate verdict",
        }

    key = str(resp_data.get("key", identifier))
    state_val = resp_data.get("state")
    state_str = (
        str(state_val.get("name", "")) if isinstance(state_val, dict) else str(state_val or "")
    )

    assignees = _format_assignees(resp_data.get("assignees", []))

    result: dict[str, Any] = {
        "status": "started",
        "key": key,
        "state": state_str,
        "assignees": assignees,
    }

    cycle_val = resp_data.get("cycle")
    if isinstance(cycle_val, dict) and cycle_val.get("name"):
        result["cycle"] = str(cycle_val["name"])
    elif isinstance(cycle_val, str) and cycle_val:
        result["cycle"] = cycle_val

    if resp_data.get("comment_ref"):
        result["comment"] = str(resp_data["comment_ref"])

    return result
