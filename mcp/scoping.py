# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Dynamic MCP Connection Scoping: Global, Workspace, and Project (KB-P4-15, S11.1)."""

from __future__ import annotations

import contextlib
import hashlib
import ipaddress
import re
import uuid
from dataclasses import dataclass
from enum import IntFlag, StrEnum
from typing import TYPE_CHECKING, Any, Final

from mcp.errors import KbMcpError, McpErrorCode

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mcp.auth import McpAuthContext

__all__ = [
    "TOOL_REQUIRED_CAPABILITIES",
    "Capability",
    "ConnectionScope",
    "CredentialBoundary",
    "ScopeMode",
    "compute_session_fingerprint",
    "enforce_connection_scope_on_tool_call",
    "enforce_credential_boundary_on_tool_call",
    "get_required_tool_capability",
    "intersect_key_and_connection_scope",
    "parse_connection_scope",
]

_PATH_WORKSPACE_RE: Final[re.Pattern[str]] = re.compile(
    r"/w/(?P<workspace>[a-zA-Z0-9_-]+)(?:/p/(?P<project>[A-Z][A-Z0-9]{0,9}))?"
)
_ISSUE_KEY_REGEX: Final[re.Pattern[str]] = re.compile(r"^([A-Z][A-Z0-9]{0,9})-([0-9]+)$")


class Capability(IntFlag):
    """Granular capability bitmask matching S3.2 / KB-P1-13 bit positions."""

    NONE = 0
    VIEW = 1 << 0  # 1
    COMMENT = 1 << 1  # 2
    EDIT = 1 << 2  # 4
    TRANSITION = 1 << 3  # 8
    LINK = 1 << 4  # 16
    SHARE = 1 << 5  # 32
    ADMIN = 1 << 6  # 64
    DELETE = 1 << 7  # 128
    ALL = 0xFF  # 255


@dataclass(frozen=True, slots=True)
class CredentialBoundary:
    """Immutable boundary enforcing scoping, surface, CIDR, and capability invariants."""

    scope_tier: str = "workspace"
    surface: str = "agent"
    workspace_allowlist: frozenset[uuid.UUID] = frozenset()
    project_allowlist: frozenset[uuid.UUID] = frozenset()
    capability_mask: int = 255
    allowed_tools: frozenset[str] | None = None
    allowed_cidrs: tuple[str, ...] = ()
    execution_id: uuid.UUID | None = None
    has_aal2_provenance: bool = False

    def allows_workspace(self, workspace_id: uuid.UUID | str | None) -> bool:
        """Check whether the workspace is permitted under this credential boundary."""
        if workspace_id is None:
            return True
        target = (
            uuid.UUID(str(workspace_id))
            if not isinstance(workspace_id, uuid.UUID)
            else workspace_id
        )
        if self.workspace_allowlist:
            return target in self.workspace_allowlist
        return self.scope_tier == "global"

    def allows_project(self, project_id: uuid.UUID | str | None) -> bool:
        """Check whether the project is permitted under this credential boundary."""
        if project_id is None:
            return True
        target = uuid.UUID(str(project_id)) if not isinstance(project_id, uuid.UUID) else project_id
        if self.project_allowlist:
            return target in self.project_allowlist
        return self.scope_tier != "project"

    def allows_ip(self, client_ip: str | None) -> bool:
        """Check whether the client IP address is allowed under the CIDR allowlist."""
        if not self.allowed_cidrs or not client_ip:
            return True
        try:
            ip = ipaddress.ip_address(client_ip)
            return any(
                ip in ipaddress.ip_network(cidr, strict=False) for cidr in self.allowed_cidrs
            )
        except ValueError:
            return False


def _as_uuid(val: object) -> uuid.UUID | None:
    """Safely convert value to UUID, returning None if unparseable."""
    if val is None:
        return None
    if isinstance(val, uuid.UUID):
        return val
    try:
        return uuid.UUID(str(val))
    except (ValueError, AttributeError, TypeError):
        return None


class ScopeMode(StrEnum):
    """Connection scoping mode."""

    GLOBAL = "GLOBAL"
    WORKSPACE = "WORKSPACE"
    PROJECT = "PROJECT"


@dataclass(frozen=True, slots=True)
class ConnectionScope:
    """Resolved MCP connection scope governing authorization and tool defaults."""

    mode: ScopeMode
    workspace_slug: str | None = None
    project_key: str | None = None
    workspace_id: str | None = None
    project_id: str | None = None

    @property
    def is_global(self) -> bool:
        """Return True if connection operates in global mode."""
        return self.mode == ScopeMode.GLOBAL

    @property
    def is_workspace(self) -> bool:
        """Return True if connection operates in workspace mode."""
        return self.mode == ScopeMode.WORKSPACE

    @property
    def is_project(self) -> bool:
        """Return True if connection operates in project mode."""
        return self.mode == ScopeMode.PROJECT


def parse_connection_scope(  # noqa: C901
    path: str,
    headers: Mapping[str, str] | None = None,
) -> ConnectionScope:
    """Parse URL path and HTTP request headers into a candidate ConnectionScope.

    Raises:
        KbMcpError: CONFLICTING_SCOPE_HEADERS (400) if path and header disagree.
        KbMcpError: VALIDATION_FAILED (400) if project key is supplied without workspace.

    """
    path_ws: str | None = None
    path_proj: str | None = None

    match = _PATH_WORKSPACE_RE.search(path)
    if match:
        path_ws = match.group("workspace")
        path_proj = match.group("project")

    header_ws: str | None = None
    header_proj: str | None = None
    if headers:
        for k, v in headers.items():
            k_lower = k.lower()
            if k_lower == "x-workspace-slug" and v:
                header_ws = v.strip()
            elif k_lower == "x-project-key" and v:
                header_proj = v.strip().upper()

    if path_ws and header_ws and path_ws != header_ws:
        msg = f"Conflicting workspace in URL path '{path_ws}' and header '{header_ws}'"
        raise KbMcpError(McpErrorCode.CONFLICTING_SCOPE_HEADERS, msg)

    if path_proj and header_proj and path_proj != header_proj:
        msg = f"Conflicting project in URL path '{path_proj}' and header '{header_proj}'"
        raise KbMcpError(McpErrorCode.CONFLICTING_SCOPE_HEADERS, msg)

    effective_ws = path_ws or header_ws
    effective_proj = path_proj or header_proj

    if effective_proj and not effective_ws:
        msg = "X-Project-Key requires X-Workspace-Slug or /w/{slug}"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if effective_proj and effective_ws:
        return ConnectionScope(
            mode=ScopeMode.PROJECT,
            workspace_slug=effective_ws,
            project_key=effective_proj,
        )

    if effective_ws:
        return ConnectionScope(
            mode=ScopeMode.WORKSPACE,
            workspace_slug=effective_ws,
        )

    return ConnectionScope(mode=ScopeMode.GLOBAL)


def _validate_boundary_workspace(
    boundary: CredentialBoundary | None,
    scope: ConnectionScope,
    auth_ctx: McpAuthContext,
    *,
    ws_match: bool,
) -> None:
    if boundary is not None and boundary.workspace_allowlist:
        ws_uuid = (
            _as_uuid(scope.workspace_id)
            or (_as_uuid(auth_ctx.workspace_id) if ws_match else None)
            or _as_uuid(scope.workspace_slug)
        )
        if ws_uuid is not None and not boundary.allows_workspace(ws_uuid):
            msg = (
                f"Requested workspace '{scope.workspace_slug}' is outside "
                f"the scope boundary of this credential."
            )
            raise KbMcpError(
                McpErrorCode.KEY_SCOPE_VIOLATION,
                msg,
                extra={"allowed_workspaces": [str(w) for w in boundary.workspace_allowlist]},
                hint="Use an API key with global or appropriate workspace permissions.",
            )


def _validate_boundary_project(
    boundary: CredentialBoundary | None,
    scope: ConnectionScope,
    auth_ctx: McpAuthContext,
) -> None:
    if boundary is not None and boundary.project_allowlist:
        proj_uuid = (
            _as_uuid(scope.project_id)
            or _as_uuid(auth_ctx.project_id)
            or _as_uuid(scope.project_key)
        )
        if proj_uuid is not None and not boundary.allows_project(proj_uuid):
            msg = (
                f"Requested project '{scope.project_key}' is outside "
                f"the scope boundary of this credential."
            )
            raise KbMcpError(
                McpErrorCode.KEY_SCOPE_VIOLATION,
                msg,
                extra={"allowed_projects": [str(p) for p in boundary.project_allowlist]},
                hint="Use an API key with permissions for this project.",
            )


def intersect_key_and_connection_scope(
    auth_ctx: McpAuthContext,
    scope: ConnectionScope,
) -> ConnectionScope:
    """Validate monotonic narrowing: connection scope may only narrow token scope, never widen."""
    token_ws = getattr(auth_ctx, "workspace_slug", None) or auth_ctx.workspace_id
    token_tier = getattr(auth_ctx, "scope_tier", None)
    allowed_projects = getattr(auth_ctx, "allowed_projects", None)

    # 1. Global connection mode
    if scope.is_global:
        if token_tier in ("global", "server") or not token_ws:
            return scope

        # Token is pinned to workspace or project: connection inherits token scope
        if allowed_projects and len(allowed_projects) == 1:
            return ConnectionScope(
                mode=ScopeMode.PROJECT,
                workspace_slug=str(token_ws),
                workspace_id=auth_ctx.workspace_id,
                project_key=str(allowed_projects[0]),
                project_id=str(allowed_projects[0]),
            )
        return ConnectionScope(
            mode=ScopeMode.WORKSPACE,
            workspace_slug=str(token_ws),
            workspace_id=auth_ctx.workspace_id,
        )

    # 2. Workspace connection mode
    if scope.is_workspace:
        ws_match = (
            bool(auth_ctx.workspace_slug) and auth_ctx.workspace_slug == scope.workspace_slug
        ) or (bool(auth_ctx.workspace_id) and str(auth_ctx.workspace_id) == scope.workspace_slug)
        _validate_boundary_workspace(
            getattr(auth_ctx, "credential_boundary", None), scope, auth_ctx, ws_match=ws_match
        )

        has_boundary = bool(auth_ctx.workspace_slug or auth_ctx.workspace_id)
        if token_tier not in ("global", "server") and has_boundary and not ws_match:
            msg = (
                f"Requested workspace '{scope.workspace_slug}' is outside "
                f"the scope boundary of this API key."
            )
            allowed_ws = (
                [str(auth_ctx.workspace_slug)]
                if auth_ctx.workspace_slug
                else ([str(auth_ctx.workspace_id)] if auth_ctx.workspace_id else [])
            )
            raise KbMcpError(
                McpErrorCode.KEY_SCOPE_VIOLATION,
                msg,
                extra={"allowed_workspaces": allowed_ws},
                hint="Use an API key with global or appropriate workspace permissions.",
            )
        if allowed_projects:
            msg = (
                "Token is pinned to specific project(s) and cannot connect in workspace-wide mode."
            )
            raise KbMcpError(
                McpErrorCode.KEY_SCOPE_VIOLATION,
                msg,
                extra={"allowed_projects": list(allowed_projects)},
            )
        return ConnectionScope(
            mode=ScopeMode.WORKSPACE,
            workspace_slug=scope.workspace_slug,
            workspace_id=auth_ctx.workspace_id if ws_match else None,
        )

    # 3. Project connection mode
    if scope.is_project:
        ws_match = (
            bool(auth_ctx.workspace_slug) and auth_ctx.workspace_slug == scope.workspace_slug
        ) or (bool(auth_ctx.workspace_id) and str(auth_ctx.workspace_id) == scope.workspace_slug)
        boundary = getattr(auth_ctx, "credential_boundary", None)
        _validate_boundary_workspace(boundary, scope, auth_ctx, ws_match=ws_match)
        _validate_boundary_project(boundary, scope, auth_ctx)

        has_boundary = bool(auth_ctx.workspace_slug or auth_ctx.workspace_id)
        if token_tier not in ("global", "server") and has_boundary and not ws_match:
            msg = (
                f"Requested workspace '{scope.workspace_slug}' is outside "
                f"the scope boundary of this API key."
            )
            allowed_ws = (
                [str(auth_ctx.workspace_slug)]
                if auth_ctx.workspace_slug
                else ([str(auth_ctx.workspace_id)] if auth_ctx.workspace_id else [])
            )
            raise KbMcpError(
                McpErrorCode.KEY_SCOPE_VIOLATION,
                msg,
                extra={"allowed_workspaces": allowed_ws},
                hint="Use an API key with global or appropriate workspace permissions.",
            )

        proj_str = str(auth_ctx.project_id) if auth_ctx.project_id is not None else None
        allowed_proj_keys = getattr(auth_ctx, "allowed_project_keys", None) or []
        proj_match = (
            (
                scope.project_key in allowed_projects
                or scope.project_key in allowed_proj_keys
                or (scope.project_id is not None and scope.project_id in allowed_projects)
                or (proj_str is not None and proj_str in (scope.project_key, scope.project_id))
            )
            if allowed_projects
            else True
        )
        if allowed_projects and not proj_match:
            msg = (
                f"Requested project '{scope.project_key}' is outside "
                f"the scope boundary of this API key."
            )
            raise KbMcpError(
                McpErrorCode.KEY_SCOPE_VIOLATION,
                msg,
                extra={"allowed_projects": list(allowed_projects)},
                hint="Use an API key with permissions for this project.",
            )
        return ConnectionScope(
            mode=ScopeMode.PROJECT,
            workspace_slug=scope.workspace_slug,
            project_key=scope.project_key,
            workspace_id=auth_ctx.workspace_id if ws_match else None,
            project_id=scope.project_id or auth_ctx.project_id,
        )

    return scope


def compute_session_fingerprint(
    token_sha256: bytes,
    workspace_id_or_slug: str | bytes | None = None,
    project_id_or_key: str | bytes | None = None,
) -> bytes:
    """Compute binding fingerprint for Mcp-Session-Id."""
    ws_bytes = (
        workspace_id_or_slug.encode("utf-8")
        if isinstance(workspace_id_or_slug, str)
        else (workspace_id_or_slug or b"")
    )
    proj_bytes = (
        project_id_or_key.encode("utf-8")
        if isinstance(project_id_or_key, str)
        else (project_id_or_key or b"")
    )
    return hashlib.sha256(token_sha256 + b"\x00" + ws_bytes + b"\x00" + proj_bytes).digest()


def _tool_accepts_project(
    tool_name: str,
    tool_spec: object | None,
    input_schema: dict[str, Any] | None,
) -> bool:
    schema = input_schema
    if schema is None and tool_spec is not None:
        schema = getattr(tool_spec, "input_schema", None)
    if schema is None:
        with contextlib.suppress(Exception):
            from mcp.surfaces.agent import create_agent_registry  # noqa: PLC0415

            t = create_agent_registry().get(tool_name)
            if t is not None:
                schema = t.input_schema

    if isinstance(schema, dict):
        properties = schema.get("properties", {})
        add_props = schema.get("additionalProperties", True)
        if "project" not in properties and add_props is False:
            return False
    return True


def enforce_connection_scope_on_tool_call(
    tool_name: str,
    arguments: dict[str, Any],
    scope: ConnectionScope,
    tool_spec: object | None = None,
    input_schema: dict[str, Any] | None = None,
) -> None:
    """Auto-fill project in Mode C (Project-Scoped) and reject cross-project mutations.

    Raises:
        KbMcpError: CONNECTION_SCOPE_VIOLATION if an explicit foreign project is targeted.

    """
    if not scope.is_project or not scope.project_key:
        return

    val = arguments.get("project")
    if val is not None and str(val).strip() != "":
        if str(val).upper() != scope.project_key:
            attempted = str(val)
            msg = (
                f"Connection is strictly pinned to project '{scope.project_key}'. "
                f"Mutation targeting foreign project '{attempted}' was blocked."
            )
            raise KbMcpError(
                McpErrorCode.CONNECTION_SCOPE_VIOLATION,
                msg,
                extra={
                    "pinned_scope": {
                        "workspace": scope.workspace_slug,
                        "project": scope.project_key,
                    },
                    "attempted_target": attempted,
                },
                hint=(
                    f"Connect to /mcp/agent/w/{scope.workspace_slug}/p/{attempted} "
                    "or run in Global mode (/mcp/agent) to operate across projects."
                ),
            )
        return

    if _tool_accepts_project(tool_name, tool_spec, input_schema):
        arguments["project"] = scope.project_key

    # Check issue key identifier for mutating tools
    mutating_tools: Final[frozenset[str]] = frozenset(
        {
            "create",
            "update",
            "create_ticket",
            "update_ticket",
            "delete_ticket",
            "transition_ticket",
            "begin_work",
            "complete_work",
            "manage_stickies",
            "upsert_doc",
            "architect_project",
        }
    )
    ident = (
        arguments.get("identifier")
        or arguments.get("parent")
        or arguments.get("ticket")
        or arguments.get("id")
    )
    if ident and isinstance(ident, str) and tool_name in mutating_tools:
        match = _ISSUE_KEY_REGEX.match(ident)
        if match:
            target_proj = match.group(1).upper()
            if target_proj != scope.project_key:
                msg = (
                    f"Connection is strictly pinned to project '{scope.project_key}'. "
                    f"Mutation targeting foreign project '{target_proj}' was blocked."
                )
                raise KbMcpError(
                    McpErrorCode.CONNECTION_SCOPE_VIOLATION,
                    msg,
                    extra={
                        "pinned_scope": {
                            "workspace": scope.workspace_slug,
                            "project": scope.project_key,
                        },
                        "attempted_target": target_proj,
                    },
                    hint=(
                        f"Connect to /mcp/agent/w/{scope.workspace_slug}/p/{target_proj} "
                        "or run in Global mode (/mcp/agent) to operate across projects."
                    ),
                )


TOOL_REQUIRED_CAPABILITIES: Final[dict[str, Capability]] = {
    # Agent surface tools
    "ping_agent": Capability.VIEW,
    "search_tickets": Capability.VIEW,
    "read_ticket": Capability.VIEW,
    "create_ticket": Capability.EDIT,
    "update_ticket": Capability.EDIT,
    "begin_work": Capability.TRANSITION,
    "transition_ticket": Capability.TRANSITION,
    "complete_work": Capability.TRANSITION,
    "add_comment": Capability.COMMENT,
    "link_objects": Capability.LINK,
    "test_agent_write": Capability.EDIT,
    # Docs surface tools
    "ping_docs": Capability.VIEW,
    "search": Capability.VIEW,
    "search_docs": Capability.VIEW,
    "search_knowledge": Capability.VIEW,
    "read_doc": Capability.VIEW,
    "create": Capability.EDIT,
    "update": Capability.EDIT,
    "create_doc": Capability.EDIT,
    "update_doc": Capability.EDIT,
    "upsert_doc": Capability.EDIT,
    "manage_stickies": Capability.EDIT,
    "promote_sticky_to_doc": Capability.EDIT,
    "link_knowledge": Capability.LINK,
    # Admin surface tools
    "destructive_lifecycle": Capability.DELETE,
    "test_admin_destructive": Capability.DELETE,
}

_ADMIN_DESTRUCTIVE_ACTIONS: Final[frozenset[str]] = frozenset({"execute_delete", "detach"})
_ADMIN_WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "create_",
    "update_",
    "set_",
    "upsert_",
    "provision_",
    "bind_",
    "unbind_",
    "add_",
    "remove_",
    "attach",
    "apply",
    "plan",
    "mint_",
    "rotate_",
)
_ADMIN_WRITE_ACTIONS: Final[frozenset[str]] = frozenset(
    {
        "override_creator",
        "override_hard_wip_move",
        "unarchive_issue",
        "run_audit",
        "refresh_repo_binding",
        "request_delete",
        "restore",
        "deactivate",
        "reactivate",
    }
)


def get_required_tool_capability(tool_name: str, action: str | None = None) -> Capability:
    """Return the Capability bit required to dispatch the specified tool/action."""
    if tool_name in TOOL_REQUIRED_CAPABILITIES:
        return TOOL_REQUIRED_CAPABILITIES[tool_name]

    if action:
        act = str(action).strip().lower()
        if act.startswith(("delete_", "purge_", "revoke_")) or act in _ADMIN_DESTRUCTIVE_ACTIONS:
            return Capability.DELETE
        if act.startswith(_ADMIN_WRITE_PREFIXES) or act in _ADMIN_WRITE_ACTIONS:
            return Capability.ADMIN

    return Capability.ADMIN


def _check_boundary_allowed_tools(boundary: CredentialBoundary, tool_name: str) -> None:
    allowed_tools = getattr(boundary, "allowed_tools", None)
    if allowed_tools is None:
        return

    is_allowed = tool_name in allowed_tools
    if not is_allowed and tool_name == "search":
        is_allowed = bool({"search", "search_knowledge", "read_doc"}.intersection(allowed_tools))

    if not is_allowed:
        is_ephemeral = (
            getattr(boundary, "scope_tier", None) == "ephemeral"
            or getattr(boundary, "execution_id", None) is not None
        )
        err_code = (
            McpErrorCode.EPHEMERAL_TOOL_FORBIDDEN
            if is_ephemeral
            else McpErrorCode.INSUFFICIENT_SCOPE
        )
        msg = (
            f"Tool '{tool_name}' is forbidden on ephemeral token"
            if is_ephemeral
            else f"Tool '{tool_name}' is not in allowed_tools for this credential"
        )
        hint = (
            "Ephemeral tokens are strictly read-only and allow at most: "
            "search_tickets, read_ticket, search."
            if is_ephemeral
            else "Tool narrowing is active; only tools in allowed_tools may be called."
        )
        raise KbMcpError(
            err_code,
            msg,
            allowed_tools=sorted(str(t) for t in allowed_tools),
            hint=hint,
        )


def _check_boundary_capability_mask(
    boundary: CredentialBoundary, tool_name: str, arguments: dict[str, Any]
) -> None:
    cap_mask = getattr(boundary, "capability_mask", None)
    if cap_mask is None:
        return
    legacy_full_mask = int(Capability.VIEW | Capability.COMMENT | Capability.EDIT)
    if getattr(boundary, "surface", None) == "admin" and int(cap_mask) == legacy_full_mask:
        return

    action_arg = arguments.get("action")
    req_cap = get_required_tool_capability(
        tool_name, str(action_arg) if action_arg is not None else None
    )
    if (int(cap_mask) & int(req_cap)) != int(req_cap):
        msg = (
            f"Tool '{tool_name}' requires capability {req_cap.name} ({int(req_cap)}), "
            f"which is masked out by capability_mask ({cap_mask})"
        )
        raise KbMcpError(
            McpErrorCode.INSUFFICIENT_SCOPE,
            msg,
            extra={
                "reason": "INSUFFICIENT_CAPABILITY",
                "required_capability": req_cap.name,
                "required_bit": int(req_cap),
                "capability_mask": int(cap_mask),
            },
            hint=f"Request an API key or token with {req_cap.name} capability bit enabled.",
        )


def _check_boundary_allowlists(boundary: CredentialBoundary, arguments: dict[str, Any]) -> None:
    ws_allow = getattr(boundary, "workspace_allowlist", None)
    if ws_allow:
        raw_ws = arguments.get("workspace") or arguments.get("workspace_id")
        target_ws = _as_uuid(raw_ws)
        if target_ws is not None and not boundary.allows_workspace(target_ws):
            msg = (
                f"Target workspace '{raw_ws}' is outside the allowed workspaces "
                "for this credential."
            )
            hint_ws = (
                "Connect to an allowed workspace or use a credential with appropriate permissions."
            )
            raise KbMcpError(
                McpErrorCode.KEY_SCOPE_VIOLATION,
                msg,
                extra={"allowed_workspaces": [str(w) for w in ws_allow]},
                hint=hint_ws,
            )

    proj_allow = getattr(boundary, "project_allowlist", None)
    if proj_allow:
        raw_proj = arguments.get("project") or arguments.get("project_id")
        if not raw_proj:
            ident = (
                arguments.get("identifier")
                or arguments.get("parent")
                or arguments.get("ticket")
                or arguments.get("id")
            )
            if ident and isinstance(ident, str):
                match = _ISSUE_KEY_REGEX.match(ident)
                if match:
                    raw_proj = match.group(1).upper()

        target_proj = _as_uuid(raw_proj)
        if target_proj is not None and not boundary.allows_project(target_proj):
            msg = (
                f"Target project '{raw_proj}' is outside the allowed projects for this credential."
            )
            raise KbMcpError(
                McpErrorCode.KEY_SCOPE_VIOLATION,
                msg,
                extra={"allowed_projects": [str(p) for p in proj_allow]},
                hint="Target an allowed project or use a credential with appropriate permissions.",
            )


def enforce_credential_boundary_on_tool_call(
    tool_name: str,
    arguments: dict[str, Any],
    boundary: CredentialBoundary | None,
) -> None:
    """Enforce CredentialBoundary before executing an MCP tool call."""
    if boundary is None:
        return

    _check_boundary_allowed_tools(boundary, tool_name)
    _check_boundary_capability_mask(boundary, tool_name, arguments)
    _check_boundary_allowlists(boundary, arguments)
