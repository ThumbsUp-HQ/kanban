# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Implementation of the configure_workspace MCP tool (S11.4, S4.1, S10.2, KB-P4-09a)."""

from __future__ import annotations

from typing import Any, Final

from mcp.context import get_current_mcp_context
from mcp.errors import KbMcpError, McpErrorCode
from mcp.help import build_help
from mcp.registry import Surface, ToolSpec
from mcp.yaml_out import dump_yaml

__all__ = [
    "CONFIGURE_WORKSPACE_SCHEMA",
    "configure_workspace",
    "create_configure_workspace_tool",
]

_ALLOWED_TOP_LEVEL_KEYS: Final[frozenset[str]] = frozenset({"action", "settings", "lod"})

_ALLOWED_SETTING_KEYS: Final[frozenset[str]] = frozenset(
    {
        "display_name",
        "default_project_visibility",
        "session_idle_timeout_min",
        "session_absolute_timeout_min",
        "trash_retention_days",
        "mcp_key_max_ttl_days",
        "air_gap_mode",
    }
)

_MAX_DISPLAY_NAME_LEN: Final[int] = 80
_MIN_IDLE_MIN: Final[int] = 5
_MAX_IDLE_MIN: Final[int] = 720
_MIN_ABS_MIN: Final[int] = 60
_MAX_ABS_MIN: Final[int] = 10080
_MIN_RETENTION_DAYS: Final[int] = 1
_MAX_RETENTION_DAYS: Final[int] = 365
_AAL2_LEVEL: Final[int] = 2

CONFIGURE_WORKSPACE_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["get", "update", "help"],
            "description": "Operation to perform: 'get', 'update', or 'help'",
        },
        "settings": {
            "type": "object",
            "properties": {
                "display_name": {
                    "type": "string",
                    "description": "Workspace display name (1..80 characters)",
                },
                "default_project_visibility": {
                    "type": "string",
                    "enum": ["private", "workspace"],
                    "description": "Default visibility for newly created projects",
                },
                "session_idle_timeout_min": {
                    "type": "integer",
                    "minimum": 5,
                    "maximum": 720,
                    "description": "Session idle timeout in minutes (5..720)",
                },
                "session_absolute_timeout_min": {
                    "type": "integer",
                    "minimum": 60,
                    "maximum": 10080,
                    "description": "Session absolute timeout in minutes (60..10080)",
                },
                "trash_retention_days": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 365,
                    "description": "Retention window for soft-deleted items in days (1..365)",
                },
                "mcp_key_max_ttl_days": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 365,
                    "description": "Maximum TTL cap for newly minted MCP keys in days (1..365)",
                },
                "air_gap_mode": {
                    "type": "boolean",
                    "description": "Air-gap mode disabling outbound network egress (requires AAL2)",
                },
            },
            "additionalProperties": False,
            "description": "Settings fields to update (required for action 'update')",
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


def _validate_settings_payload(settings: dict[str, Any]) -> None:  # noqa: C901, PLR0912
    """Validate setting fields and check boundary ranges."""
    for key in settings:
        if key not in _ALLOWED_SETTING_KEYS:
            msg = f"Unknown setting key '{key}'. Allowed: {sorted(_ALLOWED_SETTING_KEYS)}"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if "display_name" in settings:
        name = settings["display_name"]
        if not isinstance(name, str) or not (1 <= len(name) <= _MAX_DISPLAY_NAME_LEN):
            msg = f"display_name must be a string between 1 and {_MAX_DISPLAY_NAME_LEN} characters"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if "default_project_visibility" in settings:
        vis = settings["default_project_visibility"]
        if vis not in ("private", "workspace"):
            msg = "default_project_visibility must be 'private' or 'workspace'"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if "session_idle_timeout_min" in settings:
        idle = settings["session_idle_timeout_min"]
        if (
            not isinstance(idle, int)
            or isinstance(idle, bool)
            or not (_MIN_IDLE_MIN <= idle <= _MAX_IDLE_MIN)
        ):
            msg = (
                f"session_idle_timeout_min must be an integer between "
                f"{_MIN_IDLE_MIN} and {_MAX_IDLE_MIN}"
            )
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if "session_absolute_timeout_min" in settings:
        abs_val = settings["session_absolute_timeout_min"]
        if (
            not isinstance(abs_val, int)
            or isinstance(abs_val, bool)
            or not (_MIN_ABS_MIN <= abs_val <= _MAX_ABS_MIN)
        ):
            msg = (
                f"session_absolute_timeout_min must be an integer between "
                f"{_MIN_ABS_MIN} and {_MAX_ABS_MIN}"
            )
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if (
        "session_idle_timeout_min" in settings
        and "session_absolute_timeout_min" in settings
        and settings["session_absolute_timeout_min"] < settings["session_idle_timeout_min"]
    ):
        msg = "session_absolute_timeout_min must be >= session_idle_timeout_min"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if "trash_retention_days" in settings:
        ret = settings["trash_retention_days"]
        if (
            not isinstance(ret, int)
            or isinstance(ret, bool)
            or not (_MIN_RETENTION_DAYS <= ret <= _MAX_RETENTION_DAYS)
        ):
            msg = (
                f"trash_retention_days must be an integer between "
                f"{_MIN_RETENTION_DAYS} and {_MAX_RETENTION_DAYS}"
            )
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if "mcp_key_max_ttl_days" in settings:
        ttl = settings["mcp_key_max_ttl_days"]
        if (
            not isinstance(ttl, int)
            or isinstance(ttl, bool)
            or not (_MIN_RETENTION_DAYS <= ttl <= _MAX_RETENTION_DAYS)
        ):
            msg = (
                f"mcp_key_max_ttl_days must be an integer between "
                f"{_MIN_RETENTION_DAYS} and {_MAX_RETENTION_DAYS}"
            )
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if "air_gap_mode" in settings and not isinstance(settings["air_gap_mode"], bool):
        msg = "air_gap_mode must be a boolean"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)


async def configure_workspace(arguments: dict[str, Any]) -> str:  # noqa: C901, PLR0912
    """Read or update workspace security defaults, timeouts, retention, and air-gap mode."""
    # Check top-level parameter names
    for key in arguments:
        if key not in _ALLOWED_TOP_LEVEL_KEYS:
            msg = f"Unknown parameter '{key}'. Allowed: {sorted(_ALLOWED_TOP_LEVEL_KEYS)}"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    action = arguments.get("action")
    if not action or action not in ("get", "update", "help"):
        msg = "action must be one of 'get', 'update', or 'help'"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if action == "help":
        help_doc = await build_help(
            "configure_workspace",
            params_summary={
                "action": "get | update | help",
                "settings": "object",
            },
        )
        return dump_yaml(help_doc)

    ctx = get_current_mcp_context()
    if ctx is None or ctx.client is None:
        msg = "Internal API client unavailable"
        raise KbMcpError(McpErrorCode.UPSTREAM_UNAVAILABLE, msg)

    # Scope authorization checks
    if ctx.caller_scopes is not None:
        if action == "get":
            if not any(
                s in ctx.caller_scopes for s in ("admin:read", "admin:write", "admin:destructive")
            ):
                msg = "Action 'get' requires 'admin:read' scope"
                raise KbMcpError(McpErrorCode.INSUFFICIENT_SCOPE, msg)
        elif not any(s in ctx.caller_scopes for s in ("admin:write", "admin:destructive")):
            msg = "Action 'update' requires 'admin:write' scope"
            raise KbMcpError(McpErrorCode.INSUFFICIENT_SCOPE, msg)

    if action == "get":
        res = await ctx.client.request(
            "GET",
            "/api/v1/admin/workspace-settings",
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
    else:
        raw_settings = arguments.get("settings")
        if not isinstance(raw_settings, dict) or not raw_settings:
            msg = "settings dictionary is required for action 'update'"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        _validate_settings_payload(raw_settings)

        # AAL2 check for toggling air_gap_mode
        if "air_gap_mode" in raw_settings and ctx.aal_level < _AAL2_LEVEL:
            msg = "Toggling air_gap_mode requires session/token AAL2"
            raise KbMcpError(McpErrorCode.AAL2_REQUIRED, msg)

        res = await ctx.client.request(
            "PATCH",
            "/api/v1/admin/workspace-settings",
            json_data=raw_settings,
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )

    if not isinstance(res, dict):
        msg = "Unexpected response from workspace settings API"
        raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

    lod = arguments.get("lod", "summary")
    if lod == "full":
        return dump_yaml(res)

    # Standard / Summary projection conforming to S11.4 Action 3
    summary_data = {
        "workspace": res.get("display_name"),
        "air_gap_mode": res.get("air_gap_mode", False),
        "trash_retention_days": res.get("trash_retention_days", 30),
        "session": {
            "idle_min": res.get("session_idle_timeout_min", 60),
            "absolute_min": res.get("session_absolute_timeout_min", 720),
        },
        "mcp_key_max_ttl_days": res.get("mcp_key_max_ttl_days", 90),
    }
    return dump_yaml(summary_data)


def create_configure_workspace_tool() -> ToolSpec:
    """Construct ToolSpec for configure_workspace."""
    return ToolSpec(
        name="configure_workspace",
        description=(
            "Read and update workspace branding, security defaults, "
            "retention windows, and air_gap_mode."
        ),
        input_schema=CONFIGURE_WORKSPACE_SCHEMA,
        surface=Surface.ADMIN,
        handler=configure_workspace,
    )
