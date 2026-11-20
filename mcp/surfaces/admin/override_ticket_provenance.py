# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tool 10: override_ticket_provenance for /mcp/admin (KB-P4-11, S11.4, S7.2)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from mcp.context import get_current_mcp_context
from mcp.errors import KbMcpError, McpErrorCode

if TYPE_CHECKING:
    from mcp.internal_client import KanbanApiClient

MIN_REASON_LEN: Final[int] = 10
MAX_REASON_LEN: Final[int] = 500

OVERRIDE_TICKET_PROVENANCE_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["override_creator", "override_hard_wip_move", "unarchive_issue", "help"],
            "description": "Administrative provenance override action to execute",
        },
        "issue": {
            "type": "string",
            "description": "Target issue key (e.g. 'KAN-142') or UUID (required except for help)",
        },
        "new_creator": {
            "type": "string",
            "description": "UUID or @handle of the new creator (required for override_creator)",
        },
        "target_state": {
            "type": "string",
            "description": (
                "Target workflow state name or UUID (required for override_hard_wip_move)"
            ),
        },
        "after_issue": {
            "type": "string",
            "description": "Optional rank anchor issue preceding target position",
        },
        "before_issue": {
            "type": "string",
            "description": "Optional rank anchor issue following target position",
        },
        "reason": {
            "type": "string",
            "minLength": MIN_REASON_LEN,
            "maxLength": MAX_REASON_LEN,
            "description": "Mandatory administrative justification (10 to 500 characters)",
        },
    },
    "required": ["action"],
    "additionalProperties": False,
}


async def override_ticket_provenance(  # noqa: C901, PLR0912, PLR0915
    arguments: dict[str, Any],
    *,
    client: KanbanApiClient | None = None,
) -> dict[str, Any]:
    """Execute administrative provenance overrides on tickets under caller authorization."""
    action = str(arguments.get("action", ""))
    if action not in ("override_creator", "override_hard_wip_move", "unarchive_issue", "help"):
        raise KbMcpError(
            McpErrorCode.VALIDATION_FAILED,
            f"Unknown action '{action}'. Valid actions: override_creator, "
            f"override_hard_wip_move, unarchive_issue, help",
        )

    if action == "help":
        return {
            "tool": "override_ticket_provenance",
            "description": (
                "Perform audited 'Created by' overrides, Hard WIP limit overrides, and "
                "unarchivals with a mandatory justification under PROJECT_ADMIN or SERVER_ADMIN."
            ),
            "actions": {
                "override_creator": "Override created_by on an issue with audit trail",
                "override_hard_wip_move": "Move an issue bypassing column hard WIP limit",
                "unarchive_issue": "Restore an archived issue to active board state",
                "help": "Show this help text",
            },
            "required_scope": "admin:write",
            "aal_required": 2,
        }

    issue_ref = str(arguments.get("issue", "")).strip()
    if not issue_ref:
        raise KbMcpError(
            McpErrorCode.VALIDATION_FAILED,
            "Parameter 'issue' is required for provenance override actions",
        )

    reason = str(arguments.get("reason", "")).strip()
    if len(reason) < MIN_REASON_LEN or len(reason) > MAX_REASON_LEN:
        raise KbMcpError(
            McpErrorCode.VALIDATION_FAILED,
            f"Parameter 'reason' must be between {MIN_REASON_LEN} and {MAX_REASON_LEN} characters",
        )

    ctx = get_current_mcp_context()
    active_client = client or (ctx.client if ctx else None)
    if active_client is None:
        raise KbMcpError(
            McpErrorCode.UPSTREAM_UNAVAILABLE,
            "Internal API client unavailable in request context",
        )

    subject_token = ctx.subject_token if ctx else None

    if action == "override_creator":
        new_creator = str(arguments.get("new_creator", "")).strip()
        if not new_creator:
            raise KbMcpError(
                McpErrorCode.VALIDATION_FAILED,
                "Parameter 'new_creator' is required for action 'override_creator'",
            )

        resp = await active_client.request(
            "PATCH",
            f"/api/v1/issues/{issue_ref}/created-by",
            subject_token=subject_token,
            json_data={"created_by": new_creator, "reason": reason},
        )
        if not isinstance(resp, dict):
            raise KbMcpError(
                McpErrorCode.UPSTREAM_ERROR,
                "Malformed response from created-by override endpoint",
            )

        issue_key = resp.get("key") or resp.get("issue_key") or issue_ref
        prov = resp.get("provenance")
        if isinstance(prov, dict):
            orig_val = prov.get("original_created_by")
            new_val = prov.get("created_by")
        else:
            orig_val = resp.get("original_created_by")
            new_val = resp.get("created_by")

        if isinstance(orig_val, dict):
            orig_handle = str(orig_val.get("handle") or orig_val.get("label") or "unknown")
        else:
            orig_handle = str(orig_val or "unknown")
        if not orig_handle.startswith("@") and orig_handle != "1 External Collaborator":
            orig_handle = f"@{orig_handle}"

        if isinstance(new_val, dict):
            new_handle = str(new_val.get("handle") or new_val.get("label") or new_creator)
        else:
            new_handle = str(new_val or new_creator)
        if not new_handle.startswith("@") and new_handle != "1 External Collaborator":
            new_handle = f"@{new_handle}"

        return {
            "status": "creator_overridden",
            "issue": issue_key,
            "original_created_by": orig_handle,
            "created_by": new_handle,
            "reason": reason,
        }

    if action == "override_hard_wip_move":
        target_state_input = str(arguments.get("target_state", "")).strip()
        if not target_state_input:
            raise KbMcpError(
                McpErrorCode.VALIDATION_FAILED,
                "Parameter 'target_state' is required for action 'override_hard_wip_move'",
            )

        # 1. Resolve issue to obtain project identifier/id
        issue_obj = await active_client.request(
            "GET",
            f"/api/v1/issues/{issue_ref}",
            subject_token=subject_token,
        )
        if not isinstance(issue_obj, dict):
            raise KbMcpError(
                McpErrorCode.UPSTREAM_ERROR,
                "Malformed response from issue lookup endpoint",
            )

        project_id = issue_obj.get("project_id")
        if not project_id:
            raise KbMcpError(
                McpErrorCode.UPSTREAM_ERROR,
                "Unable to determine project ID for target issue",
            )

        # 2. Query project workflow states to resolve target_state UUID and name
        states_resp = await active_client.request(
            "GET",
            f"/api/v1/projects/{project_id}/states",
            subject_token=subject_token,
        )
        states_list: list[Any]
        if isinstance(states_resp, list):
            states_list = states_resp
        elif isinstance(states_resp, dict) and isinstance(states_resp.get("items"), list):
            states_list = states_resp["items"]
        else:
            raise KbMcpError(
                McpErrorCode.UPSTREAM_ERROR,
                "Malformed response from project states endpoint",
            )

        matching_state: dict[str, Any] | None = None
        for s in states_list:
            if isinstance(s, dict):
                s_id = str(s.get("id", ""))
                s_name = str(s.get("name", ""))
                if s_id == target_state_input or s_name.casefold() == target_state_input.casefold():
                    matching_state = s
                    break

        if matching_state is None:
            raise KbMcpError(
                McpErrorCode.NOT_FOUND,
                f"Workflow state '{target_state_input}' not found in target project",
                field="target_state",
                fix_hint=(
                    "Verify workflow state name or list project states "
                    "using architect_project --action=get."
                ),
                cli_example=(
                    f'kanban-cli-admin architect_project --action=get --project="{project_id}"'
                ),
            )

        state_id = str(matching_state["id"])
        state_name = str(matching_state["name"])
        hard_limit = matching_state.get("wip_hard_limit")

        move_payload: dict[str, Any] = {
            "target_state_id": state_id,
            "wip_override_reason": reason,
            "override_wip": True,
        }
        if arguments.get("after_issue"):
            move_payload["after_issue"] = arguments["after_issue"]
        if arguments.get("before_issue"):
            move_payload["before_issue"] = arguments["before_issue"]

        move_resp = await active_client.request(
            "POST",
            f"/api/v1/issues/{issue_ref}/move",
            subject_token=subject_token,
            json_data=move_payload,
        )
        if not isinstance(move_resp, dict):
            raise KbMcpError(
                McpErrorCode.UPSTREAM_ERROR,
                "Malformed response from issue move endpoint",
            )

        resulting_count = move_resp.get("resulting_count")
        if resulting_count is None:
            wip_warn = move_resp.get("wip_warning")
            if isinstance(wip_warn, dict):
                resulting_count = wip_warn.get("resulting_count")
        if resulting_count is None and hard_limit is not None:
            resulting_count = hard_limit + 1

        resolved_hard_limit = move_resp.get("hard_limit") or hard_limit

        return {
            "status": "wip_overridden_moved",
            "issue": move_resp.get("issue_key", issue_ref),
            "state": state_name,
            "hard_limit": resolved_hard_limit,
            "resulting_count": resulting_count,
            "reason": reason,
        }

    # Execute unarchive_issue action
    unarchive_resp = await active_client.request(
        "POST",
        f"/api/v1/issues/{issue_ref}/unarchive",
        subject_token=subject_token,
        json_data={"reason": reason, "admin_override": True},
    )
    if not isinstance(unarchive_resp, dict):
        raise KbMcpError(
            McpErrorCode.UPSTREAM_ERROR,
            "Malformed response from issue unarchive endpoint",
        )

    return {
        "status": "issue_unarchived",
        "issue": unarchive_resp.get("key", issue_ref),
        "reason": reason,
    }
