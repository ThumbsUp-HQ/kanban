# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tool destructive_lifecycle: Two-stage destructive confirmation gate (S11.4, KB-P4-12)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from mcp.context import current_internal_client, current_subject_token
from mcp.errors import KbMcpError, McpErrorCode
from mcp.registry import Surface, ToolSpec

if TYPE_CHECKING:
    from mcp.internal_client import KanbanApiClient

__all__ = [
    "ALLOWED_TARGET_KINDS",
    "create_destructive_lifecycle_tool",
    "destructive_lifecycle_handler",
]

_TOOL_NAME: Final[str] = "destructive_lifecycle"
_DESCRIPTION: Final[str] = (
    "Two-stage destructive confirmation gate for soft-trashing, permanent purging, and restoring "
    "Universal Object Graph entities (issues, projects, docs, pages, stickies, cycles, modules, views)."
)

ALLOWED_TARGET_KINDS: Final[frozenset[str]] = frozenset(
    {"issue", "project", "doc", "page", "sticky", "cycle", "module", "view"}
)

_INPUT_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["request_delete", "execute_delete", "restore", "help"],
            "description": "Destructive lifecycle action to perform",
        },
        "target_kind": {
            "type": "string",
            "enum": ["issue", "project", "doc", "page", "sticky", "cycle", "module", "view"],
            "description": "Universal Object Graph entity kind (required except for help)",
        },
        "target": {
            "type": "string",
            "description": "Human-readable key, identifier, or UUID (required except for help)",
        },
        "mode": {
            "type": "string",
            "enum": ["trash", "permanent_purge"],
            "default": "trash",
            "description": "Deletion mode: soft-delete to trash or permanent purge",
        },
        "confirmation_token": {
            "type": "string",
            "description": "Single-use 5-minute confirmation token (required for execute_delete)",
        },
        "confirm_phrase": {
            "type": "string",
            "description": "Literal uppercase confirmation phrase matching Stage 1 blast preview",
        },
        "reason": {
            "type": "string",
            "minLength": 10,
            "maxLength": 500,
            "description": "Mandatory audit reason (required for execute_delete and restore)",
        },
    },
    "required": ["action"],
    "additionalProperties": False,
}

_ALLOWED_KEYS: Final[frozenset[str]] = frozenset(_INPUT_SCHEMA["properties"].keys())


def _build_help_payload() -> dict[str, Any]:
    """Generate usage instructions and progressive guidance for destructive_lifecycle."""
    return {
        "tool": _TOOL_NAME,
        "description": _DESCRIPTION,
        "actions": {
            "request_delete": (
                "Stage 1: Computes recursive blast radius and issues a single-use 5m confirmation token."
            ),
            "execute_delete": (
                "Stage 2: Atomically claims token, verifies caller/target/blast-hash, and executes delete."
            ),
            "restore": "Restores a soft-deleted object from trash back to active state.",
            "help": "Show usage instructions and schema details.",
        },
        "supported_kinds": sorted(ALLOWED_TARGET_KINDS),
        "modes": ["trash", "permanent_purge"],
        "security": {
            "scope_required": "admin:destructive",
            "aal_required": 2,
            "permanent_purge_role": "SERVER_ADMIN",
            "blast_hash_protection": "TOCTOU-safe SHA-256 blast hash re-verified at execution time",
        },
    }


async def destructive_lifecycle_handler(  # noqa: C901, PLR0912, PLR0915
    arguments: dict[str, Any],
    *,
    client: KanbanApiClient | None = None,
    subject_token: str | None = None,
) -> dict[str, Any]:
    """Execute destructive_lifecycle actions against Kanban API."""
    for key in arguments:
        if key not in _ALLOWED_KEYS:
            msg = f"Unknown parameter '{key}'"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    action = arguments.get("action")
    if not action or action not in ("request_delete", "execute_delete", "restore", "help"):
        msg = f"Invalid or missing action '{action}'. Must be request_delete, execute_delete, restore, or help."
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if action == "help":
        return _build_help_payload()

    target_kind = arguments.get("target_kind")
    if not target_kind or target_kind not in ALLOWED_TARGET_KINDS:
        msg = f"Invalid or missing target_kind '{target_kind}'. Must be one of {sorted(ALLOWED_TARGET_KINDS)}."
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    target = arguments.get("target")
    if not target or not isinstance(target, str) or not target.strip():
        msg = "Parameter 'target' must be a non-empty string."
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
    if len(target) > 200:
        msg = f"Parameter 'target' length ({len(target)}) exceeds maximum of 200."
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    mode = arguments.get("mode", "trash")
    if mode not in ("trash", "permanent_purge"):
        msg = f"Invalid mode '{mode}'. Must be 'trash' or 'permanent_purge'."
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    active_client = client or current_internal_client()
    if active_client is None:
        raise KbMcpError(McpErrorCode.INTERNAL, "Kanban internal client is unavailable.")
    active_token = subject_token or current_subject_token()

    if action == "request_delete":
        res = await active_client.request(
            "POST",
            "/api/v1/admin/destructive:request",
            subject_token=active_token,
            json={
                "target_kind": target_kind,
                "target": target.strip(),
                "mode": mode,
            },
        )
        if not isinstance(res, dict):
            raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, "Unexpected non-object response from API")
        return {
            "stage": res.get("stage", "confirmation_required"),
            "target": res.get("target", target),
            "target_kind": res.get("target_kind", target_kind),
            "target_id": res.get("target_id", ""),
            "mode": res.get("mode", mode),
            "blast_summary": res.get("blast_summary", ""),
            "blast_hash": res.get("blast_hash", ""),
            "confirm_phrase": res.get("confirm_phrase", ""),
            "confirmation_token": res.get("confirmation_token", ""),
            "expires_in_sec": res.get("expires_in_sec", 300),
        }

    if action == "execute_delete":
        confirmation_token = arguments.get("confirmation_token")
        if not confirmation_token or not isinstance(confirmation_token, str):
            msg = "Missing required parameter 'confirmation_token' for execute_delete."
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        confirm_phrase = arguments.get("confirm_phrase")
        if not confirm_phrase or not isinstance(confirm_phrase, str):
            msg = "Missing required parameter 'confirm_phrase' for execute_delete."
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        reason = arguments.get("reason")
        if not reason or not isinstance(reason, str) or len(reason.strip()) < 10 or len(reason.strip()) > 500:
            msg = "Parameter 'reason' must be between 10 and 500 characters."
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        res = await active_client.request(
            "POST",
            "/api/v1/admin/destructive:execute",
            subject_token=active_token,
            json={
                "target_kind": target_kind,
                "target": target.strip(),
                "mode": mode,
                "confirmation_token": confirmation_token.strip(),
                "confirm_phrase": confirm_phrase.strip(),
                "reason": reason.strip(),
            },
        )
        if not isinstance(res, dict):
            raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, "Unexpected non-object response from API")
        return {
            "status": res.get("status", "executed"),
            "target": res.get("target", target),
            "target_kind": res.get("target_kind", target_kind),
            "target_id": res.get("target_id", ""),
            "mode": res.get("mode", mode),
            "reason": res.get("reason", reason),
            "blast_hash": res.get("blast_hash", ""),
        }

    # action == "restore"
    reason = arguments.get("reason")
    if not reason or not isinstance(reason, str) or len(reason.strip()) < 10 or len(reason.strip()) > 500:
        msg = "Parameter 'reason' must be between 10 and 500 characters."
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    res = await active_client.request(
        "POST",
        "/api/v1/admin/destructive:restore",
        subject_token=active_token,
        json={
            "target_kind": target_kind,
            "target": target.strip(),
            "reason": reason.strip(),
        },
    )
    if not isinstance(res, dict):
        raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, "Unexpected non-object response from API")
    return {
        "status": res.get("status", "restored"),
        "target": res.get("target", target),
        "target_kind": res.get("target_kind", target_kind),
        "target_id": res.get("target_id", ""),
        "reason": res.get("reason", reason),
    }


def create_destructive_lifecycle_tool(client: KanbanApiClient | None = None) -> ToolSpec:
    """Construct ToolSpec for destructive_lifecycle."""

    async def _handler(arguments: dict[str, Any], **kwargs: object) -> dict[str, Any]:
        raw_client = kwargs.get("client") or kwargs.get("internal_client")
        active_client = client or (raw_client if hasattr(raw_client, "request") else None)
        raw_token = kwargs.get("subject_token")
        active_token = str(raw_token) if raw_token is not None else None
        return await destructive_lifecycle_handler(
            arguments,
            client=active_client,  # type: ignore[arg-type]
            subject_token=active_token,
        )

    return ToolSpec(
        name=_TOOL_NAME,
        description=_DESCRIPTION,
        input_schema=_INPUT_SCHEMA,
        surface=Surface.ADMIN,
        handler=_handler,
    )
