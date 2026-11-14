# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Implementation of the manage_auth_cards MCP tool (S11.4, S4.1, S4.3, KB-P4-09a)."""

from __future__ import annotations

import re
from typing import Any, Final

from mcp.context import get_current_mcp_context
from mcp.errors import KbMcpError, McpErrorCode
from mcp.help import build_help
from mcp.registry import Surface, ToolSpec
from mcp.yaml_out import dump_yaml

__all__ = [
    "MANAGE_AUTH_CARDS_SCHEMA",
    "create_manage_auth_cards_tool",
    "manage_auth_cards",
]

_ALLOWED_KEYS: Final[frozenset[str]] = frozenset(
    {
        "action",
        "card",
        "slug",
        "provider_kind",
        "display_name",
        "button_subtext",
        "icon_preset",
        "public_config",
        "secret",
        "allowed_email_domains",
        "auto_provision_users",
        "after",
        "confirm_slug",
        "lod",
    }
)

_SLUG_CLEAN_RE: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9]+")
_MAX_EMAIL_DOMAINS: Final[int] = 50
_MIN_SLUG_LEN: Final[int] = 3

MANAGE_AUTH_CARDS_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": [
                "list",
                "get",
                "create",
                "update",
                "enable",
                "disable",
                "reorder",
                "test_handshake",
                "delete",
                "help",
            ],
            "description": "Card operation to perform",
        },
        "card": {
            "type": "string",
            "description": "Card slug or UUID (required for non-list/create actions)",
        },
        "slug": {
            "type": "string",
            "description": "Card slug (for create)",
        },
        "provider_kind": {
            "type": "string",
            "enum": ["OIDC", "OAUTH2", "LDAP", "LOCAL_ADMIN"],
            "description": "Provider type (required for create)",
        },
        "display_name": {
            "type": "string",
            "description": "User-facing title on login card",
        },
        "button_subtext": {
            "type": "string",
            "description": "Subtitle on login button",
        },
        "icon_preset": {
            "type": "string",
            "description": "Icon key preset (e.g. 'key', 'shield', 'lock')",
        },
        "public_config": {
            "type": "object",
            "description": "Provider-specific public configuration object",
        },
        "secret": {
            "type": "object",
            "writeOnly": True,
            "description": (
                "Write-only provider credentials (client_secret or bind_dn_password); never echoed"
            ),
        },
        "allowed_email_domains": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 50,
            "description": "Email domain allowlist (max 50 entries)",
        },
        "auto_provision_users": {
            "type": "boolean",
            "description": "Auto-provision users on first successful authentication",
        },
        "after": {
            "type": "string",
            "description": "Card slug to place after during reorder (empty string '' = first)",
        },
        "confirm_slug": {
            "type": "string",
            "description": "Card slug confirmation phrase required for permanent deletion",
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


def _extract_secret_string(secret_val: object) -> str | None:
    """Extract plaintext secret string from object or string."""
    if isinstance(secret_val, str):
        return secret_val
    if isinstance(secret_val, dict):
        res = (
            secret_val.get("client_secret")
            or secret_val.get("bind_dn_password")
            or secret_val.get("secret")
        )
        return str(res) if res is not None else None
    return None


def _derive_slug(card_param: str | None, slug_param: str | None, display_name: str | None) -> str:
    """Derive card slug from parameters or display name."""
    candidate = slug_param or card_param
    if candidate:
        return candidate.strip().lower()
    if display_name:
        cleaned = _SLUG_CLEAN_RE.sub("-", display_name.lower()).strip("-")
        return cleaned[:48] if len(cleaned) >= _MIN_SLUG_LEN else f"{cleaned}-auth"
    return "auth-card"


async def manage_auth_cards(arguments: dict[str, Any]) -> str:  # noqa: C901, PLR0911, PLR0912, PLR0915
    """Manage authentication provider cards, ordering, and anti-lockout safeguards."""
    # Check top-level parameter names
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
            "manage_auth_cards",
            params_summary={
                "action": (
                    "list | get | create | update | enable | disable | reorder | "
                    "test_handshake | delete | help"
                ),
                "card": "slug | uuid",
            },
        )
        return dump_yaml(help_doc)

    ctx = get_current_mcp_context()
    if ctx is None or ctx.client is None:
        msg = "Internal API client unavailable"
        raise KbMcpError(McpErrorCode.UPSTREAM_UNAVAILABLE, msg)

    # Scope authorization checks
    if ctx.caller_scopes is not None:
        if action in ("list", "get", "test_handshake"):
            if not any(
                s in ctx.caller_scopes for s in ("admin:read", "admin:write", "admin:destructive")
            ):
                msg = f"Action '{action}' requires 'admin:read' scope"
                raise KbMcpError(McpErrorCode.INSUFFICIENT_SCOPE, msg)
        elif action in ("create", "update", "enable", "disable", "reorder"):
            if not any(s in ctx.caller_scopes for s in ("admin:write", "admin:destructive")):
                msg = f"Action '{action}' requires 'admin:write' scope"
                raise KbMcpError(McpErrorCode.INSUFFICIENT_SCOPE, msg)
        elif action == "delete" and "admin:destructive" not in ctx.caller_scopes:
            msg = "Action 'delete' requires 'admin:destructive' scope"
            raise KbMcpError(McpErrorCode.INSUFFICIENT_SCOPE, msg)

    # Domain allowlist boundary check (Action 4 / Test Case 4: max 50)
    domains = arguments.get("allowed_email_domains")
    if domains is not None and (not isinstance(domains, list) or len(domains) > _MAX_EMAIL_DOMAINS):
        msg = "allowed_email_domains cannot exceed 50 entries"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    card_ref = arguments.get("card")

    # Scope and action routing
    if action == "list":
        res = await ctx.client.request(
            "GET",
            "/api/v1/admin/auth-cards",
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        if not isinstance(res, dict) or "cards" not in res:
            msg = "Unexpected response from auth cards list API"
            raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

        cards_list: list[dict[str, Any]] = res.get("cards", [])
        lod = arguments.get("lod", "summary")
        if lod == "full":
            return dump_yaml({"cards": cards_list})

        summary_cards: list[dict[str, Any]] = []
        for idx, c in enumerate(cards_list, start=1):
            health = c.get("last_health_status", "OK")
            if health == "UNVERIFIED":
                health = "OK"
            summary_cards.append(
                {
                    "slug": c.get("slug"),
                    "kind": c.get("provider_kind"),
                    "enabled": c.get("is_enabled", False),
                    "rank": idx,
                    "health": health,
                }
            )
        return dump_yaml({"cards": summary_cards})

    if action in ("get", "update", "enable", "disable", "reorder", "test_handshake", "delete") and (
        not card_ref or not isinstance(card_ref, str) or not card_ref.strip()
    ):
        msg = f"card parameter (slug or UUID) is required for action '{action}'"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if action == "get":
        res = await ctx.client.request(
            "GET",
            f"/api/v1/admin/auth-cards/{card_ref}",
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        return dump_yaml(res)

    if action == "test_handshake":
        res = await ctx.client.request(
            "POST",
            f"/api/v1/admin/auth-cards/{card_ref}/test-handshake",
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        return dump_yaml(res)

    if action == "create":
        provider_kind = arguments.get("provider_kind")
        if not provider_kind or provider_kind not in ("OIDC", "OAUTH2", "LDAP", "LOCAL_ADMIN"):
            msg = "provider_kind ('OIDC', 'OAUTH2', 'LDAP', 'LOCAL_ADMIN') is required for create"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        display_name = arguments.get("display_name")
        if not display_name or not isinstance(display_name, str):
            msg = "display_name is required for action 'create'"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        slug = _derive_slug(card_ref, arguments.get("slug"), display_name)
        secret_str = _extract_secret_string(arguments.get("secret"))

        create_payload: dict[str, Any] = {
            "provider_kind": provider_kind,
            "slug": slug,
            "display_name": display_name,
            "button_subtext": arguments.get("button_subtext"),
            "icon_preset": arguments.get("icon_preset", "key"),
            "public_config": arguments.get("public_config", {}),
            "allowed_email_domains": domains or [],
            "auto_provision_users": bool(arguments.get("auto_provision_users", False)),
        }
        if secret_str is not None:
            create_payload["secret"] = secret_str

        res = await ctx.client.request(
            "POST",
            "/api/v1/admin/auth-cards",
            json_data=create_payload,
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        return dump_yaml(res)

    if action == "update":
        update_payload: dict[str, Any] = {}
        for prop in (
            "display_name",
            "button_subtext",
            "icon_preset",
            "public_config",
            "auto_provision_users",
        ):
            if prop in arguments:
                update_payload[prop] = arguments[prop]
        if domains is not None:
            update_payload["allowed_email_domains"] = domains

        secret_str = _extract_secret_string(arguments.get("secret"))
        if secret_str is not None:
            update_payload["secret"] = secret_str

        res = await ctx.client.request(
            "PATCH",
            f"/api/v1/admin/auth-cards/{card_ref}",
            json_data=update_payload,
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        return dump_yaml(res)

    if action == "enable":
        res = await ctx.client.request(
            "POST",
            f"/api/v1/admin/auth-cards/{card_ref}/enable",
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        return dump_yaml(res)

    if action == "disable":
        res = await ctx.client.request(
            "POST",
            f"/api/v1/admin/auth-cards/{card_ref}/disable",
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        return dump_yaml(res)

    if action == "reorder":
        after_val = arguments.get("after")
        reorder_payload = {"after": after_val if after_val is not None else ""}
        res = await ctx.client.request(
            "POST",
            f"/api/v1/admin/auth-cards/{card_ref}/reorder",
            json_data=reorder_payload,
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        return dump_yaml(res)

    if action == "delete":
        confirm_slug = arguments.get("confirm_slug")
        if not confirm_slug or not isinstance(confirm_slug, str):
            msg = "confirm_slug parameter is required for action 'delete'"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        if (
            card_ref
            and not card_ref.startswith(("0", "1", "2", "3", "4", "5", "6", "7", "8", "9"))
            and confirm_slug != card_ref
        ):
            msg = f"confirm_slug must match card slug '{card_ref}'"
            raise KbMcpError(McpErrorCode.CONFIRM_PHRASE_MISMATCH, msg)

        delete_payload = {"confirm_slug": confirm_slug}
        await ctx.client.request(
            "DELETE",
            f"/api/v1/admin/auth-cards/{card_ref}",
            json_data=delete_payload,
            subject_token=ctx.subject_token,
            mcp_session_id=ctx.session_id,
        )
        return dump_yaml({"deleted": True, "card": card_ref})

    msg = f"Unknown action '{action}'"
    raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)


def create_manage_auth_cards_tool() -> ToolSpec:
    """Construct ToolSpec for manage_auth_cards."""
    return ToolSpec(
        name="manage_auth_cards",
        description=(
            "Manage authentication provider cards, ordering, health, and anti-lockout safeguards."
        ),
        input_schema=MANAGE_AUTH_CARDS_SCHEMA,
        surface=Surface.ADMIN,
        handler=manage_auth_cards,
    )
