# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""MCP Tool: manage_access_policies (KB-P4-09b / S11.4, S3.4)."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

from mcp.context import get_current_mcp_context
from mcp.errors import KbMcpError, McpErrorCode
from mcp.registry import Surface, ToolSpec

logger = logging.getLogger(__name__)

MANAGE_ACCESS_POLICIES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["inspect", "grant", "revoke", "help"],
            "description": "Action to perform on object access policies",
        },
        "object": {
            "type": "string",
            "description": "Target object reference (issue key, doc path, project key, or UUID)",
        },
        "principal": {
            "type": "string",
            "description": "Target principal (@handle, group name, agent slug, or UUID)",
        },
        "effect": {
            "type": "string",
            "enum": ["ALLOW", "DENY"],
            "description": "Policy grant or restriction effect",
        },
        "capabilities": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "VIEW",
                    "COMMENT",
                    "EDIT",
                    "TRANSITION",
                    "LINK",
                    "SHARE",
                    "ADMIN",
                    "DELETE",
                ],
            },
            "minItems": 1,
            "maxItems": 8,
            "description": "Capability permissions to grant",
        },
    },
    "required": ["action"],
}


def create_manage_access_policies_tool() -> ToolSpec:
    """Construct ToolSpec for manage_access_policies."""
    return ToolSpec(
        name="manage_access_policies",
        description=(
            "Inspect an object's access_manifest and grant or revoke ALLOW/DENY capability entries."
        ),
        input_schema=MANAGE_ACCESS_POLICIES_SCHEMA,
        surface=Surface.ADMIN,
        handler=manage_access_policies_tool,
    )


READ_ACTIONS = frozenset({"inspect", "help"})
WRITE_ACTIONS = frozenset({"grant", "revoke"})


def _assert_scope(required_scope: str) -> None:
    """Verify caller holds required admin scope."""
    ctx = get_current_mcp_context()
    if ctx is None or ctx.caller_scopes is None:
        return
    if required_scope not in ctx.caller_scopes:
        raise KbMcpError(
            code=McpErrorCode.INSUFFICIENT_SCOPE,
            message=f"Caller lacks required scope '{required_scope}'",
        )


def _format_caps_summary(caps: list[str]) -> str:
    """Format list of capability names into compact summary."""
    if "ADMIN" in caps:
        return "ADMIN"
    if "EDIT" in caps:
        return "EDIT"
    if "COMMENT" in caps:
        return "COMMENT"
    if "VIEW" in caps:
        return "VIEW"
    return ", ".join(caps) if caps else "NONE"


def _format_inspect_summary(object_ref: str, manifest: dict[str, Any]) -> dict[str, Any]:
    """Format AccessManifest dictionary into compact Spec S11.4 summary YAML."""
    inherited = manifest.get("inherited_scope") or {}
    inherited_proj = inherited.get("project_key")
    inherited_label = inherited.get("scope_label") or (
        f"Project: {inherited_proj}" if inherited_proj else "Workspace"
    )

    users_list = [
        {
            "who": u.get("handle") or u.get("display_name"),
            "caps": _format_caps_summary(u.get("capabilities", [])),
        }
        for u in manifest.get("users", [])
        if isinstance(u, dict)
    ]

    groups_list = [
        {
            "who": g.get("name"),
            "members": g.get("member_count", 0),
            "caps": _format_caps_summary(g.get("capabilities", [])),
        }
        for g in manifest.get("groups", [])
        if isinstance(g, dict)
    ]

    agents_list = [
        {"who": a.get("display_name"), "caps": _format_caps_summary(a.get("capabilities", []))}
        for a in manifest.get("agents", [])
        if isinstance(a, dict)
    ]

    restricted_list = [
        {"who": d.get("display_name"), "effect": "DENY"}
        for d in manifest.get("deny_overrides", [])
        if isinstance(d, dict)
    ]

    out: dict[str, Any] = {
        "object": object_ref,
        "inherited_scope": inherited_label,
    }
    if users_list:
        out["users"] = users_list
    if groups_list:
        out["groups"] = groups_list
    if agents_list:
        out["agents"] = agents_list
    if restricted_list:
        out["restricted"] = restricted_list

    redacted = manifest.get("redacted_entries") or []
    if redacted and isinstance(redacted, list) and len(redacted) > 0:
        first_r = redacted[0]
        label = first_r.get("label") if isinstance(first_r, dict) else "1 External Collaborator"
        out["external"] = label

    return out


async def manage_access_policies_tool(  # noqa: C901
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Inspect access manifest and grant/revoke ALLOW/DENY capabilities on objects."""
    action = arguments.get("action")
    if not action:
        raise KbMcpError(
            code=McpErrorCode.VALIDATION_FAILED,
            message="action is required",
            hint="Specify action='inspect', 'grant', 'revoke', or 'help'",
        )

    action = str(action).strip()

    if action in READ_ACTIONS:
        _assert_scope("admin:read")
    elif action in WRITE_ACTIONS:
        _assert_scope("admin:write")
    else:
        raise KbMcpError(
            code=McpErrorCode.VALIDATION_FAILED,
            message=f"Unknown action: '{action}'",
            hint=f"Supported actions: {sorted(READ_ACTIONS | WRITE_ACTIONS)}",
        )

    ctx = get_current_mcp_context()
    if ctx is None or ctx.client is None:
        raise KbMcpError(
            code=McpErrorCode.INTERNAL,
            message="MCP internal client context is unavailable",
        )

    client = ctx.client
    object_ref = arguments.get("object")
    if not object_ref:
        raise KbMcpError(
            code=McpErrorCode.VALIDATION_FAILED,
            message="object is required",
            hint="Provide object identifier, issue key, or UUID",
        )

    # 1. inspect
    if action == "inspect":
        manifest_data = await client.request(
            "GET", f"/api/v1/admin/acl-entries/{quote(str(object_ref).strip())}/manifest"
        )
        if not isinstance(manifest_data, dict):
            return {"object": object_ref}
        return _format_inspect_summary(object_ref, manifest_data)

    # 2. grant / revoke
    principal_ref = arguments.get("principal")
    if not principal_ref:
        raise KbMcpError(
            code=McpErrorCode.VALIDATION_FAILED,
            message=f"principal is required for action='{action}'",
        )
    effect = arguments.get("effect", "ALLOW")

    if action == "grant":
        capabilities = arguments.get("capabilities")
        if not capabilities or not isinstance(capabilities, list):
            raise KbMcpError(
                code=McpErrorCode.VALIDATION_FAILED,
                message="capabilities array is required for grant (min 1, max 8 items)",
            )
        res = await client.request(
            "POST",
            "/api/v1/admin/acl-entries",
            json_data={
                "object_id": str(object_ref).strip(),
                "principal_id": str(principal_ref).strip(),
                "effect": effect,
                "capabilities": capabilities,
            },
        )
        return {
            "status": "granted",
            "object": object_ref,
            "principal": str(principal_ref),
            "effect": effect,
            "capabilities": res.get("capabilities", capabilities),
            "effective_capabilities": res.get("effective_capabilities", []),
        }

    if action == "revoke":
        res = await client.request(
            "DELETE",
            "/api/v1/admin/acl-entries",
            json_data={
                "object_id": str(object_ref).strip(),
                "principal_id": str(principal_ref).strip(),
                "effect": effect,
            },
        )
        return {
            "status": "revoked",
            "object": object_ref,
            "principal": str(principal_ref),
            "effect": effect,
            "effective_capabilities": res.get("effective_capabilities", []),
        }

    return {}
