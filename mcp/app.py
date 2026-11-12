# Copyright 2026 Kanban Platform Contributors
"""Starlette ASGI application factory mounting isolated MCP surfaces."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from starlette.applications import Starlette
from starlette.routing import Mount, Route

from mcp.internal_client import KanbanApiClient
from mcp.protocol import InMemorySessionStore, McpProtocolHandler
from mcp.registry import Surface, ToolRegistry, create_placeholder_tool
from mcp.settings import McpSettings

if TYPE_CHECKING:
    from starlette.types import ASGIApp

__all__ = [
    "create_mcp_app",
]


def _build_surface_sub_app(
    handler: McpProtocolHandler,
) -> Starlette:
    """Build an independent sub-app for a single MCP surface."""
    return Starlette(
        routes=[
            Route("/", handler.handle_request, methods=["GET", "POST", "DELETE"]),
        ]
    )


def create_mcp_app(
    settings: McpSettings | None = None,
    *,
    kanban_app: ASGIApp | None = None,
    agent_registry: ToolRegistry | None = None,
    docs_registry: ToolRegistry | None = None,
    admin_registry: ToolRegistry | None = None,
) -> Starlette:
    """Construct Starlette application mounting exactly 3 isolated MCP surfaces.

    Mounts:
        - /mcp/agent
        - /mcp/docs
        - /mcp/admin
    """
    active_settings: Final[McpSettings] = settings or McpSettings()

    # Construct 3 independent registries
    active_agent_reg = agent_registry
    if active_agent_reg is None:
        active_agent_reg = ToolRegistry(Surface.AGENT)
        active_agent_reg.register(create_placeholder_tool(Surface.AGENT))
    if not active_agent_reg.is_frozen:
        active_agent_reg.freeze()

    active_docs_reg = docs_registry
    if active_docs_reg is None:
        active_docs_reg = ToolRegistry(Surface.DOCS)
        active_docs_reg.register(create_placeholder_tool(Surface.DOCS))
    if not active_docs_reg.is_frozen:
        active_docs_reg.freeze()

    active_admin_reg = admin_registry
    if active_admin_reg is None:
        active_admin_reg = ToolRegistry(Surface.ADMIN)
        active_admin_reg.register(create_placeholder_tool(Surface.ADMIN))
    if not active_admin_reg.is_frozen:
        active_admin_reg.freeze()

    # Shared session store across mounts
    session_store: Final[InMemorySessionStore] = InMemorySessionStore(
        ttl_s=active_settings.session_ttl_s,
        max_sessions=active_settings.max_sessions,
    )

    # Internal API client
    active_kanban_app = kanban_app
    if active_kanban_app is None and active_settings.mode == "standalone_inprocess":
        active_kanban_app = Starlette()

    internal_client: Final[KanbanApiClient] = KanbanApiClient(
        active_settings,
        kanban_app=active_kanban_app,
    )

    # Protocol handlers
    agent_handler: Final[McpProtocolHandler] = McpProtocolHandler(
        Surface.AGENT,
        active_agent_reg,
        session_store,
        active_settings,
        internal_client=internal_client,
    )
    docs_handler: Final[McpProtocolHandler] = McpProtocolHandler(
        Surface.DOCS,
        active_docs_reg,
        session_store,
        active_settings,
        internal_client=internal_client,
    )
    admin_handler: Final[McpProtocolHandler] = McpProtocolHandler(
        Surface.ADMIN,
        active_admin_reg,
        session_store,
        active_settings,
        internal_client=internal_client,
    )

    # Sub-apps
    agent_app = _build_surface_sub_app(agent_handler)
    docs_app = _build_surface_sub_app(docs_handler)
    admin_app = _build_surface_sub_app(admin_handler)

    routes = [
        # Explicit direct routes for /mcp/<surface>
        Route("/mcp/agent", agent_handler.handle_request, methods=["GET", "POST", "DELETE"]),
        Route("/mcp/docs", docs_handler.handle_request, methods=["GET", "POST", "DELETE"]),
        Route("/mcp/admin", admin_handler.handle_request, methods=["GET", "POST", "DELETE"]),
        # Mounts for sub-path routing
        Mount("/mcp/agent", app=agent_app),
        Mount("/mcp/docs", app=docs_app),
        Mount("/mcp/admin", app=admin_app),
    ]

    app = Starlette(routes=routes)

    # Attach references to app state
    app.state.settings = active_settings
    app.state.session_store = session_store
    app.state.internal_client = internal_client
    app.state.agent_registry = agent_registry
    app.state.docs_registry = docs_registry
    app.state.admin_registry = admin_registry

    return app
