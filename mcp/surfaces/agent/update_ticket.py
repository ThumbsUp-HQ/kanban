# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Implementation of the update_ticket MCP tool (KB-P4-05)."""

from __future__ import annotations

import contextlib
import re
from typing import TYPE_CHECKING, Any, Final

from kanban.security.push_protection import scan_text_for_secrets
from mcp.context import get_current_mcp_context
from mcp.errors import KbMcpError, McpErrorCode
from mcp.help import build_help
from mcp.lod import extract_issue_sequence

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "UPDATE_TICKET_SCHEMA",
    "update_ticket",
]

_MAX_SUMMARY_LEN: Final[int] = 500
_MAX_DESCRIPTION_BYTES: Final[int] = 1048576
_ETAG_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")

UPDATE_TICKET_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "identifier": {
            "type": "string",
        },
        "if_match": {
            "type": "string",
            "pattern": "^[0-9a-f]{64}$",
            "description": "ETag for description_markdown",
        },
        "summary": {
            "type": "string",
            "minLength": 1,
            "maxLength": 500,
        },
        "description_markdown": {
            "type": "string",
            "description": "Markdown (if_match)",
        },
        "description_mode": {
            "type": "string",
            "enum": ["append", "replace"],
            "default": "append",
        },
        "assignees_add": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 20,
        },
        "assignees_remove": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 20,
        },
        "priority": {
            "type": "string",
        },
        "start_date": {
            "type": ["string", "null"],
            "format": "date",
        },
        "due_date": {
            "type": ["string", "null"],
            "format": "date",
        },
        "cycle": {
            "type": ["string", "null"],
        },
        "modules_add": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 20,
        },
        "modules_remove": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 20,
        },
        "labels_add": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 20,
        },
        "labels_remove": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 20,
        },
        "parent": {
            "type": ["string", "null"],
        },
        "fencing_token": {
            "type": "integer",
        },
        "lease_action": {
            "type": "string",
            "enum": ["renew", "release", "keep"],
        },
    },
    "required": ["identifier"],
    "additionalProperties": False,
}

_ALLOWED_KEYS: Final[frozenset[str]] = frozenset(UPDATE_TICKET_SCHEMA["properties"].keys())


def _extract_principal_name(principal: dict[str, Any]) -> str | None:
    """Extract display name from a principal dictionary."""
    h = principal.get("handle")
    if h:
        return str(h) if str(h).startswith("@") else f"@{h}"
    if principal.get("display_name"):
        return f"@{principal['display_name'].lower().replace(' ', '')}"
    if principal.get("id"):
        return str(principal["id"])
    return None


def _format_assignees(raw_assignees: Sequence[object]) -> list[str]:
    """Format assignee models into human handles or names."""
    results: list[str] = []
    for item in raw_assignees:
        if isinstance(item, str):
            results.append(item)
        elif isinstance(item, dict):
            if item.get("kind") == "free_text" and item.get("free_text"):
                results.append(str(item["free_text"]))
            else:
                p = item.get("principal")
                if isinstance(p, dict):
                    name = _extract_principal_name(p)
                    if name:
                        results.append(name)
                elif item.get("handle"):
                    h = item["handle"]
                    results.append(str(h) if str(h).startswith("@") else f"@{h}")
    return results


async def update_ticket(arguments: dict[str, Any]) -> dict[str, Any]:  # noqa: C901, PLR0912, PLR0915
    """Execute update_ticket MCP tool applying atomic patch under description ETag concurrency."""
    ctx = get_current_mcp_context()
    if ctx is None or ctx.client is None:
        msg = "MCP request context unavailable"
        raise KbMcpError(McpErrorCode.INTERNAL, msg)

    identifier_arg = arguments.get("identifier")
    if identifier_arg == "help":
        return await build_help(
            "update_ticket",
            client=ctx.client,
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )

    # 1. Check for specific forbidden / restricted properties with designated hints
    if "custom_fields" in arguments:
        raise KbMcpError(
            McpErrorCode.VALIDATION_FAILED,
            "custom fields not supported",
            hint="custom fields arrive in Phase 5",
        )
    if "state" in arguments:
        raise KbMcpError(
            McpErrorCode.VALIDATION_FAILED,
            "state changes not permitted in update_ticket",
            hint="use transition_ticket",
        )

    for k in arguments:
        if k not in _ALLOWED_KEYS:
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, f"Unknown parameter '{k}'")

    if not identifier_arg or not isinstance(identifier_arg, str) or not identifier_arg.strip():
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, "identifier must be a non-empty string")

    identifier = identifier_arg.strip()

    # 2. Validate description and mandatory if_match
    has_description = "description_markdown" in arguments
    if_match = arguments.get("if_match")
    if has_description and (
        not if_match
        or not isinstance(if_match, str)
        or not _ETAG_PATTERN.fullmatch(if_match.strip())
    ):
        raise KbMcpError(
            McpErrorCode.VALIDATION_FAILED,
            "if_match header is required when description_markdown is present",
            hint="provide 64-character SHA-256 hex ETag",
        )

    if "fencing_token" in arguments and arguments["fencing_token"] is not None:
        ft = arguments["fencing_token"]
        if not isinstance(ft, int) or isinstance(ft, bool):
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, "fencing_token must be an integer")

    if "lease_action" in arguments and arguments["lease_action"] is not None:
        la = arguments["lease_action"]
        if la not in ("renew", "release", "keep"):
            raise KbMcpError(
                McpErrorCode.VALIDATION_FAILED,
                "lease_action must be 'renew', 'release', or 'keep'",
            )

    # 3. Fetch existing ticket
    safe_identifier = identifier.replace('"', '\\"')
    try:
        curr_issue = await ctx.client.request(
            "GET",
            f"/api/v1/issues/{identifier}",
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
    except KbMcpError as err:
        if err.code == McpErrorCode.NOT_FOUND:
            fix_hint = (
                err.fix_hint
                if err.fix_hint
                and err.fix_hint
                != "Verify identifier or use search tool to discover valid entities."
                else (
                    f"Ticket '{identifier}' was not found or you do not have access. "
                    "Search accessible tickets first."
                )
            )
            cli_example = (
                err.cli_example
                if err.cli_example
                and err.cli_example != 'kanban-cli-agent search_tickets --query=""'
                else f'kanban-cli-agent search_tickets --query="{safe_identifier}"'
            )
            raise KbMcpError(
                McpErrorCode.NOT_FOUND,
                err.message or f"ticket not found: {identifier}",
                field=err.field or "identifier",
                fix_hint=fix_hint,
                cli_example=cli_example,
                closest_match=err.closest_match,
            ) from None
        raise

    if not isinstance(curr_issue, dict):
        raise KbMcpError(
            McpErrorCode.NOT_FOUND,
            f"ticket not found: {identifier}",
            field="identifier",
            fix_hint=(
                f"Ticket '{identifier}' was not found or you do not have access. "
                "Search accessible tickets first."
            ),
            cli_example=f'kanban-cli-agent search_tickets --query="{safe_identifier}"',
        )

    issue_key = str(curr_issue.get("key", identifier))
    current_desc = str(curr_issue.get("description_markdown") or "")
    current_sha = str(curr_issue.get("description_sha256") or "")

    changed_fields: list[str] = []
    patch_body: dict[str, Any] = {}

    # 4. Handle summary update
    if "summary" in arguments:
        new_summary = arguments["summary"]
        if not isinstance(new_summary, str) or not new_summary.strip():
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, "summary must be a non-empty string")
        if len(new_summary.strip()) > _MAX_SUMMARY_LEN:
            msg = (
                f"summary length ({len(new_summary.strip())}) exceeds maximum of {_MAX_SUMMARY_LEN}"
            )
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
        summary_findings = scan_text_for_secrets(new_summary)
        if summary_findings:
            f = summary_findings[0]
            raise KbMcpError(
                McpErrorCode.SECRET_DETECTED_IN_PAYLOAD,
                f"Secret material detected in field 'summary' at line {f.line}",
                hint="Remove sensitive credentials, tokens, or private keys before submission.",
                field="summary",
                extra={
                    "rule_id": f.rule_id,
                    "secret_kind": f.kind.value,
                    "line": f.line,
                    "fingerprint": f.fingerprint,
                },
            )
        patch_body["summary"] = new_summary
        changed_fields.append("summary")

    # 5. Handle description update (append or replace)
    if has_description:
        mode = arguments.get("description_mode", "append")
        if mode not in ("append", "replace"):
            raise KbMcpError(
                McpErrorCode.VALIDATION_FAILED,
                "description_mode must be 'append' or 'replace'",
            )

        raw_desc = str(arguments["description_markdown"])
        if mode == "append":
            combined_desc = f"{current_desc}\n\n{raw_desc}" if current_desc else raw_desc
        else:
            combined_desc = raw_desc

        if len(combined_desc.encode("utf-8")) > _MAX_DESCRIPTION_BYTES:
            raise KbMcpError(
                McpErrorCode.VALIDATION_FAILED,
                f"resulting description exceeds maximum of {_MAX_DESCRIPTION_BYTES} bytes",
            )
        desc_findings = scan_text_for_secrets(combined_desc)
        if desc_findings:
            f = desc_findings[0]
            raise KbMcpError(
                McpErrorCode.SECRET_DETECTED_IN_PAYLOAD,
                f"Secret material detected in field 'description_markdown' at line {f.line}",
                hint="Remove sensitive credentials, tokens, or private keys before submission.",
                field="description_markdown",
                extra={
                    "rule_id": f.rule_id,
                    "secret_kind": f.kind.value,
                    "line": f.line,
                    "fingerprint": f.fingerprint,
                },
            )

        patch_body["description_markdown"] = combined_desc
        changed_fields.append("description_markdown")

    # 6. Handle dates
    if "start_date" in arguments:
        patch_body["start_date"] = arguments["start_date"]
        changed_fields.append("start_date")

    if "due_date" in arguments:
        patch_body["due_date"] = arguments["due_date"]
        changed_fields.append("due_date")

    eff_start = patch_body.get("start_date", curr_issue.get("start_date"))
    eff_due = patch_body.get("due_date", curr_issue.get("due_date"))
    if eff_start is not None and eff_due is not None and str(eff_due) < str(eff_start):
        raise KbMcpError(
            McpErrorCode.VALIDATION_FAILED,
            "due_date cannot be earlier than start_date",
        )

    # 7. Handle priority
    if "priority" in arguments:
        patch_body["priority"] = arguments["priority"]
        changed_fields.append("priority")

    # 8. Handle cycle
    if "cycle" in arguments:
        patch_body["cycle_id"] = arguments["cycle"]
        changed_fields.append("cycle")

    # 9. Handle parent
    if "parent" in arguments:
        patch_body["parent"] = arguments["parent"]
        changed_fields.append("parent")

    # 10. Handle modules
    has_mod_add = "modules_add" in arguments
    has_mod_rem = "modules_remove" in arguments
    if has_mod_add or has_mod_rem:
        current_mods = list(curr_issue.get("module_ids") or [])
        mods_set = {str(m) for m in current_mods}
        if has_mod_add:
            mods_add = arguments["modules_add"]
            if isinstance(mods_add, list):
                for m in mods_add:
                    mods_set.add(str(m))
        if has_mod_rem:
            mods_rem = arguments["modules_remove"]
            if isinstance(mods_rem, list):
                for m in mods_rem:
                    mods_set.discard(str(m))
        new_mods = list(mods_set)
        if sorted(new_mods) != sorted(str(m) for m in current_mods):
            patch_body["module_ids"] = new_mods
            changed_fields.append("modules")

    # 11. Handle labels
    has_lbl_add = "labels_add" in arguments
    has_lbl_rem = "labels_remove" in arguments
    if has_lbl_add or has_lbl_rem:
        current_labels = curr_issue.get("labels") or []
        lbls_set = {lbl["id"] if isinstance(lbl, dict) else lbl for lbl in current_labels}
        orig_lbls = set(lbls_set)
        if has_lbl_add:
            lbl_add = arguments["labels_add"]
            if isinstance(lbl_add, list):
                for lbl_item in lbl_add:
                    lbls_set.add(lbl_item)
        if has_lbl_rem:
            lbl_rem = arguments["labels_remove"]
            if isinstance(lbl_rem, list):
                for lbl_item in lbl_rem:
                    lbls_set.discard(lbl_item)
        if lbls_set != orig_lbls:
            patch_body["label_ids"] = list(lbls_set)
            changed_fields.append("labels")

    # 12. Send PATCH request if there are issue field changes
    patch_headers: dict[str, str] = {}
    if if_match is not None:
        patch_headers["If-Match"] = f'"{if_match.strip()}"'
    if "fencing_token" in arguments and arguments["fencing_token"] is not None:
        patch_headers["X-Fencing-Token"] = str(arguments["fencing_token"])

    patched_issue: dict[str, Any] = curr_issue
    if patch_body:
        try:
            res_patch = await ctx.client.request(
                "PATCH",
                f"/api/v1/issues/{issue_key}",
                json_data=patch_body,
                headers=patch_headers,
                subject_token=ctx.subject_token,
                mcp_session_id=ctx.session_id,
            )
            if isinstance(res_patch, dict):
                patched_issue = res_patch
        except KbMcpError as exc:
            if exc.code == McpErrorCode.CONFLICT_ETAG:
                fresh_sha = current_sha
                with contextlib.suppress(Exception):
                    fresh_issue = await ctx.client.request(
                        "GET",
                        f"/api/v1/issues/{issue_key}",
                        subject_token=ctx.subject_token,
                        mcp_session_id=ctx.session_id,
                    )
                    if isinstance(fresh_issue, dict):
                        fresh_sha = str(
                            fresh_issue.get("etag")
                            or fresh_issue.get("description_sha256")
                            or current_sha
                        )
                raise KbMcpError(
                    McpErrorCode.CONFLICT_ETAG,
                    "concurrency conflict: ticket description was modified concurrently",
                    hint=f"current etag: {fresh_sha}",
                    extra={"current_etag": fresh_sha},
                    fix_hint=(
                        "Ticket description was modified concurrently. "
                        f"Retry with fresh ETag: {fresh_sha}"
                    ),
                    cli_example=(
                        f'kanban-cli-agent update_ticket --identifier="{issue_key}" '
                        f'--if-match="{fresh_sha}"'
                    ),
                ) from None
            raise

    # 13. Handle assignees_add / assignees_remove
    assignees_modified = False
    if "assignees_add" in arguments:
        add_list = arguments["assignees_add"]
        if isinstance(add_list, list):
            current_raw_assignees = curr_issue.get("assignees", [])
            for a_item in add_list:
                a_str = str(a_item).strip()
                if not a_str:
                    continue
                # Skip if already assigned
                already_assigned = False
                clean_target = a_str.lower().lstrip("@")
                for ex_a in current_raw_assignees:
                    if not isinstance(ex_a, dict):
                        continue
                    if ex_a.get("kind") == "free_text":
                        if str(ex_a.get("free_text", "")).lower() == a_str.lower():
                            already_assigned = True
                            break
                    else:
                        p = ex_a.get("principal", {})
                        if isinstance(p, dict):
                            h = str(p.get("handle", "")).lower().lstrip("@")
                            dn = str(p.get("display_name", "")).lower()
                            pid = str(p.get("id", "")).lower()
                            if clean_target in (h, dn, pid) or a_str.lower() == pid:
                                already_assigned = True
                                break
                if already_assigned:
                    continue

                # Determine principal vs free-text
                payload: dict[str, Any]
                if a_str.startswith("@"):
                    payload = {"principal": a_str}
                else:
                    # Check if resolves to a user
                    try:
                        resolved = await ctx.client.request(
                            "GET",
                            "/api/v1/resolve",
                            params={"kind": "user", "ref": a_str},
                            subject_token=ctx.subject_token,
                            mcp_session_id=ctx.session_id,
                        )
                        if isinstance(resolved, dict) and "id" in resolved:
                            payload = {"principal": a_str}
                        else:
                            payload = {"free_text": a_str}
                    except KbMcpError:
                        payload = {"free_text": a_str}

                await ctx.client.request(
                    "POST",
                    f"/api/v1/issues/{issue_key}/assignees",
                    json_data=payload,
                    subject_token=ctx.subject_token,
                    mcp_session_id=ctx.session_id,
                )
                assignees_modified = True

    if "assignees_remove" in arguments:
        rem_list = arguments["assignees_remove"]
        if isinstance(rem_list, list):
            # Fetch latest assignees to find IDs
            latest_issue = await ctx.client.request(
                "GET",
                f"/api/v1/issues/{issue_key}",
                subject_token=ctx.subject_token,
                mcp_session_id=ctx.session_id,
            )
            raw_assignees = (
                latest_issue.get("assignees", []) if isinstance(latest_issue, dict) else []
            )
            for rem_item in rem_list:
                rem_str = str(rem_item).strip().lower()
                clean_rem = rem_str.lstrip("@")
                for a_obj in raw_assignees:
                    if not isinstance(a_obj, dict):
                        continue
                    a_id = a_obj.get("id")
                    match = False
                    if a_obj.get("kind") == "free_text":
                        ft = str(a_obj.get("free_text", "")).lower()
                        if ft == rem_str:
                            match = True
                    else:
                        p = a_obj.get("principal", {})
                        if isinstance(p, dict):
                            h = str(p.get("handle", "")).lower().lstrip("@")
                            dn = str(p.get("display_name", "")).lower()
                            pid = str(p.get("id", "")).lower()
                            if clean_rem in (h, dn, pid) or rem_str == str(a_id).lower():
                                match = True

                    if match and a_id:
                        await ctx.client.request(
                            "DELETE",
                            f"/api/v1/issues/{issue_key}/assignees/{a_id}",
                            subject_token=ctx.subject_token,
                            mcp_session_id=ctx.session_id,
                        )
                        assignees_modified = True

    if assignees_modified and "assignees" not in changed_fields:
        changed_fields.append("assignees")

    # 14. If assignees changed, re-fetch to get final state
    if assignees_modified:
        final_issue = await ctx.client.request(
            "GET",
            f"/api/v1/issues/{issue_key}",
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        if isinstance(final_issue, dict):
            patched_issue = final_issue

    # Handle lease_action
    lease_action = arguments.get("lease_action")
    if lease_action == "renew":
        hb_body: dict[str, Any] = {}
        if "fencing_token" in arguments and arguments["fencing_token"] is not None:
            hb_body["fencing_token"] = arguments["fencing_token"]
        await ctx.client.request(
            "POST",
            f"/api/v1/issues/{issue_key}/lease/heartbeat",
            json_data=hb_body,
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
    elif lease_action == "release":
        del_params: dict[str, Any] = {}
        if "fencing_token" in arguments and arguments["fencing_token"] is not None:
            del_params["fencing_token"] = arguments["fencing_token"]
        await ctx.client.request(
            "DELETE",
            f"/api/v1/issues/{issue_key}/lease",
            params=del_params,
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )

    # 15. Format return summary LOD
    state_val = patched_issue.get("state")
    state_str = (
        str(state_val.get("name", "")) if isinstance(state_val, dict) else str(state_val or "")
    )
    pri_val = patched_issue.get("priority")
    pri_str = str(pri_val.get("slug", "")) if isinstance(pri_val, dict) else str(pri_val or "")
    etag_val = patched_issue.get("etag") or patched_issue.get("description_sha256") or ""

    seq_num = extract_issue_sequence(patched_issue, issue_key)

    return {
        "key": issue_key,
        "issue_key": issue_key,
        "sequence_number": seq_num,
        "summary": patched_issue.get("summary", ""),
        "state": state_str,
        "priority": pri_str,
        "assignees": _format_assignees(patched_issue.get("assignees", [])),
        "etag": str(etag_val).strip('"'),
        "changed": changed_fields,
    }
