# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Dynamic MCP Connection Scoping: Global, Workspace, and Project (KB-P4-15, S11.1)."""

from __future__ import annotations

import contextlib
import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final

from mcp.errors import KbMcpError, McpErrorCode

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mcp.auth import McpAuthContext

__all__ = [
    "ConnectionScope",
    "ScopeMode",
    "compute_session_fingerprint",
    "enforce_connection_scope_on_tool_call",
    "intersect_key_and_connection_scope",
    "parse_connection_scope",
]

_PATH_WORKSPACE_RE: Final[re.Pattern[str]] = re.compile(
    r"/w/(?P<workspace>[a-zA-Z0-9_-]+)(?:/p/(?P<project>[A-Z][A-Z0-9]{0,9}))?"
)
_ISSUE_KEY_REGEX: Final[re.Pattern[str]] = re.compile(r"^([A-Z][A-Z0-9]{0,9})-([0-9]+)$")


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
        if token_tier == "global" or not token_ws:  # noqa: S105
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
        has_boundary = bool(auth_ctx.workspace_slug or auth_ctx.workspace_id)
        if token_tier != "global" and has_boundary and not ws_match:  # noqa: S105
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
        has_boundary = bool(auth_ctx.workspace_slug or auth_ctx.workspace_id)
        if token_tier != "global" and has_boundary and not ws_match:  # noqa: S105
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
