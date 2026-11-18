# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Implementation of the architect_project MCP tool (S11.4, S7.2, S12.2, KB-P4-10)."""

from __future__ import annotations

from typing import Any, Final

from mcp.context import get_current_mcp_context
from mcp.errors import KbMcpError, McpErrorCode
from mcp.help import build_help
from mcp.registry import Surface, ToolSpec
from mcp.yaml_out import dump_yaml

__all__ = [
    "ARCHITECT_PROJECT_SCHEMA",
    "architect_project",
    "create_architect_project_tool",
]

_ALLOWED_TOP_LEVEL_KEYS: Final[frozenset[str]] = frozenset(
    {"action", "project", "project_key", "blueprint", "plan_sha256", "lod"}
)

ARCHITECT_PROJECT_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["get", "plan", "apply", "help"],
            "description": "Blueprint operation: 'get', 'plan', 'apply', or 'help'",
        },
        "project": {
            "type": "string",
            "description": "Project identifier or UUID (required for get)",
        },
        "project_key": {
            "type": "string",
            "description": "Alias for project identifier or UUID",
        },
        "blueprint": {
            "type": "object",
            "description": "Declarative ProjectBlueprint payload (required for plan and apply)",
        },
        "plan_sha256": {
            "type": "string",
            "description": "Hash of the plan returned by action 'plan' (required for apply)",
        },
        "lod": {
            "type": "string",
            "enum": ["summary", "standard", "full"],
            "default": "summary",
            "description": "Level of detail projection ('summary', 'standard', 'full')",
        },
    },
    "required": ["action"],
    "additionalProperties": False,
}


def _map_api_error_to_mcp_error(exc: KbMcpError) -> KbMcpError:
    """Map ProblemException error codes returned via HTTP client to McpErrorCode."""
    code_str = exc.code.value if hasattr(exc.code, "value") else str(exc.code)
    msg = exc.message

    if code_str == "PLAN_STALE":
        return KbMcpError(McpErrorCode.PLAN_STALE, msg)
    if code_str == "STATE_IN_USE":
        hint = 'Specify state_migrations: {"Old State": "New State"}'
        return KbMcpError(McpErrorCode.STATE_IN_USE, msg, hint=hint)
    if code_str == "PRIORITY_IN_USE":
        return KbMcpError(McpErrorCode.PRIORITY_IN_USE, msg)
    if code_str in ("VALIDATION_FAILED", "INSUFFICIENT_CAPABILITY", "INVALID_WIP_LIMITS"):
        return KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
    if code_str == "NOT_FOUND":
        return KbMcpError(McpErrorCode.NOT_FOUND, msg)
    return exc


async def architect_project(arguments: dict[str, Any]) -> str:  # noqa: C901, PLR0912, PLR0915
    """Execute declarative blueprint planning and application for project lifecycle."""
    # Top-level key validation
    for key in arguments:
        if key not in _ALLOWED_TOP_LEVEL_KEYS:
            msg = f"Unknown parameter '{key}'. Allowed: {sorted(_ALLOWED_TOP_LEVEL_KEYS)}"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    action = arguments.get("action")
    if not action or action not in ("get", "plan", "apply", "help"):
        msg = "action must be one of 'get', 'plan', 'apply', or 'help'"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if action == "help":
        help_doc = await build_help(
            "architect_project",
            params_summary={
                "action": "get | plan | apply | help",
                "project": "string (project identifier or UUID)",
                "blueprint": "object (ProjectBlueprint specification)",
                "plan_sha256": "string (hash from plan action)",
            },
        )
        return dump_yaml(help_doc)

    ctx = get_current_mcp_context()
    if ctx is None or ctx.client is None:
        msg = "Internal API client unavailable"
        raise KbMcpError(McpErrorCode.UPSTREAM_UNAVAILABLE, msg)

    # Scopes authorization check
    if ctx.caller_scopes is not None:
        if action == "get":
            if not any(
                s in ctx.caller_scopes for s in ("admin:read", "admin:write", "admin:destructive")
            ):
                msg = "Action 'get' requires 'admin:read' scope"
                raise KbMcpError(McpErrorCode.INSUFFICIENT_SCOPE, msg)
        elif not any(s in ctx.caller_scopes for s in ("admin:write", "admin:destructive")):
            msg = f"Action '{action}' requires 'admin:write' scope"
            raise KbMcpError(McpErrorCode.INSUFFICIENT_SCOPE, msg)

    lod = arguments.get("lod", "summary")

    if action == "get":
        project_ref = arguments.get("project") or arguments.get("project_key")
        if not project_ref or not isinstance(project_ref, str) or not project_ref.strip():
            msg = "project parameter is required for action 'get'"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        try:
            res = await ctx.client.request(
                "GET",
                f"/api/v1/admin/projects/{project_ref.strip()}/blueprint",
                subject_token=ctx.subject_token,
                mcp_session_id=ctx.session_id,
            )
        except KbMcpError as exc:
            raise _map_api_error_to_mcp_error(exc) from exc

        if not isinstance(res, dict):
            msg = "Unexpected response from project blueprint API"
            raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

        return dump_yaml(res)

    if action == "plan":
        raw_bp = arguments.get("blueprint")
        if not isinstance(raw_bp, dict) or not raw_bp:
            msg = "blueprint dictionary is required for action 'plan'"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        try:
            res = await ctx.client.request(
                "POST",
                "/api/v1/admin/projects/blueprint:plan",
                json_data={"blueprint": raw_bp},
                subject_token=ctx.subject_token,
                mcp_session_id=ctx.session_id,
            )
        except KbMcpError as exc:
            raise _map_api_error_to_mcp_error(exc) from exc

        if not isinstance(res, dict):
            msg = "Unexpected response from blueprint plan API"
            raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

        if lod == "full":
            return dump_yaml(res)

        summary_plan = {
            "project": res.get("project"),
            "plan_sha256": res.get("plan_sha256"),
            "changes": res.get("changes", {}),
        }
        return dump_yaml(summary_plan)

    raw_bp = arguments.get("blueprint")
    if not isinstance(raw_bp, dict) or not raw_bp:
        msg = "blueprint dictionary is required for action 'apply'"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    plan_sha256 = arguments.get("plan_sha256")
    if not plan_sha256 or not isinstance(plan_sha256, str) or not plan_sha256.strip():
        msg = "plan_sha256 string is required for action 'apply'"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    try:
        res = await ctx.client.request(
            "POST",
            "/api/v1/admin/projects/blueprint:apply",
            json_data={
                "blueprint": raw_bp,
                "plan_sha256": plan_sha256.strip(),
            },
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
    except KbMcpError as exc:
        raise _map_api_error_to_mcp_error(exc) from exc

    if not isinstance(res, dict):
        msg = "Unexpected response from blueprint apply API"
        raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

    return dump_yaml(res)


def create_architect_project_tool() -> ToolSpec:
    """Construct ToolSpec for architect_project."""
    return ToolSpec(
        name="architect_project",
        description=(
            "Declarative project blueprint engine: read current configuration, "
            "compute reviewable diff plans, and apply configurations atomically."
        ),
        input_schema=ARCHITECT_PROJECT_SCHEMA,
        surface=Surface.ADMIN,
        handler=architect_project,
    )
