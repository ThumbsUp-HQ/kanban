# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Implementation of the transition_ticket MCP tool (S11.2, KB-P4-06)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from pydantic import ValidationError

from mcp.context import get_current_mcp_context
from mcp.errors import KbMcpError, McpErrorCode
from mcp.help import build_help
from mcp.lod import extract_issue_sequence
from mcp.surfaces.agent.proof import (
    VERIFICATION_PROOF_SCHEMA,
    VerificationProof,
    validate_proof_ticket_key,
)

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
        },
        "to_state": {
            "type": "string",
        },
        "comment_markdown": {
            "type": "string",
        },
        "verification_proof": VERIFICATION_PROOF_SCHEMA,
        "fencing_token": {
            "type": "integer",
        },
        "lease_action": {
            "type": "string",
            "enum": ["renew", "release", "keep"],
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

    if "fencing_token" in arguments and arguments["fencing_token"] is not None:
        token = arguments["fencing_token"]
        if not isinstance(token, int) or isinstance(token, bool):
            msg = "Argument 'fencing_token' must be an integer"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if "lease_action" in arguments and arguments["lease_action"] is not None:
        act = arguments["lease_action"]
        if act not in ("renew", "release", "keep"):
            msg = "Argument 'lease_action' must be one of: renew, release, keep"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)


def _is_use_complete_work(exc: KbMcpError) -> bool:
    """Return True when upstream rejected a completed-group transition with USE_COMPLETE_WORK."""
    return "USE_COMPLETE_WORK" in {
        str(getattr(exc.code, "value", exc.code)),
        str((exc.extra or {}).get("code", "")),
    }


async def _route_to_complete_work(
    arguments: dict[str, Any], identifier: str, client: KanbanApiClient
) -> dict[str, Any]:
    """Route a completed-group transition through the complete_work server gate."""
    from mcp.surfaces.agent.complete_work import complete_work  # noqa: PLC0415

    cw: dict[str, Any] = {"identifier": identifier, "to_state": arguments["to_state"].strip()}
    if arguments.get("comment_markdown"):
        cw["summary"] = arguments["comment_markdown"]
    for k in ("verification_proof", "fencing_token", "lease_action"):
        if arguments.get(k) is not None:
            cw[k] = arguments[k]
    res = await complete_work(cw, client=client)
    if res.get("status") == "completed":
        res = {**res, "status": "transitioned"}
    return res


async def transition_ticket(  # noqa: C901
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
    if arguments.get("fencing_token") is not None:
        payload["fencing_token"] = arguments["fencing_token"]
    if arguments.get("lease_action") is not None:
        payload["lease_action"] = arguments["lease_action"]

    try:
        resp_data = await active_client.request(
            "POST",
            f"/api/v1/issues/{identifier}/transition",
            json_data=payload,
            params={"wait": "true", "wait_timeout_ms": 75000},
            timeout_s=85.0,
            subject_token=subject_token,
            mcp_session_id=session_id,
        )
    except KbMcpError as exc:
        if _is_use_complete_work(exc):
            return await _route_to_complete_work(arguments, identifier, active_client)
        if exc.code == McpErrorCode.INVALID_TRANSITION and exc.valid_options:
            first_state = exc.valid_options[0]
            opts_str = ", ".join(str(s) for s in exc.valid_options)
            raise KbMcpError(
                McpErrorCode.INVALID_TRANSITION,
                exc.message,
                hint=exc.hint,
                field="to_state",
                valid_options=exc.valid_options,
                did_you_mean=exc.did_you_mean,
                fix_hint=exc.fix_hint or f"Allowed target states: {opts_str}",
                cli_example=(
                    f'kanban-cli-agent transition_ticket --identifier="{identifier}" '
                    f'--to-state="{first_state}"'
                ),
                extra=exc.extra,
            ) from None
        raise

    if not isinstance(resp_data, dict):
        msg = "Invalid response from upstream transition endpoint"
        raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

    key = str(resp_data.get("key", identifier))
    seq_num = extract_issue_sequence(resp_data, key)

    # KAN-537/538 seam: server waited for the gate verdict (wait=true)
    gate_result = resp_data.get("gate")
    if isinstance(gate_result, dict) and gate_result.get("error_code") != "GATE_TIMEOUT":
        return {
            "key": key,
            "issue_key": key,
            "sequence_number": seq_num,
            "execution_id": str(gate_result.get("execution_id", "")),
            "passed": bool(gate_result.get("passed")),
            "status": str(gate_result.get("status", "")),
            "verdict": gate_result.get("verdict"),
            "comment": str(gate_result.get("comment", "")),
            "findings": list(gate_result.get("findings") or []),
            **({"grade": gate_result["grade"]} if gate_result.get("grade") else {}),
        }

    # Check for 202 Accepted pending_agent_gate hold
    if "execution_id" in resp_data and "active_agent" in resp_data:
        from_val = resp_data.get("from_state")
        from_str = from_val.get("name", "") if isinstance(from_val, dict) else str(from_val or "")
        to_val = resp_data.get("to_state")
        to_str = to_val.get("name", "") if isinstance(to_val, dict) else str(to_val or "")
        return {
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

    state_val = resp_data.get("state")
    state_str = (
        str(state_val.get("name", "")) if isinstance(state_val, dict) else str(state_val or "")
    )
    from_val = resp_data.get("from_state")
    from_state = (
        str(from_val.get("name", "")) if isinstance(from_val, dict) else str(from_val or "")
    )

    return {
        "status": "transitioned",
        "key": key,
        "issue_key": key,
        "sequence_number": seq_num,
        "from_state": from_state or "In Progress",
        "to_state": resp_data.get("target_state") or state_str or to_state,
    }
