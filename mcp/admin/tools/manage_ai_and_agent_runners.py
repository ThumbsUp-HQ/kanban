# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Implementation of the manage_ai_and_agent_runners MCP tool (KB-P5-05b, S10.2, S11.4)."""

from __future__ import annotations

from typing import Any, Final

from mcp.context import get_current_mcp_context
from mcp.errors import KbMcpError, McpErrorCode
from mcp.help import build_help
from mcp.registry import Surface, ToolSpec
from mcp.yaml_out import dump_yaml

__all__ = [
    "MANAGE_AI_AND_AGENT_RUNNERS_SCHEMA",
    "create_manage_ai_and_agent_runners_tool",
    "manage_ai_and_agent_runners",
]

_ALLOWED_TOP_LEVEL_KEYS: Final[frozenset[str]] = frozenset(
    {
        "action",
        "id",
        "provider_kind",
        "display_name",
        "base_url",
        "model_allowlist",
        "residency_tier",
        "priority",
        "settings",
        "api_key",
        "is_enabled",
        "project_id",
        "provider_config_id",
        "period_kind",
        "token_cap",
        "lod",
    }
)

_VALID_ACTIONS: Final[frozenset[str]] = frozenset(
    {
        "list_providers",
        "upsert_provider",
        "disable_provider",
        "set_budget",
        "get_budget_usage",
        "upsert_agent_definition",
        "list_agent_definitions",
        "mint_runner_enrollment_token",
        "help",
    }
)

_DEFERRED_ACTIONS: Final[frozenset[str]] = frozenset(
    {
        "upsert_agent_definition",
        "list_agent_definitions",
        "mint_runner_enrollment_token",
    }
)

MANAGE_AI_AND_AGENT_RUNNERS_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": [
                "list_providers",
                "upsert_provider",
                "disable_provider",
                "set_budget",
                "get_budget_usage",
                "upsert_agent_definition",
                "list_agent_definitions",
                "mint_runner_enrollment_token",
                "help",
            ],
            "description": "Operation to perform on AI providers, budgets, or agent runners",
        },
        "id": {
            "type": "string",
            "description": "Provider configuration UUID (for update or disable)",
        },
        "provider_kind": {
            "type": "string",
            "enum": ["openai", "ollama", "gemini", "fixture"],
            "description": "AI provider backend type",
        },
        "display_name": {
            "type": "string",
            "description": "Human-readable provider configuration label",
        },
        "base_url": {
            "type": "string",
            "description": "Base URL for provider API endpoint (HTTPS or loopback)",
        },
        "model_allowlist": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Allowed model names for this provider",
        },
        "residency_tier": {
            "type": "string",
            "description": "Data residency classification (default, eu, etc.)",
        },
        "priority": {
            "type": "integer",
            "description": "Provider priority rank (lower numbers selected first)",
        },
        "settings": {
            "type": "object",
            "description": "Additional provider-specific settings",
        },
        "api_key": {
            "type": "string",
            "description": "Write-only API key credential (never echoed in responses)",
        },
        "is_enabled": {
            "type": "boolean",
            "description": "Whether this provider configuration is enabled",
        },
        "project_id": {
            "type": "string",
            "description": "Optional project UUID for project-scoped provider configuration",
        },
        "provider_config_id": {
            "type": "string",
            "description": "Provider configuration UUID (for budget operations)",
        },
        "period_kind": {
            "type": "string",
            "enum": ["daily", "monthly"],
            "description": "Budget period type ('daily' or 'monthly')",
        },
        "token_cap": {
            "type": "integer",
            "minimum": 0,
            "maximum": 10000000000,
            "description": "Maximum token budget cap (0..10000000000)",
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


def _project_provider(p: dict[str, Any], lod: str) -> dict[str, Any]:
    """Project provider config dictionary according to requested LOD."""
    if lod == "full":
        return p
    if lod == "standard":
        return {
            "id": p.get("id"),
            "provider_kind": p.get("provider_kind"),
            "display_name": p.get("display_name"),
            "base_url": p.get("base_url"),
            "model_allowlist": p.get("model_allowlist"),
            "residency_tier": p.get("residency_tier"),
            "priority": p.get("priority"),
            "is_enabled": p.get("is_enabled"),
            "api_key_set": p.get("api_key_set"),
            "project_id": p.get("project_id"),
        }
    # summary
    return {
        "id": p.get("id"),
        "provider_kind": p.get("provider_kind"),
        "display_name": p.get("display_name"),
        "is_enabled": p.get("is_enabled"),
        "api_key_set": p.get("api_key_set"),
    }


def _project_budget(rows: list[dict[str, Any]], lod: str) -> Any:  # noqa: ANN401
    """Project budget usage rows according to requested LOD."""
    if lod in ("standard", "full"):
        return rows
    # summary: dense operational metrics
    projected = [
        {
            "period_kind": r.get("period_kind"),
            "token_cap": r.get("token_cap"),
            "tokens_used": r.get("tokens_used"),
            "tokens_reserved": r.get("tokens_reserved"),
        }
        for r in rows
    ]
    if len(projected) == 1:
        return projected[0]
    return projected


async def manage_ai_and_agent_runners(arguments: dict[str, Any]) -> str:  # noqa: C901, PLR0911, PLR0912, PLR0915
    """Read, configure, or disable AI providers and manage token budgets."""
    for key in arguments:
        if key not in _ALLOWED_TOP_LEVEL_KEYS:
            msg = f"Unknown parameter '{key}'. Allowed: {sorted(_ALLOWED_TOP_LEVEL_KEYS)}"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    action = arguments.get("action")
    if not action or action not in _VALID_ACTIONS:
        msg = f"action must be one of {sorted(_VALID_ACTIONS)}"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if action == "help":
        help_doc = await build_help(
            "manage_ai_and_agent_runners",
            params_summary={
                "action": (
                    "list_providers | upsert_provider | disable_provider | "
                    "set_budget | get_budget_usage"
                ),
                "lod": "summary | standard | full",
            },
        )
        return dump_yaml(help_doc)

    if action in _DEFERRED_ACTIONS:
        return dump_yaml(
            {
                "error": "ACTION_NOT_AVAILABLE",
                "message": (
                    f"Action '{action}' is reserved for future implementation "
                    f"(KB-P5-16 / KB-P5-22)."
                ),
            }
        )

    ctx = get_current_mcp_context()
    if ctx is None or ctx.client is None:
        msg = "Internal API client unavailable"
        raise KbMcpError(McpErrorCode.UPSTREAM_UNAVAILABLE, msg)

    lod = arguments.get("lod", "summary")

    # Authorize caller scopes
    if ctx.caller_scopes is not None:
        if action in ("list_providers", "get_budget_usage"):
            if not any(
                s in ctx.caller_scopes for s in ("admin:read", "admin:write", "admin:destructive")
            ):
                msg = f"Action '{action}' requires 'admin:read' scope"
                raise KbMcpError(McpErrorCode.INSUFFICIENT_SCOPE, msg)
        elif not any(s in ctx.caller_scopes for s in ("admin:write", "admin:destructive")):
            msg = f"Action '{action}' requires 'admin:write' scope"
            raise KbMcpError(McpErrorCode.INSUFFICIENT_SCOPE, msg)

    if action == "list_providers":
        params: dict[str, Any] = {}
        if arguments.get("project_id"):
            params["project_id"] = arguments["project_id"]
        res = await ctx.client.request(
            "GET",
            "/api/v1/admin/ai/providers",
            params=params,
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        if not isinstance(res, list):
            msg = "Unexpected response from AI providers API"
            raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

        if "is_enabled" in arguments and isinstance(arguments["is_enabled"], bool):
            res = [r for r in res if r.get("is_enabled") == arguments["is_enabled"]]

        projected = [_project_provider(p, lod) for p in res]
        return dump_yaml(projected, strip_nulls=True)

    if action == "upsert_provider":
        if arguments.get("id"):
            config_id = arguments["id"]
            patch_fields = [
                "display_name",
                "model_allowlist",
                "residency_tier",
                "base_url",
                "priority",
                "settings",
                "is_enabled",
            ]
            payload: dict[str, Any] = {f: arguments[f] for f in patch_fields if f in arguments}
            if "api_key" in arguments:
                payload["api_key"] = arguments["api_key"]

            res = await ctx.client.request(
                "PATCH",
                f"/api/v1/admin/ai/providers/{config_id}",
                json_data=payload,
                subject_token=ctx.subject_token,
                mcp_session_id=ctx.session_id,
            )
        else:
            if not arguments.get("provider_kind"):
                msg = "provider_kind is required to create a new provider config"
                raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
            if not arguments.get("display_name"):
                msg = "display_name is required to create a new provider config"
                raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

            create_payload: dict[str, Any] = {
                "provider_kind": arguments["provider_kind"],
                "display_name": arguments["display_name"],
            }
            opt_fields = [
                "base_url",
                "model_allowlist",
                "residency_tier",
                "priority",
                "settings",
                "project_id",
                "is_enabled",
                "api_key",
            ]
            for field in opt_fields:
                if field in arguments and arguments[field] is not None:
                    create_payload[field] = arguments[field]

            res = await ctx.client.request(
                "POST",
                "/api/v1/admin/ai/providers",
                json_data=create_payload,
                subject_token=ctx.subject_token,
                mcp_session_id=ctx.session_id,
            )

        if not isinstance(res, dict):
            msg = "Unexpected response from AI providers API"
            raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

        return dump_yaml(_project_provider(res, lod), strip_nulls=True)

    if action == "disable_provider":
        config_id = arguments.get("id")
        if not config_id:
            msg = "id parameter is required for action 'disable_provider'"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        res = await ctx.client.request(
            "POST",
            f"/api/v1/admin/ai/providers/{config_id}:disable",
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        if not isinstance(res, dict):
            msg = "Unexpected response from AI providers API"
            raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

        return dump_yaml(_project_provider(res, lod), strip_nulls=True)

    if action == "set_budget":
        for req in ("provider_config_id", "period_kind", "token_cap"):
            if req not in arguments or arguments[req] is None:
                msg = f"'{req}' is required for action 'set_budget'"
                raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        budget_payload = {
            "provider_config_id": arguments["provider_config_id"],
            "period_kind": arguments["period_kind"],
            "token_cap": arguments["token_cap"],
        }
        if arguments.get("project_id"):
            budget_payload["project_id"] = arguments["project_id"]

        res = await ctx.client.request(
            "PUT",
            "/api/v1/admin/ai/budgets",
            json_data=budget_payload,
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        if not isinstance(res, dict):
            msg = "Unexpected response from AI budgets API"
            raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

        return dump_yaml(_project_budget([res], lod), strip_nulls=True)

    # get_budget_usage
    provider_config_id = arguments.get("provider_config_id")
    if not provider_config_id:
        msg = "'provider_config_id' is required for action 'get_budget_usage'"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    res = await ctx.client.request(
        "GET",
        "/api/v1/admin/ai/budgets",
        params={"provider_config_id": provider_config_id},
        subject_token=ctx.subject_token,
        mcp_session_id=ctx.session_id,
    )
    if not isinstance(res, list):
        msg = "Unexpected response from AI budgets API"
        raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

    return dump_yaml(_project_budget(res, lod), strip_nulls=True)


def create_manage_ai_and_agent_runners_tool() -> ToolSpec:
    """Construct ToolSpec for manage_ai_and_agent_runners."""
    return ToolSpec(
        name="manage_ai_and_agent_runners",
        description=(
            "Manage AI providers, envelope-encrypted API keys, token budgets, "
            "and agent runner infrastructure."
        ),
        input_schema=MANAGE_AI_AND_AGENT_RUNNERS_SCHEMA,
        surface=Surface.ADMIN,
        handler=manage_ai_and_agent_runners,
    )
