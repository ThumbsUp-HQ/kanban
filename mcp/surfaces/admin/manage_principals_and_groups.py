# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""MCP Tool: manage_principals_and_groups (KB-P4-09b / S11.4)."""

from __future__ import annotations

import logging
from typing import Any

from mcp.context import get_current_mcp_context
from mcp.errors import KbMcpError, McpErrorCode
from mcp.registry import Surface, ToolSpec

logger = logging.getLogger(__name__)

MANAGE_PRINCIPALS_AND_GROUPS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": [
                "list",
                "get",
                "provision_user",
                "provision_group",
                "provision_agent",
                "deactivate",
                "reactivate",
                "add_member",
                "remove_member",
                "bind_role",
                "unbind_role",
                "help",
            ],
            "description": "Administrative action to perform",
        },
        "principal": {
            "type": "string",
            "description": "@handle, group name, agent slug, or UUID",
        },
        "group": {
            "type": "string",
            "description": "Target group name or UUID for membership actions",
        },
        "handle": {
            "type": "string",
            "pattern": "^[a-z0-9][a-z0-9._-]{1,38}$",
            "description": "User or agent handle without leading @",
        },
        "display_name": {
            "type": "string",
            "maxLength": 120,
            "description": "Human-readable display name",
        },
        "email": {
            "type": "string",
            "format": "email",
            "description": "User email address",
        },
        "role": {
            "type": "string",
            "description": "RBAC role enum (e.g. SERVER_ADMIN, WORKSPACE_ADMIN, MEMBER)",
        },
        "scope": {
            "type": "string",
            "description": "'server', 'workspace', or project key",
        },
        "filter": {
            "type": "string",
            "enum": ["USER", "GROUP", "AGENT", "SERVICE_PRINCIPAL"],
            "description": "Filter principals list by type",
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 100,
            "default": 50,
            "description": "Max items to return in list",
        },
    },
    "required": ["action"],
}


def create_manage_principals_and_groups_tool() -> ToolSpec:
    """Construct ToolSpec for manage_principals_and_groups."""
    return ToolSpec(
        name="manage_principals_and_groups",
        description=(
            "Provision and deactivate users, groups, and service agents; "
            "manage group memberships and RBAC role bindings."
        ),
        input_schema=MANAGE_PRINCIPALS_AND_GROUPS_SCHEMA,
        surface=Surface.ADMIN,
        handler=manage_principals_and_groups_tool,
    )


READ_ACTIONS = frozenset({"list", "get", "help"})
WRITE_ACTIONS = frozenset(
    {
        "provision_user",
        "provision_group",
        "provision_agent",
        "deactivate",
        "reactivate",
        "add_member",
        "remove_member",
        "bind_role",
        "unbind_role",
    }
)


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


async def manage_principals_and_groups_tool(  # noqa: C901, PLR0911, PLR0912, PLR0915
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Administer identity principals, groups, and role bindings."""
    action = arguments.get("action")
    if not action:
        raise KbMcpError(
            code=McpErrorCode.VALIDATION_FAILED,
            message="action is required",
            hint="Specify action='list', 'get', 'provision_user', etc. or action='help'",
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

    # 1. list
    if action == "list":
        filter_type = arguments.get("filter")
        limit = arguments.get("limit", 50)
        params: dict[str, Any] = {"limit": limit}
        if filter_type:
            params["filter"] = filter_type

        principals_data = await client.request("GET", "/api/v1/admin/principals", params=params)
        if not isinstance(principals_data, list):
            principals_data = []

        summary_list = [
            {
                "principal": p.get("principal"),
                "type": p.get("type"),
                "status": p.get("status"),
            }
            for p in principals_data
        ]
        return {"principals": summary_list}

    # 2. get
    if action == "get":
        principal_ref = arguments.get("principal")
        if not principal_ref:
            raise KbMcpError(
                code=McpErrorCode.VALIDATION_FAILED,
                message="principal is required for action='get'",
                hint="Provide @handle, group name, agent slug, or UUID",
            )
        data = await client.request("GET", f"/api/v1/admin/principals/{principal_ref}")
        if not isinstance(data, dict):
            return {}

        roles_summary = [
            {"role": r.get("role"), "scope": r.get("scope")}
            for r in data.get("roles", [])
            if isinstance(r, dict)
        ]
        return {
            "principal": data.get("principal"),
            "type": data.get("type"),
            "status": data.get("status"),
            "groups": data.get("groups", []),
            "roles": roles_summary,
        }

    # 3. provision_user
    if action == "provision_user":
        handle = arguments.get("handle")
        display_name = arguments.get("display_name")
        email = arguments.get("email")
        if not handle or not display_name or not email:
            raise KbMcpError(
                code=McpErrorCode.VALIDATION_FAILED,
                message="handle, display_name, and email are required for provision_user",
            )
        res = await client.request(
            "POST",
            "/api/v1/admin/principals",
            json_data={
                "type": "USER",
                "handle": handle,
                "display_name": display_name,
                "email": email,
            },
        )
        res_dict = res if isinstance(res, dict) else {}
        return {
            "status": "provisioned",
            "principal": res_dict.get("principal", f"@{handle.lstrip('@')}"),
            "type": "USER",
            "email": res_dict.get("email", email),
        }

    # 4. provision_group
    if action == "provision_group":
        display_name = arguments.get("display_name") or arguments.get("group")
        if not display_name:
            raise KbMcpError(
                code=McpErrorCode.VALIDATION_FAILED,
                message="display_name (or group) is required for provision_group",
            )
        res = await client.request(
            "POST",
            "/api/v1/admin/principals",
            json_data={
                "type": "GROUP",
                "display_name": display_name,
            },
        )
        res_dict = res if isinstance(res, dict) else {}
        return {
            "status": "provisioned",
            "principal": res_dict.get("principal", display_name),
            "type": "GROUP",
        }

    # 5. provision_agent
    if action == "provision_agent":
        handle = arguments.get("handle") or arguments.get("principal")
        display_name = arguments.get("display_name")
        if not handle or not display_name:
            raise KbMcpError(
                code=McpErrorCode.VALIDATION_FAILED,
                message="handle and display_name are required for provision_agent",
            )
        res = await client.request(
            "POST",
            "/api/v1/admin/principals",
            json_data={
                "type": "AGENT",
                "handle": handle,
                "display_name": display_name,
            },
        )
        res_dict = res if isinstance(res, dict) else {}
        return {
            "status": "provisioned",
            "principal": res_dict.get("principal", f"@{handle.lstrip('@')}"),
            "type": "AGENT",
        }

    # 6. deactivate / reactivate
    if action in ("deactivate", "reactivate"):
        principal_ref = arguments.get("principal")
        if not principal_ref:
            raise KbMcpError(
                code=McpErrorCode.VALIDATION_FAILED,
                message=f"principal is required for action='{action}'",
            )
        # First resolve principal to UUID if needed
        p_detail = await client.request("GET", f"/api/v1/admin/principals/{principal_ref}")
        p_dict = p_detail if isinstance(p_detail, dict) else {}
        p_id = p_dict.get("id") or principal_ref

        target_status = "deactivated" if action == "deactivate" else "active"
        res = await client.request(
            "PATCH",
            f"/api/v1/admin/principals/{p_id}",
            json_data={"status": target_status},
        )
        res_dict = res if isinstance(res, dict) else {}
        return {
            "status": "deactivated" if action == "deactivate" else "activated",
            "principal": res_dict.get("principal", principal_ref),
            "type": res_dict.get("type"),
        }

    # 7. add_member / remove_member
    if action in ("add_member", "remove_member"):
        group_ref = arguments.get("group")
        member_ref = arguments.get("principal")
        if not group_ref or not member_ref:
            raise KbMcpError(
                code=McpErrorCode.VALIDATION_FAILED,
                message=f"group and principal are required for action='{action}'",
            )
        g_detail = await client.request("GET", f"/api/v1/admin/principals/{group_ref}")
        m_detail = await client.request("GET", f"/api/v1/admin/principals/{member_ref}")

        g_dict = g_detail if isinstance(g_detail, dict) else {}
        m_dict = m_detail if isinstance(m_detail, dict) else {}

        g_id = g_dict.get("id") or group_ref
        m_id = m_dict.get("id") or member_ref

        method = "POST" if action == "add_member" else "DELETE"
        await client.request(method, f"/api/v1/admin/groups/{g_id}/members/{m_id}")
        return {
            "status": "member_added" if action == "add_member" else "member_removed",
            "group": g_dict.get("principal", group_ref),
            "member": m_dict.get("principal", member_ref),
        }

    # 8. bind_role / unbind_role
    if action in ("bind_role", "unbind_role"):
        principal_ref = arguments.get("principal")
        role = arguments.get("role")
        scope = arguments.get("scope", "workspace")
        if not principal_ref or not role:
            raise KbMcpError(
                code=McpErrorCode.VALIDATION_FAILED,
                message=f"principal and role are required for action='{action}'",
            )
        p_detail = await client.request("GET", f"/api/v1/admin/principals/{principal_ref}")
        p_dict = p_detail if isinstance(p_detail, dict) else {}
        p_id = p_dict.get("id") or principal_ref

        # Determine scope_type and scope_id
        scope_str = str(scope).strip()
        scope_type = "workspace"
        scope_id = None
        if scope_str.lower() == "server":
            scope_type = "server"
        elif scope_str.lower() == "workspace":
            scope_type = "workspace"
        else:
            # Assume project key or UUID
            scope_type = "project"
            proj = await client.request("GET", f"/api/v1/projects/{scope_str}")
            scope_id = proj.get("id") if isinstance(proj, dict) else None

        method = "POST" if action == "bind_role" else "DELETE"
        await client.request(
            method,
            "/api/v1/admin/role-bindings",
            json_data={
                "principal_id": p_id,
                "role": role,
                "scope_type": scope_type,
                "scope_id": scope_id,
            },
        )
        return {
            "status": "role_bound" if action == "bind_role" else "role_unbound",
            "principal": p_dict.get("principal", principal_ref),
            "role": role,
            "scope": scope_str,
        }

    return {}
