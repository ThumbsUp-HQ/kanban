# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Implementation of the add_comment MCP tool (S11.2, KB-P4-07)."""

from __future__ import annotations

from typing import Any, Final

from kanban.security.push_protection import scan_text_for_secrets
from mcp.context import get_current_mcp_context
from mcp.errors import KbMcpError, McpErrorCode
from mcp.help import build_help

__all__ = [
    "ADD_COMMENT_SCHEMA",
    "add_comment",
]

_MAX_IDENTIFIER_LEN: Final[int] = 200
_MAX_BODY_BYTES: Final[int] = 65536

ADD_COMMENT_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "identifier": {
            "type": "string",
            "description": "Issue ref",
        },
        "body_markdown": {
            "type": "string",
            "description": "Body markdown",
        },
        "reply_to": {
            "type": "string",
            "description": "Reply to ID",
        },
        "ack_mentions": {
            "type": "boolean",
            "default": False,
            "description": "Ack mentions",
        },
    },
    "required": ["identifier", "body_markdown"],
    "additionalProperties": False,
}

_ALLOWED_KEYS: Final[frozenset[str]] = frozenset(ADD_COMMENT_SCHEMA["properties"].keys())


def _validate_add_comment_arguments(arguments: dict[str, Any]) -> None:  # noqa: C901
    """Strictly validate add_comment arguments against schema constraints."""
    if arguments.get("identifier") == "help" or arguments.get("action") == "help":
        return

    for key in arguments:
        if key not in _ALLOWED_KEYS:
            msg = f"Unknown parameter '{key}'"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if "identifier" not in arguments:
        msg = "identifier is required"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    identifier = arguments["identifier"]
    if not isinstance(identifier, str) or not identifier.strip():
        msg = "identifier must be a non-empty string"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
    if len(identifier) > _MAX_IDENTIFIER_LEN:
        msg = f"identifier length ({len(identifier)}) exceeds maximum of {_MAX_IDENTIFIER_LEN}"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if "body_markdown" not in arguments:
        msg = "body_markdown is required"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    body = arguments["body_markdown"]
    if not isinstance(body, str) or not body.strip():
        msg = "body_markdown cannot be empty"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    body_bytes = len(body.encode("utf-8"))
    if body_bytes > _MAX_BODY_BYTES:
        msg = (
            f"body_markdown length ({body_bytes} bytes) exceeds maximum of {_MAX_BODY_BYTES} bytes"
        )
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    findings = scan_text_for_secrets(body)
    if findings:
        f = findings[0]
        raise KbMcpError(
            McpErrorCode.SECRET_DETECTED_IN_PAYLOAD,
            f"Secret material detected in field 'body_markdown' at line {f.line}",
            hint="Remove sensitive credentials, tokens, or private keys before submission.",
            field="body_markdown",
            extra={
                "rule_id": f.rule_id,
                "secret_kind": f.kind.value,
                "line": f.line,
                "fingerprint": f.fingerprint,
            },
        )

    reply_to = arguments.get("reply_to")
    if reply_to is not None and (not isinstance(reply_to, str) or not reply_to.strip()):
        msg = "reply_to must be a non-empty string"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    ack_mentions = arguments.get("ack_mentions")
    if ack_mentions is not None and not isinstance(ack_mentions, bool):
        msg = "ack_mentions must be a boolean"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)


async def add_comment(arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute add_comment MCP tool to post Markdown comment to an issue."""
    ctx = get_current_mcp_context()
    if ctx is None or ctx.client is None:
        msg = "MCP request context or API client is unavailable"
        raise KbMcpError(McpErrorCode.INTERNAL, msg)

    # JIT help progressive disclosure
    if arguments.get("identifier") == "help" or arguments.get("action") == "help":
        return await build_help(
            "add_comment",
            client=ctx.client,
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )

    _validate_add_comment_arguments(arguments)

    identifier = str(arguments["identifier"]).strip()
    body_markdown = str(arguments["body_markdown"])
    reply_to = arguments.get("reply_to")
    ack_mentions = bool(arguments.get("ack_mentions", False))

    payload: dict[str, Any] = {
        "body_markdown": body_markdown,
    }
    if reply_to:
        payload["parent_comment_id"] = str(reply_to).strip()

    try:
        res = await ctx.client.request(
            "POST",
            f"/api/v1/issues/{identifier}/comments",
            json_data=payload,
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
            headers={"X-KB-MCP-Tool": "add_comment"},
        )
    except KbMcpError as exc:
        if exc.code == McpErrorCode.MENTION_ACCESS_WARNING:
            unauth = (exc.extra or {}).get("unauthorized_mentions", [])
            if ack_mentions and unauth:
                ack_pids = [
                    u["principal_id"] for u in unauth if isinstance(u, dict) and "principal_id" in u
                ]
                payload["acknowledge_mentions"] = ack_pids
                res = await ctx.client.request(
                    "POST",
                    f"/api/v1/issues/{identifier}/comments",
                    json_data=payload,
                    subject_token=ctx.subject_token,
                    mcp_session_id=ctx.session_id,
                    headers={"X-KB-MCP-Tool": "add_comment"},
                )
            else:
                handles = [
                    str(u.get("handle")) for u in unauth if isinstance(u, dict) and u.get("handle")
                ]
                handles_str = (
                    ", ".join(f"@{h.lstrip('@')}" for h in handles) if handles else "unknown"
                )
                msg = f"Mentioned users lack access to issue: {handles_str}."
                raise KbMcpError(
                    McpErrorCode.MENTION_ACCESS_WARNING,
                    msg,
                    hint="Pass ack_mentions=true to post without granting access.",
                    extra={"unauthorized_mentions": unauth},
                ) from exc
        else:
            raise

    if not isinstance(res, dict):
        msg = "Unexpected response from comment creation"
        raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

    comment_id = str(res.get("id", ""))
    short_id = comment_id.replace("-", "")[:8]
    permalink = str(res.get("permalink", ""))
    if "/issues/" in permalink:
        issue_key = permalink.rsplit("/issues/", maxsplit=1)[-1].split("#", maxsplit=1)[0]
    else:
        issue_key = identifier

    comment_ref = f"{issue_key}#c-{short_id}"
    return {
        "status": "commented",
        "key": issue_key,
        "comment": comment_ref,
    }
