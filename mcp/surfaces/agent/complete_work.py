# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Implementation of the complete_work MCP tool (S11.2, KB-P4-06)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from pydantic import ValidationError

from kanban.security.push_protection import scan_text_for_secrets
from mcp.context import get_current_mcp_context
from mcp.errors import KbMcpError, McpErrorCode
from mcp.help import build_help
from mcp.lod import extract_issue_sequence
from mcp.surfaces.agent.proof import (
    VERIFICATION_PROOF_SCHEMA,
    VerificationProof,
    validate_proof_ticket_key,
    validate_reality_checker_report,
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
_MAX_BATCH: Final[int] = 25
_DEFAULT_SUMMARY: Final[str] = "Completed via MCP"

COMPLETE_WORK_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "identifier": {
            "type": "string",
        },
        "identifiers": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 25,
        },
        "summary": {
            "type": "string",
        },
        "summary_markdown": {
            "type": "string",
        },
        "verification_proof": VERIFICATION_PROOF_SCHEMA,
        "to_state": {
            "type": "string",
        },
        "fencing_token": {
            "type": "integer",
        },
        "lease_action": {
            "type": "string",
            "enum": ["release", "keep", "renew"],
        },
    },
    "required": [],
    "additionalProperties": False,
}


def _summary_of(arguments: dict[str, Any]) -> object:
    """Return the summary (alias of summary_markdown) or the server default."""
    for key in ("summary", "summary_markdown"):
        if arguments.get(key) is not None:
            return arguments[key]
    return _DEFAULT_SUMMARY


def _validate_complete_work_arguments(  # noqa: C901, PLR0912, PLR0915
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

    summary = _summary_of(arguments)
    if not isinstance(summary, str):
        msg = "Argument 'summary' must be a string"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    summary_bytes = len(summary.encode("utf-8"))
    if summary_bytes < 1 or summary_bytes > _MAX_SUMMARY_BYTES:
        msg = f"Argument 'summary' must be 1..{_MAX_SUMMARY_BYTES} bytes"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    findings = scan_text_for_secrets(summary)
    if findings:
        f = findings[0]
        raise KbMcpError(
            McpErrorCode.SECRET_DETECTED_IN_PAYLOAD,
            f"Secret material detected in field 'summary_markdown' at line {f.line}",
            hint="Remove sensitive credentials, tokens, or private keys before submission.",
            field="summary_markdown",
            extra={
                "rule_id": f.rule_id,
                "secret_kind": f.kind.value,
                "line": f.line,
                "fingerprint": f.fingerprint,
            },
        )

    if arguments.get("verification_proof") is not None and (
        summary.strip().startswith("# Integration Agent Reality-Based Report")
        or "## Reality Check Validation" in summary
        or "NEEDS WORK" in summary
        or "NEEDS_WORK" in summary
        or "FAILED" in summary
    ):
        try:
            validate_reality_checker_report(summary, require_ready=True)
        except ValueError as err:
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, str(err)) from err

    proof: VerificationProof | None = None
    raw_proof = arguments.get("verification_proof")
    if raw_proof is not None:
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

    if "fencing_token" in arguments and arguments["fencing_token"] is not None:
        token = arguments["fencing_token"]
        if not isinstance(token, int) or isinstance(token, bool):
            msg = "Argument 'fencing_token' must be an integer"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if "lease_action" in arguments and arguments["lease_action"] is not None:
        act = arguments["lease_action"]
        if act not in ("release", "keep", "renew"):
            msg = "Argument 'lease_action' must be one of: release, keep, renew"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    return proof


def _batch_identifiers(arguments: dict[str, Any]) -> list[str] | None:
    """Return the deduped identifier list for batch mode, or None for single mode."""
    has_one = arguments.get("identifier") is not None
    many = arguments.get("identifiers")
    if many is None:
        return None
    if has_one:
        raise KbMcpError(
            McpErrorCode.VALIDATION_FAILED,
            "Provide either 'identifier' or 'identifiers', not both",
            fix_hint="Pass a single 'identifier' or a list in 'identifiers'.",
        )
    if not isinstance(many, list) or not many:
        raise KbMcpError(
            McpErrorCode.VALIDATION_FAILED,
            "Argument 'identifiers' must be a non-empty list of strings",
            fix_hint="Pass 'identifiers': ['KEY-1', 'KEY-2'].",
        )
    out: list[str] = []
    for item in many:
        if not isinstance(item, str) or not item.strip():
            msg = "Each entry of 'identifiers' must be a non-empty string"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
        if len(item.strip()) > _MAX_IDENTIFIER_LEN:
            msg = f"Identifier exceeds maximum length of {_MAX_IDENTIFIER_LEN}"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
        if item.strip() not in out:
            out.append(item.strip())
    if len(out) > _MAX_BATCH:
        msg = f"'identifiers' accepts at most {_MAX_BATCH} entries"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
    return out


async def complete_work(
    arguments: dict[str, Any],
    *,
    client: KanbanApiClient | None = None,
) -> dict[str, Any]:
    """Complete one ticket (identifier) or a batch (identifiers) via the server gate."""
    ids = _batch_identifiers(arguments)
    if ids is None:
        if arguments.get("identifier") is None:
            raise KbMcpError(
                McpErrorCode.VALIDATION_FAILED,
                "Missing required argument 'identifier' or 'identifiers'",
                fix_hint="Pass 'identifier': 'KEY-1' or 'identifiers': ['KEY-1', 'KEY-2'].",
            )
        return await _complete_single(arguments, client=client)
    results: list[dict[str, Any]] = []
    for ident in ids:
        sub_args = {k: v for k, v in arguments.items() if k not in ("identifiers", "fencing_token")}
        sub_args["identifier"] = ident
        try:
            res = await _complete_single(sub_args, client=client)
            entry: dict[str, Any] = {"identifier": ident, "status": res.get("status", "completed")}
            for k in ("state", "to_state", "gate_comment"):
                if k in res:
                    entry[k if k != "to_state" else "state"] = res[k]
            results.append(entry)
        except KbMcpError as exc:
            results.append(
                {
                    "identifier": ident,
                    "status": "failed",
                    "error": {
                        "code": str(getattr(exc.code, "value", exc.code)),
                        "message": exc.message,
                        "fix_hint": exc.fix_hint or exc.hint or "",
                    },
                }
            )
        except Exception as exc:  # noqa: BLE001 - one failure must never abort the batch
            results.append(
                {
                    "identifier": ident,
                    "status": "failed",
                    "error": {"code": "INTERNAL", "message": type(exc).__name__, "fix_hint": ""},
                }
            )
    failed = sum(1 for r in results if r["status"] == "failed")
    return {
        "status": "batch",
        "completed": len(results) - failed,
        "failed": failed,
        "results": results,
    }


async def _complete_single(  # noqa: C901
    arguments: dict[str, Any],
    *,
    client: KanbanApiClient | None = None,
) -> dict[str, Any]:
    """Execute complete_work workflow for one ticket."""
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

    payload: dict[str, Any] = {"summary_markdown": str(_summary_of(arguments))}
    if arguments.get("verification_proof") is not None:
        payload["verification_proof"] = arguments["verification_proof"]
    if arguments.get("to_state"):
        payload["to_state"] = arguments["to_state"].strip()
    if arguments.get("fencing_token") is not None:
        payload["fencing_token"] = arguments["fencing_token"]
    if arguments.get("lease_action") is not None:
        payload["lease_action"] = arguments["lease_action"]

    resp_data = await active_client.request(
        "POST",
        f"/api/v1/issues/{identifier}/complete-work",
        json_data=payload,
        params={"wait": "true"},
        subject_token=subject_token,
        mcp_session_id=session_id,
    )

    if not isinstance(resp_data, dict):
        msg = "Invalid response from upstream complete-work endpoint"
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

    proof_summary: dict[str, Any] = {}
    if proof_obj is not None:
        proof_summary = {
            "qa_dir": proof_obj.qa_dir,
            "artifacts": len(proof_obj.artifacts),
            "verdict": proof_obj.reality_checker.verdict,
        }

    result: dict[str, Any] = {
        "status": "completed",
        "key": key,
        "issue_key": key,
        "sequence_number": seq_num,
        "state": resp_data.get("target_state") or state_str or "Done",
    }
    if proof_summary:
        result["proof"] = proof_summary
    if resp_data.get("comment_ref"):
        result["comment"] = str(resp_data["comment_ref"])

    return result
