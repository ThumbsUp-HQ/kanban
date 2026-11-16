# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: C901, PLR0911, PLR0912, PLR0915, ERA001, BLE001, S110, TRY300, E501
"""Implementation of the manage_workflow_interceptors MCP tool (KB-P5-17b, S11.4)."""

from __future__ import annotations

import uuid
from typing import Any, Final

from mcp.context import get_current_mcp_context
from mcp.errors import KbMcpError, McpErrorCode
from mcp.registry import Surface, ToolSpec
from mcp.resolver import EntityResolver
from mcp.yaml_out import dump_yaml

__all__ = [
    "MANAGE_WORKFLOW_INTERCEPTORS_SCHEMA",
    "create_manage_workflow_interceptors_tool",
    "manage_workflow_interceptors",
]

_MUTABLE_FIELD_UNIVERSE: Final[list[str]] = [
    "labels",
    "priority",
    "assignees",
    "start_date",
    "due_date",
    "cycle",
    "custom_fields.risk_rating",
    "custom_fields.qa_status",
    "custom_fields.security_review",
]

_VALID_ACTIONS: Final[frozenset[str]] = frozenset(
    {
        "help",
        "list",
        "attach",
        "update",
        "reorder",
        "enable",
        "disable",
        "detach",
        "dry_run",
    }
)

MANAGE_WORKFLOW_INTERCEPTORS_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": [
                "help",
                "list",
                "attach",
                "update",
                "reorder",
                "enable",
                "disable",
                "detach",
                "dry_run",
            ],
            "description": "Operation to perform on workflow hooks and interceptors",
        },
        "project": {
            "type": "string",
            "description": "Project human key (e.g. 'KAN') or UUID",
        },
        "hook": {
            "type": "string",
            "description": "Workflow hook UUID or unique name",
        },
        "name": {
            "type": "string",
            "description": "Name for the attached hook (e.g. 'require-qa-proof-link')",
        },
        "from_state": {
            "type": "string",
            "description": "Source workflow state name, UUID, or '*' for wildcard",
        },
        "to_state": {
            "type": "string",
            "description": "Target workflow state name or UUID",
        },
        "hook_kind": {
            "type": "string",
            "enum": ["sync_validator", "sync_mutator", "agent_interceptor"],
            "description": "Kind of hook to attach",
        },
        "failure_policy": {
            "type": "string",
            "enum": ["fail_closed", "fail_open_warn"],
            "description": "Execution failure policy: fail_closed (default) or fail_open_warn",
        },
        "wasm_module_sha256": {
            "type": "string",
            "description": "32-byte hex SHA-256 of approved WASM module",
        },
        "agent": {
            "type": "string",
            "description": "Agent definition slug or UUID (required for agent_interceptor)",
        },
        "allowed_mutable_fields": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of fields this mutator is permitted to modify",
        },
        "ordered_hook_ids": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Complete list of hook IDs in desired execution order for reorder",
        },
        "issue": {
            "type": "string",
            "description": "Issue key (e.g. 'KAN-142') or UUID for dry-run target",
        },
        "sample_ticket": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "description_markdown": {"type": "string"},
                "priority": {"type": "string"},
                "labels": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["summary", "description_markdown"],
            "description": "Synthetic ticket specification for dry-run",
        },
        "confirm": {
            "type": "boolean",
            "description": "Explicit confirmation for destructive detach operation",
        },
        "lod": {
            "type": "string",
            "enum": ["summary", "standard", "full"],
            "default": "summary",
            "description": "Level of detail for output projection",
        },
    },
    "required": ["action"],
}

_ALLOWED_KEYS: Final[frozenset[str]] = frozenset(
    MANAGE_WORKFLOW_INTERCEPTORS_SCHEMA["properties"].keys()
)


async def _resolve_project(resolver: EntityResolver, project_ref: str) -> str:
    """Resolve project reference (slug/key or UUID) via EntityResolver."""
    ref_str = project_ref.strip()
    try:
        uuid.UUID(ref_str)
        return ref_str
    except ValueError:
        pass
    resolved = await resolver.resolve("project", ref_str)
    return resolved.id


async def _resolve_state(
    resolver: EntityResolver,
    project_id: str,
    state_ref: str | None,
) -> str | None:
    """Resolve state reference to state ID or preserve wildcard null."""
    if state_ref is None or state_ref.strip() in ("", "*"):
        return None
    ref_str = state_ref.strip()
    try:
        uuid.UUID(ref_str)
        return ref_str
    except ValueError:
        pass
    try:
        resolved = await resolver.resolve("state", ref_str, project=project_id)
        return resolved.id
    except Exception:
        # Fall back to passing ref_str directly to REST API
        return ref_str


async def manage_workflow_interceptors(arguments: dict[str, Any]) -> str:
    """Execute /mcp/admin tool 8 manage_workflow_interceptors action."""
    for key in arguments:
        if key not in _ALLOWED_KEYS:
            msg = f"Unknown parameter '{key}'. Allowed: {sorted(_ALLOWED_KEYS)}"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    action = arguments.get("action")
    if not action or not isinstance(action, str):
        msg = "action parameter is required"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if action not in _VALID_ACTIONS:
        msg = f"Unknown action '{action}'. Valid actions: {sorted(_VALID_ACTIONS)}"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    ctx = get_current_mcp_context()

    # -------------------------------------------------------------------------
    # Action: help (accessible without context or scopes)
    # -------------------------------------------------------------------------
    if action == "help":
        live_states: list[str] = []
        agent_slugs: list[str] = []
        if ctx is not None and ctx.client is not None:
            resolver = EntityResolver(
                ctx.client,
                subject_token=ctx.subject_token,
                mcp_session_id=ctx.session_id,
            )
            project_arg = arguments.get("project")
            if project_arg:
                try:
                    proj_id = await _resolve_project(resolver, project_arg)
                    states_res = await ctx.client.request(
                        "GET",
                        f"/api/v1/projects/{proj_id}/states",
                        subject_token=ctx.subject_token,
                        mcp_session_id=ctx.session_id,
                    )
                    if isinstance(states_res, list):
                        live_states = [s.get("name", "") for s in states_res if isinstance(s, dict)]
                except Exception:
                    pass
            try:
                agents_res = await ctx.client.request(
                    "GET",
                    "/api/v1/agent-definitions",
                    subject_token=ctx.subject_token,
                    mcp_session_id=ctx.session_id,
                )
                agents_list = agents_res if isinstance(agents_res, list) else []
                agent_slugs = [
                    str(a.get("slug")) for a in agents_list if isinstance(a, dict) and a.get("slug")
                ]
            except Exception:
                pass

        help_data = {
            "tool": "manage_workflow_interceptors",
            "description": "Manage and dry-run Tier A sync validators/mutators and Tier B agent interceptors",
            "actions": sorted(_VALID_ACTIONS),
            "live_states": live_states or ["* (wildcard)"],
            "registered_agents": agent_slugs,
            "mutable_field_universe": _MUTABLE_FIELD_UNIVERSE,
            "immutable_fields_notice": (
                "summary, description_markdown, state, parent, and created_by are immutable "
                "to preserve zero-TOCTOU guarantees."
            ),
            "dry_run_semantics": (
                "Simulates complete pipeline in transactional SAVEPOINT with immediate ROLLBACK. "
                "Zero DB rows persisted. WASM hooks execute with 25ms budget; agent hooks return skipped_async."
            ),
            "params": {
                "action": "help | list | attach | update | reorder | enable | disable | detach | dry_run",
                "project": "slug | uuid",
                "hook": "uuid | name",
                "from_state": "state name | uuid | *",
                "to_state": "state name | uuid",
                "hook_kind": "sync_validator | sync_mutator | agent_interceptor",
                "issue": "issue_key (e.g. KAN-142) | uuid",
            },
        }
        return dump_yaml(help_data)

    if ctx is None or ctx.client is None:
        msg = "Internal API client unavailable"
        raise KbMcpError(McpErrorCode.UPSTREAM_UNAVAILABLE, msg)

    # 1. Surface and key scoping: Tool 8 is exclusively on /mcp/admin (kb_adm_* keys)
    if ctx.surface != Surface.ADMIN:
        msg = (
            "Tool manage_workflow_interceptors is only available on /mcp/admin "
            "(requires kb_adm_* key)"
        )
        raise KbMcpError(McpErrorCode.SURFACE_KEY_MISMATCH, msg)

    token = ctx.subject_token or ""
    if token.startswith("kb_agt_"):
        msg = (
            "Tool manage_workflow_interceptors is only available on /mcp/admin "
            "(kb_agt_* key rejected)"
        )
        raise KbMcpError(McpErrorCode.SURFACE_KEY_MISMATCH, msg)

    # 2. Scope checks
    if ctx.caller_scopes is not None:
        if action == "list":
            if not any(
                s in ctx.caller_scopes for s in ("admin:read", "admin:write", "admin:destructive")
            ):
                msg = f"Action '{action}' requires 'admin:read' scope"
                raise KbMcpError(McpErrorCode.INSUFFICIENT_SCOPE, msg)
        elif action in ("attach", "update", "reorder", "enable", "disable", "dry_run"):
            if not any(s in ctx.caller_scopes for s in ("admin:write", "admin:destructive")):
                msg = f"Action '{action}' requires 'admin:write' scope"
                raise KbMcpError(McpErrorCode.INSUFFICIENT_SCOPE, msg)
        elif action == "detach" and "admin:destructive" not in ctx.caller_scopes:
            msg = "Action 'detach' requires 'admin:destructive' scope"
            raise KbMcpError(McpErrorCode.INSUFFICIENT_SCOPE, msg)

    resolver = EntityResolver(
        ctx.client,
        subject_token=ctx.subject_token,
        mcp_session_id=ctx.session_id,
    )

    lod = arguments.get("lod", "summary")
    project_arg = arguments.get("project")

    # -------------------------------------------------------------------------
    # Action: list
    # -------------------------------------------------------------------------
    if action == "list":
        if not project_arg:
            msg = "project parameter is required for action 'list'"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        proj_id = await _resolve_project(resolver, project_arg)
        rules_res = await ctx.client.request(
            "GET",
            f"/api/v1/projects/{proj_id}/workflow-hooks",
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        if not isinstance(rules_res, list):
            msg = "Unexpected response from workflow hooks listing"
            raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

        if lod == "full":
            return dump_yaml({"project": project_arg, "transition_rules": rules_res})

        projected: list[dict[str, Any]] = []
        for r in rules_res:
            if isinstance(r, dict):
                hooks_list = r.get("hooks", [])
                p_hooks: list[dict[str, Any]] = []
                for h in hooks_list:
                    if isinstance(h, dict):
                        h_item = {
                            "id": h.get("id"),
                            "name": h.get("name"),
                            "hook_kind": h.get("hook_kind"),
                            "is_enabled": h.get("is_enabled"),
                        }
                        if lod == "standard":
                            h_item["sort_rank"] = h.get("sort_rank")
                            h_item["failure_policy"] = h.get("failure_policy")
                            h_item["allowed_mutable_fields"] = h.get("allowed_mutable_fields")
                            h_item["agent_slug"] = h.get("agent_slug")
                            h_item["wasm_module_sha256"] = h.get("wasm_module_sha256")
                        p_hooks.append(h_item)
                projected.append(
                    {
                        "from_state": r.get("from_state"),
                        "to_state": r.get("to_state"),
                        "active_hook_count": r.get("active_hook_count"),
                        "hooks": p_hooks,
                    }
                )
        return dump_yaml({"project": project_arg, "transition_rules": projected})

    # -------------------------------------------------------------------------
    # Action: attach
    # -------------------------------------------------------------------------
    if action == "attach":
        if not project_arg:
            msg = "project parameter is required for action 'attach'"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
        name = arguments.get("name")
        to_state = arguments.get("to_state")
        hook_kind = arguments.get("hook_kind")
        if not name or not to_state or not hook_kind:
            msg = "name, to_state, and hook_kind parameters are required for action 'attach'"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        if (
            hook_kind in ("sync_validator", "sync_mutator")
            and "wasm_module_sha256" not in arguments
        ):
            msg = f"wasm_module_sha256 parameter is required for hook_kind '{hook_kind}'"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        if hook_kind == "sync_mutator":
            if "allowed_mutable_fields" not in arguments or not arguments["allowed_mutable_fields"]:
                msg = "allowed_mutable_fields parameter is required for hook_kind 'sync_mutator'"
                raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
            invalid_fields = [
                f for f in arguments["allowed_mutable_fields"] if f not in _MUTABLE_FIELD_UNIVERSE
            ]
            if invalid_fields:
                msg = (
                    f"Fields {invalid_fields} are not permitted for mutation. "
                    f"Permitted universe: {_MUTABLE_FIELD_UNIVERSE}"
                )
                raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        if hook_kind == "agent_interceptor" and "agent" not in arguments:
            msg = "agent parameter is required for hook_kind 'agent_interceptor'"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        proj_id = await _resolve_project(resolver, project_arg)
        resolved_from = await _resolve_state(resolver, proj_id, arguments.get("from_state"))
        resolved_to = await _resolve_state(resolver, proj_id, to_state)

        body: dict[str, Any] = {
            "name": name,
            "from_state": resolved_from,
            "to_state": resolved_to,
            "hook_kind": hook_kind,
            "failure_policy": arguments.get("failure_policy", "fail_closed"),
        }
        if "wasm_module_sha256" in arguments:
            body["wasm_module_sha256"] = arguments["wasm_module_sha256"]
        if "agent" in arguments:
            body["agent"] = arguments["agent"]
        if "allowed_mutable_fields" in arguments:
            body["allowed_mutable_fields"] = arguments["allowed_mutable_fields"]

        res = await ctx.client.request(
            "POST",
            f"/api/v1/projects/{proj_id}/workflow-hooks",
            json_data=body,
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        return dump_yaml({"status": "attached", "hook": res})

    # -------------------------------------------------------------------------
    # Action: update
    # -------------------------------------------------------------------------
    if action == "update":
        hook_ref = arguments.get("hook")
        if not hook_ref:
            msg = "hook parameter is required for action 'update'"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        body = {}
        for prop in (
            "name",
            "failure_policy",
            "allowed_mutable_fields",
            "wasm_module_sha256",
            "agent",
        ):
            if prop in arguments:
                body[prop] = arguments[prop]

        res = await ctx.client.request(
            "PATCH",
            f"/api/v1/workflow-hooks/{hook_ref}",
            json_data=body,
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        return dump_yaml({"status": "updated", "hook": res})

    # -------------------------------------------------------------------------
    # Action: reorder
    # -------------------------------------------------------------------------
    if action == "reorder":
        if not project_arg:
            msg = "project parameter is required for action 'reorder'"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
        to_state = arguments.get("to_state")
        ordered_ids = arguments.get("ordered_hook_ids")
        if not to_state or not ordered_ids or not isinstance(ordered_ids, list):
            msg = (
                "to_state and ordered_hook_ids (list) parameters are required for action 'reorder'"
            )
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        proj_id = await _resolve_project(resolver, project_arg)
        resolved_from = await _resolve_state(resolver, proj_id, arguments.get("from_state"))
        resolved_to = await _resolve_state(resolver, proj_id, to_state)

        reorder_body = {
            "transition": {
                "from_state": resolved_from,
                "to_state": resolved_to,
            },
            "ordered_hook_ids": ordered_ids,
        }
        res = await ctx.client.request(
            "POST",
            f"/api/v1/projects/{proj_id}/workflow-hooks/reorder",
            json_data=reorder_body,
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        return dump_yaml({"status": "reordered", "hooks": res})

    # -------------------------------------------------------------------------
    # Action: enable / disable
    # -------------------------------------------------------------------------
    if action in ("enable", "disable"):
        hook_ref = arguments.get("hook")
        if not hook_ref:
            msg = f"hook parameter is required for action '{action}'"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        res = await ctx.client.request(
            "POST",
            f"/api/v1/workflow-hooks/{hook_ref}/{action}",
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        return dump_yaml({"status": f"{action}d", "hook": res})

    # -------------------------------------------------------------------------
    # Action: detach (with 2-stage confirmation)
    # -------------------------------------------------------------------------
    if action == "detach":
        hook_ref = arguments.get("hook")
        if not hook_ref:
            msg = "hook parameter is required for action 'detach'"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        confirm = arguments.get("confirm", False)
        if not confirm:
            return dump_yaml(
                {
                    "status": "confirmation_required",
                    "requires_confirmation": True,
                    "warning": f"Detaching hook '{hook_ref}' requires explicit confirm: true parameter",
                    "hook": hook_ref,
                    "copyable_confirmation": f"action: detach\nhook: {hook_ref}\nconfirm: true",
                }
            )

        res = await ctx.client.request(
            "DELETE",
            f"/api/v1/workflow-hooks/{hook_ref}",
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        return dump_yaml({"status": "detached", "hook": hook_ref})

    # -------------------------------------------------------------------------
    # Action: dry_run
    # -------------------------------------------------------------------------
    if action == "dry_run":
        if not project_arg:
            msg = "project parameter is required for action 'dry_run'"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
        to_state = arguments.get("to_state")
        if not to_state:
            msg = "to_state parameter is required for action 'dry_run'"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        if "issue" not in arguments and "sample_ticket" not in arguments:
            msg = "Either 'issue' or 'sample_ticket' parameter is required for action 'dry_run'"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        proj_id = await _resolve_project(resolver, project_arg)
        resolved_from = await _resolve_state(resolver, proj_id, arguments.get("from_state"))
        resolved_to = await _resolve_state(resolver, proj_id, to_state)

        dry_body: dict[str, Any] = {
            "from_state": resolved_from,
            "to_state": resolved_to,
        }
        if "issue" in arguments:
            dry_body["issue_key"] = arguments["issue"]
        if "sample_ticket" in arguments:
            dry_body["sample_ticket"] = arguments["sample_ticket"]

        res = await ctx.client.request(
            "POST",
            f"/api/v1/projects/{proj_id}/workflow-hooks/dry-run",
            json_data=dry_body,
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        return dump_yaml(res)

    msg = f"Unhandled action '{action}'"
    raise KbMcpError(McpErrorCode.INTERNAL, msg)


def create_manage_workflow_interceptors_tool() -> ToolSpec:
    """Create tool specification for /mcp/admin tool 8 manage_workflow_interceptors."""
    return ToolSpec(
        name="manage_workflow_interceptors",
        description=(
            "Manage, order, attach, detach, and dry-run workflow transition hooks "
            "(Tier A sync validators/mutators and Tier B agent interceptors) on transitions."
        ),
        input_schema=MANAGE_WORKFLOW_INTERCEPTORS_SCHEMA,
        surface=Surface.ADMIN,
        handler=manage_workflow_interceptors,
    )
