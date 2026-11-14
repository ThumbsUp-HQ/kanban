# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Implementation of the transition_ticket MCP tool (S11.2, KB-P4-06)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from pydantic import ValidationError

from mcp.context import get_current_mcp_context
from mcp.errors import KbMcpError, McpErrorCode
from mcp.help import build_help
from mcp.surfaces.agent.proof import VerificationProof, validate_proof_ticket_key

if TYPE_CHECKING:
    from mcp.internal_client import KanbanApiClient

__all__ = [
    "TRANSITION_TICKET_SCHEMA",
    "transition_ticket",
]

_MAX_IDENTIFIER_LEN: Final[int] = 200
_MAX_STATE_LEN: Final[int] = 100
_MAX_COMMENT_BYTES: Final[int] = 65536

TRANSITION_TICKET_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "identifier": {
            "type": "string",
            "description": "Issue key (e.g. 'KAN-142'), UUID, or 'help'",
        },
        "to_state": {
            "type": "string",
            "description": "Target workflow state name or UUID (cannot be a completed state)",
        },
        "comment_markdown": {
            "type": "string",
            "description": "Optional comment markdown (<= 65536 bytes)",
        },
        "verification_proof": {
            "type": "object",
            "description": "Optional structured VerificationProof packet",
        },
    },
    "required": ["identifier", "to_state"],
    "additionalProperties": False,
}


def _validate_transition_arguments(arguments: dict[str, Any]) -> None:  # noqa: C901, PLR0912
    """Validate transition_ticket arguments against schema constraints."""
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

    if "to_state" not in arguments:
        msg = "Missing required argument 'to_state'"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    to_state = arguments["to_state"]
    if not isinstance(to_state, str) or not to_state.strip():
        msg = "Argument 'to_state' must be a non-empty string"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if len(to_state.strip()) > _MAX_STATE_LEN:
        msg = f"Argument 'to_state' exceeds maximum length of {_MAX_STATE_LEN}"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if "comment_markdown" in arguments and arguments["comment_markdown"] is not None:
        c = arguments["comment_markdown"]
        if not isinstance(c, str):
            msg = "Argument 'comment_markdown' must be a string"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
        if len(c.encode("utf-8")) > _MAX_COMMENT_BYTES:
            msg = f"Argument 'comment_markdown' exceeds {_MAX_COMMENT_BYTES} bytes"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if "verification_proof" in arguments and arguments["verification_proof"] is not None:
        raw_proof = arguments["verification_proof"]
        if not isinstance(raw_proof, dict):
            msg = "Argument 'verification_proof' must be a dictionary"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
        try:
            proof = VerificationProof.model_validate(raw_proof)
            validate_proof_ticket_key(proof, identifier.strip())
        except (ValidationError, ValueError) as err:
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, str(err)) from err


async def transition_ticket(
    arguments: dict[str, Any],
    *,
    client: KanbanApiClient | None = None,
) -> dict[str, Any]:
    """Execute intermediate state transition on an issue."""
    _validate_transition_arguments(arguments)
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
            "transition_ticket",
            client=active_client,
            subject_token=subject_token,
            mcp_session_id=session_id,
        )

    to_state = arguments["to_state"].strip()
    payload: dict[str, Any] = {"to_state": to_state}
    if arguments.get("comment_markdown") is not None:
        payload["comment_markdown"] = arguments["comment_markdown"]
    if arguments.get("verification_proof") is not None:
        payload["verification_proof"] = arguments["verification_proof"]

    resp_data = await active_client.request(
        "POST",
        f"/api/v1/issues/{identifier}/transition",
        json_data=payload,
        subject_token=subject_token,
        mcp_session_id=session_id,
    )

    if not isinstance(resp_data, dict):
        msg = "Invalid response from upstream transition endpoint"
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
    from_state = str(resp_data.get("from_state", ""))

    return {
        "status": "transitioned",
        "key": key,
        "from_state": from_state or "In Progress",
        "to_state": resp_data.get("target_state") or state_str or to_state,
    }
