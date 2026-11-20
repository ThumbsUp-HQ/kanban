# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Implementation of the complete_work MCP tool (S11.2, KB-P4-06)."""

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
    "COMPLETE_WORK_SCHEMA",
    "complete_work",
]

_MAX_IDENTIFIER_LEN: Final[int] = 200
_MAX_SUMMARY_BYTES: Final[int] = 65536
_MAX_STATE_LEN: Final[int] = 100

COMPLETE_WORK_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "identifier": {
            "type": "string",
            "description": "Issue ref",
        },
        "summary_markdown": {
            "type": "string",
            "description": "Summary",
        },
        "verification_proof": VERIFICATION_PROOF_SCHEMA,
        "to_state": {
            "type": "string",
            "description": "Target state",
        },
    },
    "required": ["identifier", "summary_markdown", "verification_proof"],
    "additionalProperties": False,
}


def _validate_complete_work_arguments(  # noqa: C901, PLR0912
    arguments: dict[str, Any],
) -> VerificationProof | None:
    """Validate complete_work arguments against schema constraints and return parsed proof."""
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
        return None

    if "summary_markdown" not in arguments:
        msg = "Missing required argument 'summary_markdown'"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    summary = arguments["summary_markdown"]
    if not isinstance(summary, str):
        msg = "Argument 'summary_markdown' must be a string"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    summary_bytes = len(summary.encode("utf-8"))
    if summary_bytes < 1 or summary_bytes > _MAX_SUMMARY_BYTES:
        msg = f"Argument 'summary_markdown' must be 1..{_MAX_SUMMARY_BYTES} bytes"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if "verification_proof" not in arguments:
        msg = "Missing required argument 'verification_proof'"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    raw_proof = arguments["verification_proof"]
    if not isinstance(raw_proof, dict):
        msg = "Argument 'verification_proof' must be a dictionary"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    try:
        proof = VerificationProof.model_validate(raw_proof)
        validate_proof_ticket_key(proof, identifier.strip())
    except (ValidationError, ValueError) as err:
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, str(err)) from err

    if "to_state" in arguments and arguments["to_state"] is not None:
        ts = arguments["to_state"]
        if not isinstance(ts, str) or not ts.strip():
            msg = "Argument 'to_state' must be a non-empty string"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
        if len(ts.strip()) > _MAX_STATE_LEN:
            msg = f"Argument 'to_state' exceeds maximum length of {_MAX_STATE_LEN}"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    return proof


async def complete_work(
    arguments: dict[str, Any],
    *,
    client: KanbanApiClient | None = None,
) -> dict[str, Any]:
    """Execute complete_work workflow: audit blockers, check QA gate, and close ticket."""
    proof_obj = _validate_complete_work_arguments(arguments)
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
            "complete_work",
            client=active_client,
            subject_token=subject_token,
            mcp_session_id=session_id,
        )

    summary_markdown = arguments["summary_markdown"]
    payload: dict[str, Any] = {
        "summary_markdown": summary_markdown,
        "verification_proof": arguments["verification_proof"],
    }
    if arguments.get("to_state"):
        payload["to_state"] = arguments["to_state"].strip()

    resp_data = await active_client.request(
        "POST",
        f"/api/v1/issues/{identifier}/complete-work",
        json_data=payload,
        subject_token=subject_token,
        mcp_session_id=session_id,
    )

    if not isinstance(resp_data, dict):
        msg = "Invalid response from upstream complete-work endpoint"
        raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

    key = str(resp_data.get("key", identifier))
    seq_num = extract_issue_sequence(resp_data, key)

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

    proof_summary: dict[str, Any] = {
        "qa_dir": proof_obj.qa_dir if proof_obj else arguments["verification_proof"].get("qa_dir"),
        "artifacts": len(proof_obj.artifacts)
        if proof_obj
        else len(arguments["verification_proof"].get("artifacts", [])),
        "verdict": proof_obj.reality_checker.verdict
        if proof_obj
        else arguments["verification_proof"].get("reality_checker", {}).get("verdict"),
    }

    result: dict[str, Any] = {
        "status": "completed",
        "key": key,
        "issue_key": key,
        "sequence_number": seq_num,
        "state": resp_data.get("target_state") or state_str or "Done",
        "proof": proof_summary,
    }
    if resp_data.get("comment_ref"):
        result["comment"] = str(resp_data["comment_ref"])

    return result
