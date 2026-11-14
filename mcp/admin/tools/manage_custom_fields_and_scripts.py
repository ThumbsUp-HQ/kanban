# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tool 7: manage_custom_fields_and_scripts for /mcp/admin (S11.4, S13.1, S13.3, KB-P5-13)."""

from __future__ import annotations

from typing import Any, Final

from mcp.context import get_current_mcp_context
from mcp.errors import KbMcpError, McpErrorCode
from mcp.help import build_help
from mcp.registry import Surface, ToolSpec
from mcp.yaml_out import dump_yaml

__all__ = [
    "MANAGE_CUSTOM_FIELDS_AND_SCRIPTS_SCHEMA",
    "create_manage_custom_fields_and_scripts_tool",
    "manage_custom_fields_and_scripts",
]

_ALLOWED_KEYS: Final[frozenset[str]] = frozenset(
    {
        "action",
        "project",
        "field",
        "issue",
        "name",
        "slug",
        "tier",
        "output_format",
        "output_format_metadata",
        "script_source",
        "wasm_module_sha256",
        "target_scope",
        "credential_mode",
        "egress_allowlist",
        "is_enabled",
        "wasm_base64",
        "manifest_sha256",
        "justification",
        "sp_warning_acknowledged",
        "force_refresh",
        "confirm",
        "lod",
    }
)

MANAGE_CUSTOM_FIELDS_AND_SCRIPTS_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": [
                "help",
                "list_fields",
                "upsert_field",
                "delete_field",
                "upload_wasm_module",
                "request_escalation",
                "approve_escalation",
                "execute_field",
            ],
            "description": "Administrative operation to perform",
        },
        "project": {
            "type": "string",
            "description": "Project slug or UUID identifier",
        },
        "field": {
            "type": "string",
            "description": "Field slug or UUID identifier",
        },
        "issue": {
            "type": "string",
            "description": "Issue key (e.g. KAN-142) for execute_field",
        },
        "name": {
            "type": "string",
            "description": "Human-readable field name",
        },
        "slug": {
            "type": "string",
            "description": "Unique URL/JSON slug for the field",
        },
        "tier": {
            "type": "string",
            "enum": ["wasm", "nsjail"],
            "description": "Execution sandbox tier",
        },
        "output_format": {
            "type": "string",
            "enum": [
                "text",
                "number",
                "badge",
                "markdown_snippet",
                "url",
                "json_table",
                "severity_pill",
            ],
            "description": "Strict output schema format",
        },
        "output_format_metadata": {
            "type": "object",
            "description": "Format-specific constraint schema metadata",
        },
        "script_source": {
            "type": "string",
            "description": "Script source code (nsjail) or hex/base64 wasm fallback",
        },
        "wasm_module_sha256": {
            "type": "string",
            "description": "SHA-256 digest of pre-registered ApprovedWasmModule",
        },
        "target_scope": {
            "type": "string",
            "enum": ["PROJECT", "WORKSPACE", "SERVER"],
            "description": "Authorization token scope tier",
        },
        "credential_mode": {
            "type": "string",
            "enum": ["INVOKING_USER", "PROJECT_ADMIN_SP", "SERVER_ADMIN_SP"],
            "description": "Execution principal credential mode",
        },
        "egress_allowlist": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Network egress domain allowlist (max 16)",
        },
        "is_enabled": {
            "type": "boolean",
            "description": "Whether custom field evaluation is enabled",
        },
        "wasm_base64": {
            "type": "string",
            "description": "Base64-encoded WebAssembly binary for upload_wasm_module",
        },
        "manifest_sha256": {
            "type": "string",
            "description": "Cryptographic manifest digest for escalation request/approval",
        },
        "justification": {
            "type": "string",
            "description": "Auditable business justification for escalation request",
        },
        "sp_warning_acknowledged": {
            "type": "boolean",
            "description": "Explicit acknowledgment of Service Principal capability escalation",
        },
        "force_refresh": {
            "type": "boolean",
            "description": "Bypass partition cache and force fresh execution",
        },
        "confirm": {
            "type": "boolean",
            "description": "Two-stage destructive confirmation flag required for permanent delete",
        },
        "lod": {
            "type": "string",
            "enum": ["summary", "standard", "full"],
            "default": "summary",
            "description": "Level of detail projection",
        },
    },
    "required": ["action"],
    "additionalProperties": False,
}


async def manage_custom_fields_and_scripts(  # noqa: C901, PLR0911, PLR0912, PLR0915
    arguments: dict[str, Any],
) -> str:
    """Tool 7 handler for custom fields, Wasm artifacts, escalation approvals, and execution."""
    for key in arguments:
        if key not in _ALLOWED_KEYS:
            msg = f"Unknown parameter '{key}'. Allowed: {sorted(_ALLOWED_KEYS)}"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    action = arguments.get("action")
    if not action or not isinstance(action, str):
        msg = "action parameter is required"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if action == "help":
        help_doc = await build_help(
            "manage_custom_fields_and_scripts",
            params_summary={
                "action": (
                    "list_fields | upsert_field | delete_field | upload_wasm_module | "
                    "request_escalation | approve_escalation | execute_field | help"
                ),
                "project": "slug | uuid",
                "field": "slug | uuid",
                "issue": "issue_key (e.g. KAN-142)",
            },
        )
        return dump_yaml(help_doc)

    ctx = get_current_mcp_context()
    if ctx is None or ctx.client is None:
        msg = "Internal API client unavailable"
        raise KbMcpError(McpErrorCode.UPSTREAM_UNAVAILABLE, msg)

    # Surface & key binding enforcement: tool 7 is exclusively on /mcp/admin (kb_adm_* keys)
    if ctx.surface != Surface.ADMIN:
        msg = (
            "Tool manage_custom_fields_and_scripts is only available on /mcp/admin "
            "(requires kb_adm_* key)"
        )
        raise KbMcpError(McpErrorCode.SURFACE_KEY_MISMATCH, msg)

    token = ctx.subject_token or ""
    if token.startswith("kb_agt_"):
        msg = (
            "Tool manage_custom_fields_and_scripts is only available on /mcp/admin "
            "(kb_agt_* key rejected)"
        )
        raise KbMcpError(McpErrorCode.SURFACE_KEY_MISMATCH, msg)

    # Scope authorization checks
    if ctx.caller_scopes is not None:
        if action == "list_fields":
            if not any(
                s in ctx.caller_scopes for s in ("admin:read", "admin:write", "admin:destructive")
            ):
                msg = f"Action '{action}' requires 'admin:read' scope"
                raise KbMcpError(McpErrorCode.INSUFFICIENT_SCOPE, msg)
        elif action in (
            "upsert_field",
            "upload_wasm_module",
            "request_escalation",
            "approve_escalation",
            "execute_field",
        ):
            if not any(s in ctx.caller_scopes for s in ("admin:write", "admin:destructive")):
                msg = f"Action '{action}' requires 'admin:write' scope"
                raise KbMcpError(McpErrorCode.INSUFFICIENT_SCOPE, msg)
        elif action == "delete_field" and "admin:destructive" not in ctx.caller_scopes:
            msg = "Action 'delete_field' requires 'admin:destructive' scope"
            raise KbMcpError(McpErrorCode.INSUFFICIENT_SCOPE, msg)

    project = arguments.get("project")
    field_ref = arguments.get("field")
    lod = arguments.get("lod", "summary")

    # Sub-command: list_fields
    if action == "list_fields":
        if not project:
            msg = "project parameter is required for list_fields"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        res = await ctx.client.request(
            "GET",
            f"/api/v1/projects/{project}/custom-fields",
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        if not isinstance(res, list):
            msg = "Unexpected response from list custom fields API"
            raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

        if lod == "full":
            return dump_yaml({"fields": res, "count": len(res)})

        projected: list[dict[str, Any]] = []
        for f in res:
            if isinstance(f, dict):
                item = {
                    "id": f.get("id"),
                    "slug": f.get("slug"),
                    "name": f.get("name"),
                    "tier": f.get("tier"),
                    "output_format": f.get("output_format"),
                    "target_scope": f.get("target_scope"),
                    "credential_mode": f.get("credential_mode"),
                    "is_enabled": f.get("is_enabled"),
                }
                if lod == "standard":
                    item["manifest_sha256"] = f.get("manifest_sha256")
                    item["approval_status"] = f.get("approval_status")
                projected.append(item)
        return dump_yaml({"fields": projected, "count": len(projected)})

    # Sub-command: upsert_field
    if action == "upsert_field":
        if not project:
            msg = "project parameter is required for upsert_field"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        body: dict[str, Any] = {}
        for prop in (
            "name",
            "slug",
            "tier",
            "output_format",
            "output_format_metadata",
            "script_source",
            "wasm_module_sha256",
            "target_scope",
            "credential_mode",
            "egress_allowlist",
            "is_enabled",
        ):
            if prop in arguments:
                body[prop] = arguments[prop]

        if field_ref:
            res = await ctx.client.request(
                "PATCH",
                f"/api/v1/projects/{project}/custom-fields/{field_ref}",
                json_data=body,
                subject_token=ctx.subject_token,
                mcp_session_id=ctx.session_id,
            )
            return dump_yaml({"status": "updated", "field": res})

        res = await ctx.client.request(
            "POST",
            f"/api/v1/projects/{project}/custom-fields",
            json_data=body,
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        return dump_yaml({"status": "created", "field": res})

    # Sub-command: delete_field
    if action == "delete_field":
        if not project or not field_ref:
            msg = "project and field parameters are required for delete_field"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        confirm = arguments.get("confirm", False)
        if confirm is not True:
            return dump_yaml(
                {
                    "status": "confirmation_required",
                    "action": "delete_field",
                    "project": project,
                    "field": field_ref,
                    "message": (
                        "Permanent deletion of custom field definition. "
                        "Re-run with confirm=true to proceed."
                    ),
                }
            )

        await ctx.client.request(
            "DELETE",
            f"/api/v1/projects/{project}/custom-fields/{field_ref}",
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        return dump_yaml({"status": "deleted", "field": field_ref})

    # Sub-command: upload_wasm_module
    if action == "upload_wasm_module":
        if not project:
            msg = "project parameter is required for upload_wasm_module"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        wasm_b64 = arguments.get("wasm_base64")
        mod_name = arguments.get("name", "wasm-module")
        if not wasm_b64:
            msg = "wasm_base64 parameter is required for upload_wasm_module"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        res = await ctx.client.request(
            "POST",
            f"/api/v1/projects/{project}/wasm-modules",
            json_data={"name": mod_name, "wasm_base64": wasm_b64},
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        return dump_yaml({"status": "uploaded", "module": res})

    # Sub-command: request_escalation
    if action == "request_escalation":
        if not project or not field_ref:
            msg = "project and field parameters are required for request_escalation"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        manifest = arguments.get("manifest_sha256")
        justification = arguments.get("justification")
        if not manifest or not justification:
            msg = "manifest_sha256 and justification are required for request_escalation"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        res = await ctx.client.request(
            "POST",
            f"/api/v1/projects/{project}/custom-fields/{field_ref}/approvals",
            json_data={"manifest_sha256": manifest, "justification": justification},
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        return dump_yaml({"status": "escalation_requested", "approval": res})

    # Sub-command: approve_escalation
    if action == "approve_escalation":
        if not project or not field_ref:
            msg = "project and field parameters are required for approve_escalation"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        manifest = arguments.get("manifest_sha256")
        sp_warn = arguments.get("sp_warning_acknowledged", False)
        if not manifest:
            msg = "manifest_sha256 is required for approve_escalation"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        res = await ctx.client.request(
            "POST",
            f"/api/v1/projects/{project}/custom-fields/{field_ref}/approvals/approve",
            json_data={"manifest_sha256": manifest, "sp_warning_acknowledged": sp_warn},
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        return dump_yaml({"status": "approved", "approval": res})

    # Sub-command: execute_field
    if action == "execute_field":
        issue_key = arguments.get("issue")
        if not issue_key or not field_ref:
            msg = "issue and field parameters are required for execute_field"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        force_ref = arguments.get("force_refresh", False)
        if force_ref:
            res = await ctx.client.request(
                "POST",
                f"/api/v1/issues/{issue_key}/custom-fields/{field_ref}/execute",
                subject_token=ctx.subject_token,
                mcp_session_id=ctx.session_id,
            )
            return dump_yaml({"result": res})

        res_list = await ctx.client.request(
            "GET",
            f"/api/v1/issues/{issue_key}/custom-fields",
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        if isinstance(res_list, list):
            for item in res_list:
                if (isinstance(item, dict) and item.get("field_id") == str(field_ref)) or item.get(
                    "slug"
                ) == str(field_ref):
                    return dump_yaml({"result": item})
        return dump_yaml({"result": res_list})

    msg = f"Unhandled action '{action}'"
    raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)


def create_manage_custom_fields_and_scripts_tool() -> ToolSpec:
    """Create ToolSpec instance for manage_custom_fields_and_scripts on /mcp/admin."""
    return ToolSpec(
        name="manage_custom_fields_and_scripts",
        description=(
            "Manage admin-defined custom fields, WebAssembly modules, "
            "cryptographic escalation approvals, and execution (S11.4 Tool 7)."
        ),
        input_schema=MANAGE_CUSTOM_FIELDS_AND_SCRIPTS_SCHEMA,
        surface=Surface.ADMIN,
        handler=manage_custom_fields_and_scripts,
    )
