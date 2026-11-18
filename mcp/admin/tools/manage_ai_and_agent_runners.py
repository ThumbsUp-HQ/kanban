# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Implementation of manage_ai_and_agent_runners MCP tool (KB-P5-05b, KB-P5-22a)."""

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

_BANNED_CLI_FLAGS: Final[frozenset[str]] = frozenset(
    {
        "--yolo",
        "--dangerously-bypass-approvals-and-sandbox",
        "--dangerously-skip-permissions",
        "--full-auto",
        "--allow-all-tools",
    }
)

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
        "project",
        "project_key",
        "provider_config_id",
        "period_kind",
        "token_cap",
        "slug",
        "agent",
        "harness_kind",
        "model_id",
        "cli_binary_allowlist_id",
        "cli_args",
        "remote_runner_pool_slug",
        "repo_access_mode",
        "mcp_allowed_tools",
        "system_instructions_md",
        "timeout_ms",
        "pool_slug",
        "ttl_seconds",
        "status",
        "runner_id",
        "confirm",
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
        "delete_agent_definition",
        "mint_runner_enrollment_token",
        "list_remote_runners",
        "revoke_remote_runner",
        "help",
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
                "delete_agent_definition",
                "mint_runner_enrollment_token",
                "list_remote_runners",
                "revoke_remote_runner",
                "help",
            ],
            "description": "Operation to perform on AI providers, budgets, or agent runners",
        },
        "id": {
            "type": "string",
            "description": "Entity identifier UUID (provider, agent definition, or runner)",
        },
        "provider_kind": {
            "type": "string",
            "enum": ["openai", "ollama", "gemini", "fixture"],
            "description": "AI provider backend type",
        },
        "display_name": {
            "type": "string",
            "description": "Human-readable label for provider or agent definition",
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
            "description": "Optional project UUID for project-scoped entities",
        },
        "project": {
            "type": "string",
            "description": "Optional project UUID or identifier (alias for project_id)",
        },
        "project_key": {
            "type": "string",
            "description": "Optional project key or identifier (alias for project_id)",
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
        "slug": {
            "type": "string",
            "description": "Unique slug for agent definition",
        },
        "agent": {
            "type": "string",
            "description": "Agent definition slug or UUID",
        },
        "harness_kind": {
            "type": "string",
            "enum": ["in_app_sdk", "cli_pipe", "remote_runner"],
            "description": "Execution harness mode",
        },
        "model_id": {
            "type": "string",
            "description": "Target model identifier for in_app_sdk harness",
        },
        "cli_binary_allowlist_id": {
            "type": "string",
            "enum": ["agy", "codex", "gemini-cli", "claude-code"],
            "description": "Allowlisted CLI binary identifier for cli_pipe harness",
        },
        "cli_args": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Validated CLI arguments array for cli_pipe harness",
        },
        "remote_runner_pool_slug": {
            "type": "string",
            "description": "Pool slug for remote_runner harness",
        },
        "repo_access_mode": {
            "type": "string",
            "enum": ["none", "bare_git_tools", "ro_vfs_mount"],
            "description": "Repository access mode for agent execution",
        },
        "mcp_allowed_tools": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Allowed MCP tools subset for agent execution",
        },
        "system_instructions_md": {
            "type": "string",
            "description": "Markdown system instructions for agent definition",
        },
        "timeout_ms": {
            "type": "integer",
            "minimum": 1000,
            "maximum": 300000,
            "description": "Agent execution timeout in milliseconds",
        },
        "pool_slug": {
            "type": "string",
            "description": "Target runner pool slug",
        },
        "ttl_seconds": {
            "type": "integer",
            "minimum": 60,
            "maximum": 900,
            "description": "Single-use enrollment token TTL in seconds (60..900)",
        },
        "status": {
            "type": "string",
            "description": "Runner status filter ('online', 'offline', 'revoked')",
        },
        "runner_id": {
            "type": "string",
            "description": "Remote runner UUID for revocation",
        },
        "confirm": {
            "type": "boolean",
            "description": "Two-stage confirmation flag required for destructive actions",
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


def _project_agent_definition(a: dict[str, Any], lod: str) -> dict[str, Any]:
    """Project agent definition dictionary according to requested LOD."""
    if lod == "full":
        return a
    if lod == "standard":
        return {
            "id": a.get("id"),
            "slug": a.get("slug"),
            "display_name": a.get("display_name"),
            "harness_kind": a.get("harness_kind"),
            "provider_kind": a.get("provider_kind"),
            "model_id": a.get("model_id"),
            "cli_binary_allowlist_id": a.get("cli_binary_allowlist_id"),
            "remote_runner_pool_slug": a.get("remote_runner_pool_slug"),
            "repo_access_mode": a.get("repo_access_mode"),
            "timeout_ms": a.get("timeout_ms"),
            "project_id": a.get("project_id"),
        }
    return {
        "id": a.get("id"),
        "slug": a.get("slug"),
        "display_name": a.get("display_name"),
        "harness_kind": a.get("harness_kind"),
    }


def _project_runner(r: dict[str, Any], lod: str) -> dict[str, Any]:
    """Project remote runner dictionary according to requested LOD."""
    if lod == "full":
        return r
    if lod == "standard":
        return {
            "id": r.get("id"),
            "pool_slug": r.get("pool_slug"),
            "hostname": r.get("hostname"),
            "status": r.get("status"),
            "last_heartbeat_at": r.get("last_heartbeat_at"),
            "cert_expires_at": r.get("cert_expires_at"),
            "client_cert_sha256_hex": r.get("client_cert_sha256_hex"),
        }
    return {
        "id": r.get("id"),
        "pool_slug": r.get("pool_slug"),
        "hostname": r.get("hostname"),
        "status": r.get("status"),
    }


async def manage_ai_and_agent_runners(arguments: dict[str, Any]) -> str:  # noqa: C901, PLR0911, PLR0912, PLR0915
    """Read, configure, or disable AI providers, budgets, agent definitions, and remote runners."""
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
                    "set_budget | get_budget_usage | upsert_agent_definition | "
                    "list_agent_definitions | delete_agent_definition | "
                    "mint_runner_enrollment_token | list_remote_runners | revoke_remote_runner"
                ),
                "lod": "summary | standard | full",
            },
        )
        return dump_yaml(help_doc)

    ctx = get_current_mcp_context()
    if ctx is None or ctx.client is None:
        msg = "Internal API client unavailable"
        raise KbMcpError(McpErrorCode.UPSTREAM_UNAVAILABLE, msg)

    # Invariant: kb_agt_* key rejected on admin surface
    if ctx.subject_token and ctx.subject_token.startswith("kb_agt_"):
        msg = "Agent API keys (kb_agt_*) cannot access /mcp/admin tool (kb_agt_* key rejected)"
        raise KbMcpError(McpErrorCode.SURFACE_KEY_MISMATCH, msg)

    lod = arguments.get("lod", "summary")

    # Authorize caller scopes
    if ctx.caller_scopes is not None:
        read_actions = (
            "list_providers",
            "get_budget_usage",
            "list_agent_definitions",
            "list_remote_runners",
        )
        write_actions = (
            "upsert_provider",
            "disable_provider",
            "set_budget",
            "upsert_agent_definition",
            "mint_runner_enrollment_token",
        )
        if action in read_actions:
            if not any(
                s in ctx.caller_scopes for s in ("admin:read", "admin:write", "admin:destructive")
            ):
                msg = f"Action '{action}' requires 'admin:read' scope"
                raise KbMcpError(McpErrorCode.INSUFFICIENT_SCOPE, msg)
        elif action in write_actions:
            if not any(s in ctx.caller_scopes for s in ("admin:write", "admin:destructive")):
                msg = f"Action '{action}' requires 'admin:write' scope"
                raise KbMcpError(McpErrorCode.INSUFFICIENT_SCOPE, msg)
        elif action in ("delete_agent_definition", "revoke_remote_runner") and not any(
            s in ctx.caller_scopes for s in ("admin:destructive", "admin:write")
        ):
            msg = f"Action '{action}' requires 'admin:destructive' scope"
            raise KbMcpError(McpErrorCode.INSUFFICIENT_SCOPE, msg)

    # Normalize project / project_key / project_id alias
    resolved_proj = (
        arguments.get("project_id") or arguments.get("project") or arguments.get("project_key")
    )
    if resolved_proj:
        arguments["project_id"] = str(resolved_proj).strip()

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

    if action == "get_budget_usage":
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

    if action == "upsert_agent_definition":
        slug = arguments.get("slug") or arguments.get("id")
        if not slug:
            msg = "'slug' is required for action 'upsert_agent_definition'"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        # Validate cli_args for banned flags
        cli_args = arguments.get("cli_args")
        if isinstance(cli_args, list):
            for arg in cli_args:
                if isinstance(arg, str):
                    folded = arg.casefold()
                    if (
                        folded in _BANNED_CLI_FLAGS
                        or any(folded.startswith(f"{b}=") for b in _BANNED_CLI_FLAGS)
                        or folded.startswith("--dangerously")
                    ):
                        msg = f"BANNED_CLI_FLAG: CLI argument {arg!r} violates sandbox policy"
                        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        # Check if definition already exists
        existing: dict[str, Any] | None = None
        try:
            get_res = await ctx.client.request(
                "GET",
                f"/api/v1/admin/agent-definitions/{slug}",
                subject_token=ctx.subject_token,
                mcp_session_id=ctx.session_id,
            )
            if isinstance(get_res, dict):
                existing = get_res
        except Exception:  # noqa: BLE001
            existing = None

        if existing is not None:
            # Update definition (harness_kind is immutable after creation)
            patch_keys = [
                "display_name",
                "provider_kind",
                "model_id",
                "cli_binary_allowlist_id",
                "cli_args",
                "remote_runner_pool_slug",
                "repo_access_mode",
                "mcp_allowed_tools",
                "system_instructions_md",
                "timeout_ms",
            ]
            patch_payload: dict[str, Any] = {
                k: arguments[k] for k in patch_keys if k in arguments and arguments[k] is not None
            }
            res = await ctx.client.request(
                "PATCH",
                f"/api/v1/admin/agent-definitions/{slug}",
                json_data=patch_payload,
                subject_token=ctx.subject_token,
                mcp_session_id=ctx.session_id,
            )
        else:
            # Create new definition
            create_keys = [
                "slug",
                "display_name",
                "harness_kind",
                "provider_kind",
                "model_id",
                "cli_binary_allowlist_id",
                "cli_args",
                "remote_runner_pool_slug",
                "repo_access_mode",
                "mcp_allowed_tools",
                "system_instructions_md",
                "timeout_ms",
                "project_id",
            ]
            create_payload = {
                k: arguments[k] for k in create_keys if k in arguments and arguments[k] is not None
            }
            if "slug" not in create_payload:
                create_payload["slug"] = slug
            if "display_name" not in create_payload:
                create_payload["display_name"] = slug.replace("-", " ").title()
            if "harness_kind" not in create_payload:
                create_payload["harness_kind"] = "in_app_sdk"

            res = await ctx.client.request(
                "POST",
                "/api/v1/admin/agent-definitions",
                json_data=create_payload,
                subject_token=ctx.subject_token,
                mcp_session_id=ctx.session_id,
            )

        if not isinstance(res, dict):
            msg = "Unexpected response from agent definitions API"
            raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

        return dump_yaml(_project_agent_definition(res, lod), strip_nulls=True)

    if action == "list_agent_definitions":
        res = await ctx.client.request(
            "GET",
            "/api/v1/admin/agent-definitions",
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        if not isinstance(res, list):
            msg = "Unexpected response from agent definitions API"
            raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

        projected = [_project_agent_definition(a, lod) for a in res]
        return dump_yaml(projected, strip_nulls=True)

    if action == "delete_agent_definition":
        agent_ref = arguments.get("slug") or arguments.get("id") or arguments.get("agent")
        if not agent_ref:
            msg = "'slug' or 'id' is required for action 'delete_agent_definition'"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        confirm = arguments.get("confirm", False)
        if confirm is not True:
            return dump_yaml(
                {
                    "status": "confirmation_required",
                    "action": "delete_agent_definition",
                    "agent": agent_ref,
                    "message": (
                        "Permanent deletion of agent definition. "
                        "Re-run with confirm=true to proceed."
                    ),
                }
            )

        await ctx.client.request(
            "DELETE",
            f"/api/v1/admin/agent-definitions/{agent_ref}",
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        return dump_yaml(
            {
                "status": "deleted",
                "action": "delete_agent_definition",
                "agent": agent_ref,
            }
        )

    if action == "mint_runner_enrollment_token":
        pool_slug = arguments.get("pool_slug")
        if not pool_slug:
            msg = "'pool_slug' is required for action 'mint_runner_enrollment_token'"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        mint_payload: dict[str, Any] = {"pool_slug": pool_slug}
        if "ttl_seconds" in arguments and arguments["ttl_seconds"] is not None:
            mint_payload["ttl_seconds"] = arguments["ttl_seconds"]

        res = await ctx.client.request(
            "POST",
            "/api/v1/admin/agent-runners/enrollment-tokens",
            json_data=mint_payload,
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        if not isinstance(res, dict):
            msg = "Unexpected response from runner enrollment tokens API"
            raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

        return dump_yaml(res, strip_nulls=True)

    if action == "list_remote_runners":
        params = {}
        if arguments.get("pool_slug"):
            params["pool_slug"] = arguments["pool_slug"]
        if arguments.get("status"):
            params["status"] = arguments["status"]

        res = await ctx.client.request(
            "GET",
            "/api/v1/admin/agent-runners",
            params=params,
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        if not isinstance(res, list):
            msg = "Unexpected response from remote runners API"
            raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

        projected = [_project_runner(r, lod) for r in res]
        return dump_yaml(projected, strip_nulls=True)

    if action == "revoke_remote_runner":
        runner_id = arguments.get("id") or arguments.get("runner_id")
        if not runner_id:
            msg = "'id' or 'runner_id' is required for action 'revoke_remote_runner'"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        confirm = arguments.get("confirm", False)
        if confirm is not True:
            return dump_yaml(
                {
                    "status": "confirmation_required",
                    "action": "revoke_remote_runner",
                    "runner_id": runner_id,
                    "message": (
                        "Permanent revocation of remote runner credentials. "
                        "Re-run with confirm=true to proceed."
                    ),
                }
            )

        res = await ctx.client.request(
            "POST",
            f"/api/v1/admin/agent-runners/{runner_id}:revoke",
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        if not isinstance(res, dict):
            msg = "Unexpected response from remote runners API"
            raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

        return dump_yaml(res, strip_nulls=True)

    msg = f"Unhandled action '{action}'"
    raise KbMcpError(McpErrorCode.INTERNAL, msg)


def create_manage_ai_and_agent_runners_tool() -> ToolSpec:
    """Construct ToolSpec for manage_ai_and_agent_runners."""
    return ToolSpec(
        name="manage_ai_and_agent_runners",
        description=(
            "Manage AI providers, envelope-encrypted API keys, token budgets, "
            "agent execution definitions, and remote agent runner infrastructure."
        ),
        input_schema=MANAGE_AI_AND_AGENT_RUNNERS_SCHEMA,
        surface=Surface.ADMIN,
        handler=manage_ai_and_agent_runners,
    )
