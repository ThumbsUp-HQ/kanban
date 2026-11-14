# Copyright 2026 Kanban Platform Contributors
"""JIT (Just-In-Time) progressive disclosure help builder (S11.1)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from mcp.errors import KbMcpError

if TYPE_CHECKING:
    from mcp.internal_client import KanbanApiClient

__all__ = [
    "build_help",
]

_logger = logging.getLogger(__name__)

_TOOL_PARAM_DEFAULTS: dict[str, dict[str, str]] = {
    "update_ticket": {"identifier": "KAN-142 | uuid", "description_mode": "append | replace"},
    "read_ticket": {"identifier": "KAN-142 | uuid", "lod": "summary | standard | full"},
    "create_ticket": {
        "project": "KAN",
        "summary": "str",
        "priority": "urgent | high | medium | low | none",
    },
    "search_tickets": {"query": "str", "project": "KAN", "lod": "summary | standard | full"},
    "begin_work": {"identifier": "KAN-142 | uuid"},
    "transition_ticket": {"identifier": "KAN-142 | uuid", "state": "str"},
    "ping_agent": {"action": "ping | help | echo", "message": "str"},
    "configure_workspace": {"action": "get | update | help", "settings": "object"},
    "manage_auth_cards": {
        "action": (
            "list | get | create | update | enable | disable | reorder | "
            "test_handshake | delete | help"
        ),
        "card": "slug | uuid",
    },
    "destructive_lifecycle": {
        "action": "request_delete | execute_delete | restore | help",
        "target_kind": "issue | project | doc | page | sticky | cycle | module | view",
        "target": "identifier | uuid",
        "mode": "trash | permanent_purge",
        "confirmation_token": "str",
        "confirm_phrase": "str",
        "reason": "str",
    },
}


async def _resolve_live_metadata(
    client: KanbanApiClient,
    project: str,
    subject_token: str | None,
    mcp_session_id: str | None,
) -> tuple[str, dict[str, Any]]:
    """Resolve project key and query live project metadata if available."""
    proj_key = project
    meta: dict[str, Any] = {}
    try:
        resolved = await client.request(
            "GET",
            "/api/v1/resolve",
            params={"kind": "project", "ref": project},
            subject_token=subject_token,
            mcp_session_id=mcp_session_id,
        )
        if isinstance(resolved, dict) and "key" in resolved:
            proj_key = str(resolved["key"])
    except (KbMcpError, RuntimeError, ValueError, OSError, TimeoutError, KeyError) as exc:
        _logger.debug("Failed to resolve project key for JIT help: %s", exc)

    try:
        fetched = await client.request(
            "GET",
            f"/api/v1/projects/{proj_key}",
            subject_token=subject_token,
            mcp_session_id=mcp_session_id,
        )
        if isinstance(fetched, dict):
            meta = fetched
    except (KbMcpError, RuntimeError, ValueError, OSError, TimeoutError, KeyError) as exc:
        _logger.debug("Upstream project metadata unavailable for %s: %s", proj_key, exc)

    return proj_key, meta


def _populate_project_attributes(doc: dict[str, Any], meta: dict[str, Any]) -> None:
    """Populate live workflow attributes into help document without inventing values."""
    for field in ("states", "priorities", "labels", "cycles"):
        if field in meta and meta[field] is not None:
            doc[field] = meta[field]

    modules_enabled = meta.get("modules_enabled", True)
    if modules_enabled is not False and "modules" in meta and meta["modules"] is not None:
        doc["modules"] = meta["modules"]

    doc["custom_fields"] = meta.get("custom_fields", [])
    doc["agents"] = meta.get("agents", [])


async def build_help(  # noqa: PLR0913
    tool_name: str,
    *,
    project: str | None = None,
    client: KanbanApiClient | None = None,
    subject_token: str | None = None,
    mcp_session_id: str | None = None,
    project_metadata: dict[str, Any] | None = None,
    params_summary: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build live project data and parameter summary dictionary for JIT help."""
    help_doc: dict[str, Any] = {"tool": tool_name}
    meta: dict[str, Any] = {}

    if project_metadata is not None:
        meta = project_metadata
        help_doc["project"] = project or str(meta.get("key") or "KAN")
    elif project is not None:
        if client is not None:
            proj_key, meta = await _resolve_live_metadata(
                client, project, subject_token, mcp_session_id
            )
            help_doc["project"] = proj_key
        else:
            help_doc["project"] = project

    _populate_project_attributes(help_doc, meta)

    params = params_summary or _TOOL_PARAM_DEFAULTS.get(tool_name)
    if params:
        help_doc["params"] = params

    return help_doc
