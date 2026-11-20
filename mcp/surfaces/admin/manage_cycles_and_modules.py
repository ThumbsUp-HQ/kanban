# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Implementation of the manage_cycles_and_modules MCP tool (S11.4, S7.2, KB-P4-10)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Final

from mcp.context import get_current_mcp_context
from mcp.errors import KbMcpError, McpErrorCode
from mcp.help import build_help
from mcp.registry import Surface, ToolSpec
from mcp.resolver import EntityResolver
from mcp.yaml_out import dump_yaml

if TYPE_CHECKING:
    from mcp.context import McpRequestContext

__all__ = [
    "MANAGE_CYCLES_AND_MODULES_SCHEMA",
    "create_manage_cycles_and_modules_tool",
    "manage_cycles_and_modules",
]

_ALLOWED_TOP_LEVEL_KEYS: Final[frozenset[str]] = frozenset(
    {
        "action",
        "project",
        "cycle",
        "target_cycle",
        "module",
        "view",
        "name",
        "start_date",
        "end_date",
        "view_spec",
        "lod",
        "slug",
        "remote_url",
        "default_ref",
        "access_mode",
        "credential",
        "binding",
        "confirm",
    }
)

MANAGE_CYCLES_AND_MODULES_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": [
                "list_cycles",
                "create_cycle",
                "update_cycle",
                "start_cycle",
                "complete_cycle",
                "rollover",
                "list_modules",
                "create_module",
                "update_module",
                "list_views",
                "create_view",
                "update_view",
                "bind_project_repo",
                "list_repo_bindings",
                "refresh_repo_binding",
                "unbind_project_repo",
                "help",
            ],
            "description": "Operation to perform on cycles, modules, saved views, or repo bindings",
        },
        "project": {
            "type": "string",
            "description": "Project identifier or UUID (required except for help)",
        },
        "cycle": {
            "type": "string",
            "description": "Cycle name or UUID (for update, start, complete, rollover)",
        },
        "target_cycle": {
            "type": "string",
            "description": "Target cycle name or UUID (for rollover destination)",
        },
        "module": {
            "type": "string",
            "description": "Module name or UUID (for update_module)",
        },
        "view": {
            "type": "string",
            "description": "View name or UUID (for update_view)",
        },
        "name": {
            "type": "string",
            "maxLength": 120,
            "description": "Name for new or updated cycle, module, or view",
        },
        "start_date": {
            "type": "string",
            "format": "date",
            "description": "Start date for cycle (YYYY-MM-DD)",
        },
        "end_date": {
            "type": "string",
            "format": "date",
            "description": "End date for cycle (YYYY-MM-DD)",
        },
        "view_spec": {
            "type": "object",
            "description": "View specification containing layout, filters, group_by, sub_group_by",
        },
        "lod": {
            "type": "string",
            "enum": ["summary", "standard", "full"],
            "default": "summary",
            "description": "Level of detail projection ('summary', 'standard', 'full')",
        },
        "slug": {
            "type": "string",
            "description": "Repository binding slug",
        },
        "remote_url": {
            "type": "string",
            "description": "Remote Git URL (https or ssh)",
        },
        "default_ref": {
            "type": "string",
            "default": "main",
            "description": "Default branch or commit ref",
        },
        "access_mode": {
            "type": "string",
            "enum": ["bare_git_tools", "ro_vfs_mount"],
            "description": "Agent repository mount and access mode",
        },
        "credential": {
            "type": "string",
            "description": "Optional deploy key or access token (write-only)",
        },
        "binding": {
            "type": "string",
            "description": "Repository binding slug or UUID identifier",
        },
        "confirm": {
            "type": "boolean",
            "description": "Explicit confirmation for destructive unbind operation",
        },
    },
    "required": ["action"],
    "additionalProperties": False,
}


def _is_uuid(val: str) -> bool:
    try:
        uuid.UUID(val)
    except ValueError:
        return False
    else:
        return True


def _map_cycle_error(exc: KbMcpError) -> KbMcpError:
    code_str = exc.code.value if hasattr(exc.code, "value") else str(exc.code)
    msg = exc.message
    if code_str in ("INVALID_CYCLE_TRANSITION", "INVALID_TRANSITION"):
        valid_opts = ["upcoming", "started", "completed"]
        return KbMcpError(
            McpErrorCode.INVALID_TRANSITION,
            msg,
            field="action",
            valid_options=valid_opts,
            fix_hint=(
                "Cycle state transition must follow monotonicity: "
                "upcoming -> started -> completed"
            ),
            cli_example=(
                'kanban-cli-admin manage_cycles_and_modules --action=update_cycle '
                '--cycle="<id>"'
            ),
        )
    if code_str == "MODULES_DISABLED":
        return KbMcpError(
            McpErrorCode.MODULES_DISABLED,
            msg,
            fix_hint=(
                "Modules are disabled for this project. "
                "Enable modules in project settings first."
            ),
            cli_example='kanban-cli-admin architect_project --action=update --project="<project>"',
        )
    if code_str == "NOT_FOUND":
        return KbMcpError(
            McpErrorCode.NOT_FOUND,
            msg,
            fix_hint="Cycle or module not found. Verify identifier or list project cycles/modules.",
            cli_example=(
                'kanban-cli-admin manage_cycles_and_modules --action=list '
                '--project="<project>"'
            ),
        )
    return exc


async def _resolve_cycle_id(ctx: McpRequestContext, project_ref: str, cycle_ref: str) -> str:
    """Resolve cycle name or UUID to cycle UUID."""
    if _is_uuid(cycle_ref):
        return cycle_ref

    if ctx.client is None:
        raise KbMcpError(McpErrorCode.UPSTREAM_UNAVAILABLE, "Internal API client unavailable")

    cycles_res = await ctx.client.request(
        "GET",
        f"/api/v1/projects/{project_ref}/cycles",
        subject_token=ctx.subject_token,
        mcp_session_id=ctx.session_id,
    )
    if isinstance(cycles_res, list):
        for c in cycles_res:
            if isinstance(c, dict) and c.get("name") == cycle_ref:
                return str(c["id"])
    msg = f"Cycle '{cycle_ref}' not found in project '{project_ref}'"
    raise KbMcpError(McpErrorCode.NOT_FOUND, msg)


async def _resolve_module_id(ctx: McpRequestContext, project_ref: str, module_ref: str) -> str:
    """Resolve module name or UUID to module UUID."""
    if _is_uuid(module_ref):
        return module_ref

    if ctx.client is None:
        raise KbMcpError(McpErrorCode.UPSTREAM_UNAVAILABLE, "Internal API client unavailable")

    mods_res = await ctx.client.request(
        "GET",
        f"/api/v1/projects/{project_ref}/modules",
        subject_token=ctx.subject_token,
        mcp_session_id=ctx.session_id,
    )
    if isinstance(mods_res, list):
        for m in mods_res:
            if isinstance(m, dict) and m.get("name") == module_ref:
                return str(m["id"])
    msg = f"Module '{module_ref}' not found in project '{project_ref}'"
    raise KbMcpError(McpErrorCode.NOT_FOUND, msg)


async def _resolve_view_id(ctx: McpRequestContext, project_ref: str, view_ref: str) -> str:
    """Resolve view name or UUID to view UUID."""
    if _is_uuid(view_ref):
        return view_ref

    if ctx.client is None:
        raise KbMcpError(McpErrorCode.UPSTREAM_UNAVAILABLE, "Internal API client unavailable")

    views_res = await ctx.client.request(
        "GET",
        f"/api/v1/projects/{project_ref}/views",
        subject_token=ctx.subject_token,
        mcp_session_id=ctx.session_id,
    )
    raw_list: list[Any] = []
    if isinstance(views_res, dict):
        raw_list = views_res.get("items") or views_res.get("views") or []
    elif isinstance(views_res, list):
        raw_list = views_res

    for v in raw_list:
        if isinstance(v, dict) and v.get("name") == view_ref:
            return str(v["id"])
    msg = f"View '{view_ref}' not found in project '{project_ref}'"
    raise KbMcpError(McpErrorCode.NOT_FOUND, msg)


async def manage_cycles_and_modules(arguments: dict[str, Any]) -> str:  # noqa: C901, PLR0911, PLR0912, PLR0915
    """Manage cycles lifecycle, project modules, and saved views."""
    for key in arguments:
        if key not in _ALLOWED_TOP_LEVEL_KEYS:
            msg = f"Unknown parameter '{key}'. Allowed: {sorted(_ALLOWED_TOP_LEVEL_KEYS)}"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    action = arguments.get("action")
    if not action:
        msg = "action parameter is required"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if action == "help":
        help_doc = await build_help(
            "manage_cycles_and_modules",
            params_summary={
                "action": (
                    "list_cycles | create_cycle | update_cycle | start_cycle | complete_cycle | "
                    "rollover | list_modules | create_module | update_module | list_views | "
                    "create_view | update_view | help"
                ),
                "project": "string (project identifier or UUID)",
                "cycle": "string (cycle name or UUID)",
                "target_cycle": "string (target cycle name or UUID)",
                "module": "string (module name or UUID)",
                "view": "string (view name or UUID)",
                "name": "string (1..120 characters)",
                "start_date / end_date": "string (YYYY-MM-DD)",
                "view_spec": "object (layout, filters, group_by, sub_group_by)",
            },
        )
        return dump_yaml(help_doc)

    raw_project = arguments.get("project")
    project_ref: str = ""
    if raw_project and isinstance(raw_project, str) and raw_project.strip():
        project_ref = raw_project.strip()
    elif (
        action in ("refresh_repo_binding", "unbind_project_repo")
        and arguments.get("binding")
        and _is_uuid(str(arguments.get("binding")))
    ):
        project_ref = ""
    else:
        msg = "project parameter is required"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    ctx = get_current_mcp_context()
    if ctx is None or ctx.client is None:
        msg = "Internal API client unavailable"
        raise KbMcpError(McpErrorCode.UPSTREAM_UNAVAILABLE, msg)

    # Scopes authorization check
    if ctx.caller_scopes is not None:
        if action.startswith("list_"):
            if not any(
                s in ctx.caller_scopes for s in ("admin:read", "admin:write", "admin:destructive")
            ):
                msg = f"Action '{action}' requires 'admin:read' scope"
                raise KbMcpError(McpErrorCode.INSUFFICIENT_SCOPE, msg)
        elif not any(s in ctx.caller_scopes for s in ("admin:write", "admin:destructive")):
            msg = f"Action '{action}' requires 'admin:write' scope"
            raise KbMcpError(McpErrorCode.INSUFFICIENT_SCOPE, msg)

    lod = arguments.get("lod", "summary")

    # -------------------------------------------------------------------------
    # Cycles Actions
    # -------------------------------------------------------------------------
    if action == "list_cycles":
        try:
            res = await ctx.client.request(
                "GET",
                f"/api/v1/projects/{project_ref}/cycles",
                subject_token=ctx.subject_token,
                mcp_session_id=ctx.session_id,
            )
        except KbMcpError as exc:
            raise _map_cycle_error(exc) from exc

        if not isinstance(res, list):
            msg = "Unexpected response from list cycles API"
            raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

        if lod == "full":
            return dump_yaml({"cycles": res})

        summary_cycles = [
            {
                "id": str(c.get("id")),
                "name": c.get("name"),
                "status": c.get("status"),
                "start_date": c.get("start_date"),
                "end_date": c.get("end_date"),
                "issue_count": c.get("issue_count", 0),
            }
            for c in res
            if isinstance(c, dict)
        ]
        return dump_yaml({"cycles": summary_cycles})

    if action == "create_cycle":
        name = arguments.get("name")
        if not name or not isinstance(name, str) or not name.strip():
            msg = "name parameter is required for create_cycle"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        payload: dict[str, Any] = {"name": name.strip()}
        if arguments.get("start_date"):
            payload["start_date"] = arguments["start_date"]
        if arguments.get("end_date"):
            payload["end_date"] = arguments["end_date"]

        try:
            res = await ctx.client.request(
                "POST",
                f"/api/v1/projects/{project_ref}/cycles",
                json_data=payload,
                subject_token=ctx.subject_token,
                mcp_session_id=ctx.session_id,
            )
        except KbMcpError as exc:
            raise _map_cycle_error(exc) from exc

        return dump_yaml(res)

    if action == "update_cycle":
        cycle_ref = arguments.get("cycle")
        if not cycle_ref or not isinstance(cycle_ref, str) or not cycle_ref.strip():
            msg = "cycle parameter is required for update_cycle"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        cycle_id = await _resolve_cycle_id(ctx, project_ref, cycle_ref.strip())
        patch_payload: dict[str, Any] = {}
        if arguments.get("name"):
            patch_payload["name"] = arguments["name"].strip()
        if "start_date" in arguments:
            patch_payload["start_date"] = arguments["start_date"]
        if "end_date" in arguments:
            patch_payload["end_date"] = arguments["end_date"]

        try:
            res = await ctx.client.request(
                "PATCH",
                f"/api/v1/cycles/{cycle_id}",
                json_data=patch_payload,
                subject_token=ctx.subject_token,
                mcp_session_id=ctx.session_id,
            )
        except KbMcpError as exc:
            raise _map_cycle_error(exc) from exc

        return dump_yaml(res)

    if action == "start_cycle":
        cycle_ref = arguments.get("cycle")
        if not cycle_ref or not isinstance(cycle_ref, str) or not cycle_ref.strip():
            msg = "cycle parameter is required for start_cycle"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        cycle_id = await _resolve_cycle_id(ctx, project_ref, cycle_ref.strip())
        try:
            res = await ctx.client.request(
                "POST",
                f"/api/v1/cycles/{cycle_id}/start",
                subject_token=ctx.subject_token,
                mcp_session_id=ctx.session_id,
            )
        except KbMcpError as exc:
            raise _map_cycle_error(exc) from exc

        return dump_yaml(res)

    if action == "complete_cycle":
        cycle_ref = arguments.get("cycle")
        if not cycle_ref or not isinstance(cycle_ref, str) or not cycle_ref.strip():
            msg = "cycle parameter is required for complete_cycle"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        cycle_id = await _resolve_cycle_id(ctx, project_ref, cycle_ref.strip())
        complete_payload: dict[str, Any] = {}
        target_ref = arguments.get("target_cycle")
        if target_ref and isinstance(target_ref, str) and target_ref.strip():
            target_id = await _resolve_cycle_id(ctx, project_ref, target_ref.strip())
            complete_payload["rollover_to_cycle_id"] = target_id

        try:
            res = await ctx.client.request(
                "POST",
                f"/api/v1/cycles/{cycle_id}/complete",
                json_data=complete_payload,
                subject_token=ctx.subject_token,
                mcp_session_id=ctx.session_id,
            )
        except KbMcpError as exc:
            raise _map_cycle_error(exc) from exc

        return dump_yaml(res)

    if action == "rollover":
        cycle_ref = arguments.get("cycle")
        if not cycle_ref or not isinstance(cycle_ref, str) or not cycle_ref.strip():
            msg = "cycle parameter is required for rollover"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        target_ref = arguments.get("target_cycle")
        if not target_ref or not isinstance(target_ref, str) or not target_ref.strip():
            msg = "target_cycle parameter is required for rollover"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        cycle_id = await _resolve_cycle_id(ctx, project_ref, cycle_ref.strip())
        target_id = await _resolve_cycle_id(ctx, project_ref, target_ref.strip())

        try:
            res = await ctx.client.request(
                "POST",
                f"/api/v1/cycles/{cycle_id}/rollover",
                json_data={"target_cycle_id": target_id},
                subject_token=ctx.subject_token,
                mcp_session_id=ctx.session_id,
            )
        except KbMcpError as exc:
            raise _map_cycle_error(exc) from exc

        if not isinstance(res, dict):
            msg = "Unexpected response from cycle rollover API"
            raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

        summary_rollover = {
            "status": "rolled_over",
            "from": res.get("from_cycle", cycle_ref),
            "to": res.get("to_cycle", target_ref),
            "moved": res.get("moved", 0),
        }
        return dump_yaml(summary_rollover)

    # -------------------------------------------------------------------------
    # Modules Actions
    # -------------------------------------------------------------------------
    if action == "list_modules":
        try:
            res = await ctx.client.request(
                "GET",
                f"/api/v1/projects/{project_ref}/modules",
                subject_token=ctx.subject_token,
                mcp_session_id=ctx.session_id,
            )
        except KbMcpError as exc:
            raise _map_cycle_error(exc) from exc

        if not isinstance(res, list):
            msg = "Unexpected response from list modules API"
            raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

        if lod == "full":
            return dump_yaml({"modules": res})

        summary_modules = [
            {
                "id": str(m.get("id")),
                "name": m.get("name"),
                "status": m.get("status"),
            }
            for m in res
            if isinstance(m, dict)
        ]
        return dump_yaml({"modules": summary_modules})

    if action == "create_module":
        name = arguments.get("name")
        if not name or not isinstance(name, str) or not name.strip():
            msg = "name parameter is required for create_module"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        try:
            res = await ctx.client.request(
                "POST",
                f"/api/v1/projects/{project_ref}/modules",
                json_data={"name": name.strip()},
                subject_token=ctx.subject_token,
                mcp_session_id=ctx.session_id,
            )
        except KbMcpError as exc:
            raise _map_cycle_error(exc) from exc

        return dump_yaml(res)

    if action == "update_module":
        module_ref = arguments.get("module")
        if not module_ref or not isinstance(module_ref, str) or not module_ref.strip():
            msg = "module parameter is required for update_module"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        name = arguments.get("name")
        patch_mod: dict[str, Any] = {}
        if name and isinstance(name, str) and name.strip():
            patch_mod["name"] = name.strip()

        module_id = await _resolve_module_id(ctx, project_ref, module_ref.strip())
        try:
            res = await ctx.client.request(
                "PATCH",
                f"/api/v1/modules/{module_id}",
                json_data=patch_mod,
                subject_token=ctx.subject_token,
                mcp_session_id=ctx.session_id,
            )
        except KbMcpError as exc:
            raise _map_cycle_error(exc) from exc

        return dump_yaml(res)

    # -------------------------------------------------------------------------
    # Views Actions
    # -------------------------------------------------------------------------
    if action == "list_views":
        try:
            res = await ctx.client.request(
                "GET",
                f"/api/v1/projects/{project_ref}/views",
                subject_token=ctx.subject_token,
                mcp_session_id=ctx.session_id,
            )
        except KbMcpError as exc:
            raise _map_cycle_error(exc) from exc

        raw_items = (
            res.get("items", [])
            if isinstance(res, dict)
            else (res if isinstance(res, list) else [])
        )
        if lod == "full":
            return dump_yaml({"views": raw_items})

        summary_views = [
            {
                "id": str(v.get("id")),
                "name": v.get("name"),
                "layout": v.get("layout"),
                "group_by": v.get("group_by"),
            }
            for v in raw_items
            if isinstance(v, dict)
        ]
        return dump_yaml({"views": summary_views})

    if action == "create_view":
        name = arguments.get("name")
        if not name or not isinstance(name, str) or not name.strip():
            msg = "name parameter is required for create_view"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        view_create_payload: dict[str, Any] = {"name": name.strip()}
        view_spec = arguments.get("view_spec")
        if isinstance(view_spec, dict):
            for k in ("layout", "group_by", "sub_group_by", "filters", "filters_json"):
                if k in view_spec:
                    if k == "filters_json" and "filters" not in view_spec:
                        view_create_payload["filters"] = view_spec[k]
                    else:
                        view_create_payload[k] = view_spec[k]

        try:
            res = await ctx.client.request(
                "POST",
                f"/api/v1/projects/{project_ref}/views",
                json_data=view_create_payload,
                subject_token=ctx.subject_token,
                mcp_session_id=ctx.session_id,
            )
        except KbMcpError as exc:
            raise _map_cycle_error(exc) from exc

        return dump_yaml(res)

    if action == "update_view":
        view_ref = arguments.get("view")
        if not view_ref or not isinstance(view_ref, str) or not view_ref.strip():
            msg = "view parameter is required for update_view"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        view_id = await _resolve_view_id(ctx, project_ref, view_ref.strip())
        view_patch_payload: dict[str, Any] = {}
        if arguments.get("name"):
            view_patch_payload["name"] = arguments["name"].strip()
        view_spec = arguments.get("view_spec")
        if isinstance(view_spec, dict):
            for k in ("layout", "group_by", "sub_group_by", "filters", "filters_json"):
                if k in view_spec:
                    if k == "filters_json" and "filters" not in view_spec:
                        view_patch_payload["filters"] = view_spec[k]
                    else:
                        view_patch_payload[k] = view_spec[k]

        try:
            res = await ctx.client.request(
                "PATCH",
                f"/api/v1/views/{view_id}",
                json_data=view_patch_payload,
                subject_token=ctx.subject_token,
                mcp_session_id=ctx.session_id,
            )
        except KbMcpError as exc:
            raise _map_cycle_error(exc) from exc

        return dump_yaml(res)

    # -------------------------------------------------------------------------
    # Repo Bindings Actions (KB-P5-19b)
    # -------------------------------------------------------------------------
    if action == "bind_project_repo":
        slug = arguments.get("slug")
        remote_url = arguments.get("remote_url")
        access_mode = arguments.get("access_mode")
        if not slug or not remote_url or not access_mode:
            msg = "slug, remote_url, and access_mode parameters are required for bind_project_repo"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        resolver = EntityResolver(
            ctx.client, subject_token=ctx.subject_token, mcp_session_id=ctx.session_id
        )
        resolved_proj = await resolver.resolve("project", project_ref)
        proj_key = resolved_proj.key

        bind_payload: dict[str, Any] = {
            "slug": slug,
            "remote_url": remote_url,
            "default_ref": arguments.get("default_ref", "main"),
            "access_mode": access_mode,
        }
        if arguments.get("credential"):
            bind_payload["credential"] = arguments["credential"]

        res = await ctx.client.request(
            "POST",
            f"/api/v1/projects/{proj_key}/repo-bindings",
            json_data=bind_payload,
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        return dump_yaml({"status": "created", "repo_binding": res})

    if action == "list_repo_bindings":
        resolver = EntityResolver(
            ctx.client, subject_token=ctx.subject_token, mcp_session_id=ctx.session_id
        )
        resolved_proj = await resolver.resolve("project", project_ref)
        proj_key = resolved_proj.key

        res = await ctx.client.request(
            "GET",
            f"/api/v1/projects/{proj_key}/repo-bindings",
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        if not isinstance(res, list):
            msg = "Unexpected response from list repo bindings API"
            raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

        if lod == "full":
            return dump_yaml({"repo_bindings": res})

        summary_bindings = [
            {
                "id": str(b.get("id")),
                "slug": b.get("slug"),
                "remote_url": b.get("remote_url"),
                "access_mode": b.get("access_mode"),
                "default_ref": b.get("default_ref"),
                "last_fetched_commit": b.get("last_fetched_commit"),
            }
            for b in res
            if isinstance(b, dict)
        ]
        return dump_yaml({"repo_bindings": summary_bindings})

    if action == "refresh_repo_binding":
        binding_ref = arguments.get("binding") or arguments.get("slug")
        if not binding_ref:
            msg = "binding parameter is required for refresh_repo_binding"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        if _is_uuid(str(binding_ref)):
            binding_id = str(binding_ref)
        else:
            if not project_ref:
                msg = "project parameter is required to resolve repo binding by slug"
                raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
            resolver = EntityResolver(
                ctx.client, subject_token=ctx.subject_token, mcp_session_id=ctx.session_id
            )
            resolved = await resolver.resolve("repo_binding", str(binding_ref), project=project_ref)
            binding_id = str(resolved.id)

        res = await ctx.client.request(
            "POST",
            f"/api/v1/repo-bindings/{binding_id}/refresh",
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        return dump_yaml({"status": "refreshed", "repo_binding": res})

    if action == "unbind_project_repo":
        binding_ref = arguments.get("binding") or arguments.get("slug")
        if not binding_ref:
            msg = "binding parameter is required for unbind_project_repo"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        if _is_uuid(str(binding_ref)):
            binding_id = str(binding_ref)
        else:
            if not project_ref:
                msg = "project parameter is required to resolve repo binding by slug"
                raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
            resolver = EntityResolver(
                ctx.client, subject_token=ctx.subject_token, mcp_session_id=ctx.session_id
            )
            resolved = await resolver.resolve("repo_binding", str(binding_ref), project=project_ref)
            binding_id = str(resolved.id)

        confirm = arguments.get("confirm", False)
        if not confirm:
            return dump_yaml(
                {
                    "status": "confirmation_required",
                    "warning": "Unbinding repository requires explicit confirm: true parameter",
                    "binding_id": binding_id,
                    "project": project_ref,
                }
            )

        await ctx.client.request(
            "DELETE",
            f"/api/v1/repo-bindings/{binding_id}",
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        return dump_yaml({"status": "deleted", "binding_id": binding_id, "project": project_ref})

    msg = f"Unsupported action '{action}'"
    raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)


def create_manage_cycles_and_modules_tool() -> ToolSpec:
    """Construct ToolSpec for manage_cycles_and_modules."""
    return ToolSpec(
        name="manage_cycles_and_modules",
        description=(
            "Manage project cycles, iteration rollover, project modules, and saved views."
        ),
        input_schema=MANAGE_CYCLES_AND_MODULES_SCHEMA,
        surface=Surface.ADMIN,
        handler=manage_cycles_and_modules,
    )
