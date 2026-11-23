# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Implementation of the begin_work MCP tool (S11.2, KB-P4-06)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from mcp.context import get_current_mcp_context
from mcp.errors import KbMcpError, McpErrorCode
from mcp.help import build_help
from mcp.lod import extract_issue_sequence
from mcp.surfaces.agent.read_ticket import _format_assignees

if TYPE_CHECKING:
    from mcp.internal_client import KanbanApiClient

__all__ = [
    "BEGIN_WORK_SCHEMA",
    "begin_work",
]

_MAX_IDENTIFIER_LEN: Final[int] = 200
_MAX_PLAN_BYTES: Final[int] = 65536
_MIN_TTL_SECONDS: Final[int] = 60
_MAX_TTL_SECONDS: Final[int] = 7200

BEGIN_WORK_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "identifier": {
            "type": "string",
        },
        "plan_markdown": {
            "type": "string",
        },
        "ttl_seconds": {
            "type": "integer",
            "minimum": 60,
            "maximum": 7200,
        },
        "fencing_token": {
            "type": "integer",
        },
        "lease_action": {
            "type": "string",
            "enum": ["acquire", "renew"],
        },
        "use_workpad": {
            "type": "boolean",
            "default": True,
        },
    },
    "required": ["identifier", "plan_markdown"],
    "additionalProperties": False,
}


def _validate_begin_work_arguments(arguments: dict[str, Any]) -> None:  # noqa: C901, PLR0912
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

    if "ttl_seconds" in arguments and arguments["ttl_seconds"] is not None:
        ttl = arguments["ttl_seconds"]
        if (
            not isinstance(ttl, int)
            or isinstance(ttl, bool)
            or ttl < _MIN_TTL_SECONDS
            or ttl > _MAX_TTL_SECONDS
        ):
            msg = (
                f"Argument 'ttl_seconds' must be between {_MIN_TTL_SECONDS} and {_MAX_TTL_SECONDS}"
            )
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if "fencing_token" in arguments and arguments["fencing_token"] is not None:
        ft = arguments["fencing_token"]
        if not isinstance(ft, int) or isinstance(ft, bool):
            msg = "Argument 'fencing_token' must be an integer"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if "lease_action" in arguments and arguments["lease_action"] is not None:
        la = arguments["lease_action"]
        if la not in ("acquire", "renew"):
            msg = "Argument 'lease_action' must be 'acquire' or 'renew'"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)


async def begin_work(  # noqa: C901, PLR0912, PLR0915
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
    payload: dict[str, Any] = {"plan_markdown": plan_markdown}
    if arguments.get("ttl_seconds") is not None:
        payload["ttl_seconds"] = arguments["ttl_seconds"]
    if arguments.get("fencing_token") is not None:
        payload["fencing_token"] = arguments["fencing_token"]
    if arguments.get("lease_action") is not None:
        payload["lease_action"] = arguments["lease_action"]
    if arguments.get("use_workpad") is not None:
        payload["use_workpad"] = arguments["use_workpad"]
    else:
        payload["use_workpad"] = True

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

    key = str(resp_data.get("key", identifier))
    seq_num = extract_issue_sequence(resp_data, key)

    # Check for 202 Accepted pending_agent_gate hold
    if "execution_id" in resp_data and "active_agent" in resp_data:
        from_val = resp_data.get("from_state")
        from_str = from_val.get("name", "") if isinstance(from_val, dict) else str(from_val or "")
        to_val = resp_data.get("to_state")
        to_str = to_val.get("name", "") if isinstance(to_val, dict) else str(to_val or "")
        pending_res: dict[str, Any] = {
            "status": "pending_agent_gate",
            "key": key,
            "issue_key": key,
            "sequence_number": seq_num,
            "from_state": from_str,
            "to_state": to_str,
            "execution_id": str(resp_data.get("execution_id", "")),
            "active_agent": str(resp_data.get("active_agent", "")),
            "hint": "transition is held; poll read_ticket for the gate verdict",
        }
        if resp_data.get("lease_id"):
            pending_res["lease_id"] = str(resp_data["lease_id"])
        if resp_data.get("fencing_token") is not None:
            pending_res["fencing_token"] = resp_data["fencing_token"]
        if resp_data.get("lease_expires_at"):
            pending_res["lease_expires_at"] = str(resp_data["lease_expires_at"])
        return pending_res

    state_val = resp_data.get("state")
    state_str = (
        str(state_val.get("name", "")) if isinstance(state_val, dict) else str(state_val or "")
    )

    assignees = _format_assignees(resp_data.get("assignees", []))

    result: dict[str, Any] = {
        "status": "started",
        "key": key,
        "issue_key": key,
        "sequence_number": seq_num,
        "state": state_str,
        "assignees": assignees,
    }

    if resp_data.get("lease_id"):
        result["lease_id"] = str(resp_data["lease_id"])
    if resp_data.get("fencing_token") is not None:
        result["fencing_token"] = resp_data["fencing_token"]
    if resp_data.get("lease_expires_at"):
        result["lease_expires_at"] = str(resp_data["lease_expires_at"])

    cycle_val = resp_data.get("cycle")
    if isinstance(cycle_val, dict) and cycle_val.get("name"):
        result["cycle"] = str(cycle_val["name"])
    elif isinstance(cycle_val, str) and cycle_val:
        result["cycle"] = cycle_val

    if resp_data.get("comment_ref"):
        result["comment"] = str(resp_data["comment_ref"])

    return result
