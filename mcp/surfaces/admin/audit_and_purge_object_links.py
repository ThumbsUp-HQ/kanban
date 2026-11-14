# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tool 11: audit_and_purge_object_links for /mcp/admin (KB-P4-11, S11.4, S12.3)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from mcp.context import get_current_mcp_context
from mcp.errors import KbMcpError, McpErrorCode

if TYPE_CHECKING:
    from mcp.internal_client import KanbanApiClient

MIN_PURGE_REASON_LEN: Final[int] = 10
MAX_PURGE_REASON_LEN: Final[int] = 500
MAX_AUDIT_BATCH_SIZE: Final[int] = 200

ALLOWED_REASONS: Final[frozenset[str]] = frozenset(
    {
        "DANGLING_SOURCE",
        "DANGLING_TARGET",
        "SOFT_DELETED_ENDPOINT",
        "ARCHIVED_POLICY_VIOLATION",
        "TYPE_MATRIX_VIOLATION",
        "CROSS_WORKSPACE_LEAK",
        "PERMISSION_SEVERED",
    }
)

AUDIT_AND_PURGE_OBJECT_LINKS_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["run_audit", "list_flagged", "purge_audited", "help"],
            "description": "Administrative link auditor action to execute",
        },
        "reason_filter": {
            "type": "string",
            "enum": [
                "DANGLING_SOURCE",
                "DANGLING_TARGET",
                "SOFT_DELETED_ENDPOINT",
                "ARCHIVED_POLICY_VIOLATION",
                "TYPE_MATRIX_VIOLATION",
                "CROSS_WORKSPACE_LEAK",
                "PERMISSION_SEVERED",
            ],
            "description": "Optional invalid link classification filter",
        },
        "audit_ids": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": MAX_AUDIT_BATCH_SIZE,
            "description": "Flagged audit record UUIDs to purge (required for purge_audited)",
        },
        "reason": {
            "type": "string",
            "minLength": MIN_PURGE_REASON_LEN,
            "maxLength": MAX_PURGE_REASON_LEN,
            "description": (
                "Mandatory administrative justification for purge (10 to 500 characters)"
            ),
        },
        "lod": {
            "type": "string",
            "enum": ["summary", "standard", "full"],
            "default": "summary",
            "description": "Level of detail for list_flagged action",
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 100,
            "default": 50,
            "description": "Maximum number of audit records to return in list_flagged",
        },
        "cursor": {
            "type": "string",
            "description": "Pagination cursor for list_flagged",
        },
    },
    "required": ["action"],
    "additionalProperties": False,
}


async def audit_and_purge_object_links(  # noqa: C901, PLR0912, PLR0915
    arguments: dict[str, Any],
    *,
    client: KanbanApiClient | None = None,
) -> dict[str, Any]:
    """Execute Universal Object Graph auditor scans, inspect snapshots, and purge invalid links."""
    action = str(arguments.get("action", ""))
    if action not in ("run_audit", "list_flagged", "purge_audited", "help"):
        raise KbMcpError(
            McpErrorCode.VALIDATION_FAILED,
            f"Unknown action '{action}'. Valid actions: run_audit, list_flagged, "
            f"purge_audited, help",
        )

    if action == "help":
        return {
            "tool": "audit_and_purge_object_links",
            "description": (
                "Execute the 6-class Universal Object Graph Auditor, inspect flagged link "
                "snapshots, and purge audited entries with an immutable activity ledger record."
            ),
            "actions": {
                "run_audit": (
                    "Run audit scan across workspace and report counts by reason (admin:write)"
                ),
                "list_flagged": (
                    "List unpurged invalid link audit records at chosen LOD (admin:read)"
                ),
                "purge_audited": (
                    "Purge flagged invalid links permanently with reason (admin:destructive)"
                ),
                "help": "Show this help text",
            },
            "scopes": {
                "run_audit": "admin:write",
                "list_flagged": "admin:read",
                "purge_audited": "admin:destructive",
            },
        }

    ctx = get_current_mcp_context()
    active_client = client or (ctx.client if ctx else None)
    if active_client is None:
        raise KbMcpError(
            McpErrorCode.UPSTREAM_UNAVAILABLE,
            "Internal API client unavailable in request context",
        )

    subject_token = ctx.subject_token if ctx else None
    caller_scopes = ctx.caller_scopes if ctx else None

    # Scope separation enforcement
    if action == "purge_audited":
        if caller_scopes is not None and "admin:destructive" not in caller_scopes:
            raise KbMcpError(
                McpErrorCode.INSUFFICIENT_SCOPE,
                "Purging invalid object links requires admin:destructive scope",
            )

        raw_audit_ids = arguments.get("audit_ids")
        if not isinstance(raw_audit_ids, list) or len(raw_audit_ids) < 1:
            raise KbMcpError(
                McpErrorCode.VALIDATION_FAILED,
                "Parameter 'audit_ids' is required and must be a non-empty list of audit UUIDs",
            )
        if len(raw_audit_ids) > MAX_AUDIT_BATCH_SIZE:
            raise KbMcpError(
                McpErrorCode.VALIDATION_FAILED,
                f"Parameter 'audit_ids' exceeds maximum batch size of {MAX_AUDIT_BATCH_SIZE}",
            )

        reason = str(arguments.get("reason", "")).strip()
        if len(reason) < MIN_PURGE_REASON_LEN or len(reason) > MAX_PURGE_REASON_LEN:
            raise KbMcpError(
                McpErrorCode.VALIDATION_FAILED,
                f"Parameter 'reason' must be between {MIN_PURGE_REASON_LEN} and "
                f"{MAX_PURGE_REASON_LEN} characters",
            )

        purge_resp = await active_client.request(
            "POST",
            "/api/v1/admin/object-links:purge",
            subject_token=subject_token,
            json_data={"audit_ids": raw_audit_ids, "reason": reason},
        )
        if not isinstance(purge_resp, dict):
            raise KbMcpError(
                McpErrorCode.UPSTREAM_ERROR,
                "Malformed response from object-links:purge endpoint",
            )

        return {
            "status": "purged",
            "purged_count": purge_resp.get("purged_count", 0),
            "activity_ids": purge_resp.get("activity_ids", []),
            "reason": reason,
        }

    if action == "run_audit":
        if caller_scopes is not None and not {"admin:write", "admin:destructive"}.intersection(
            caller_scopes
        ):
            raise KbMcpError(
                McpErrorCode.INSUFFICIENT_SCOPE,
                "Running link audit requires admin:write or admin:destructive scope",
            )

        scan_resp = await active_client.request(
            "POST",
            "/api/v1/admin/object-links:audit",
            subject_token=subject_token,
        )
        if not isinstance(scan_resp, dict):
            raise KbMcpError(
                McpErrorCode.UPSTREAM_ERROR,
                "Malformed response from object-links:audit endpoint",
            )

        return {
            "flagged_total": scan_resp.get("flagged_total", 0),
            "by_reason": scan_resp.get("by_reason", {}),
        }

    # Execute list_flagged action
    params: dict[str, Any] = {
        "status": "unpurged",
        "limit": int(arguments.get("limit", 50)),
    }
    if arguments.get("reason_filter"):
        rf = str(arguments["reason_filter"])
        if rf not in ALLOWED_REASONS:
            allowed = ", ".join(sorted(ALLOWED_REASONS))
            raise KbMcpError(
                McpErrorCode.VALIDATION_FAILED,
                f"Invalid reason_filter '{rf}'. Must be one of: {allowed}",
            )
        params["reason_code"] = rf
    if arguments.get("cursor"):
        params["cursor"] = str(arguments["cursor"])

    list_resp = await active_client.request(
        "GET",
        "/api/v1/admin/object-links/audits",
        subject_token=subject_token,
        params=params,
    )
    if not isinstance(list_resp, dict):
        raise KbMcpError(
            McpErrorCode.UPSTREAM_ERROR,
            "Malformed response from object-links/audits endpoint",
        )

    lod = str(arguments.get("lod", "summary")).lower()
    raw_items = list_resp.get("items") or []

    if lod == "full":
        formatted_items = raw_items
    elif lod == "standard":
        formatted_items = []
        for it in raw_items:
            if isinstance(it, dict):
                ls = it.get("link_snapshot") or {}
                ss = it.get("source_snapshot") or {}
                ts = it.get("target_snapshot") or {}
                formatted_items.append(
                    {
                        "audit_id": str(it.get("id")),
                        "link_id": str(it.get("link_id")),
                        "reason": it.get("reason"),
                        "link_type": ls.get("link_type", "unknown"),
                        "source_key": ss.get("canonical_key") or str(ls.get("source_id", "")),
                        "target_key": ts.get("canonical_key") or str(ls.get("target_id", "")),
                    }
                )
    else:  # summary
        formatted_items = [
            {
                "audit_id": str(it.get("id")),
                "link_id": str(it.get("link_id")),
                "reason": it.get("reason"),
            }
            for it in raw_items
            if isinstance(it, dict)
        ]

    out_result: dict[str, Any] = {
        "total_unpurged": list_resp.get("total", len(formatted_items)),
        "total_returned": len(formatted_items),
        "has_more": list_resp.get("has_more", False),
        "items": formatted_items,
    }
    if list_resp.get("next_cursor"):
        out_result["next_cursor"] = list_resp["next_cursor"]

    return out_result
