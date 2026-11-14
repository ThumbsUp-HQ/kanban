# Copyright 2026 Kanban Platform Contributors
"""Starlette ASGI application factory mounting isolated MCP surfaces."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from starlette.applications import Starlette
from starlette.routing import Mount, Route

from mcp.auth import McpAuthMiddleware
from mcp.internal_client import KanbanApiClient
from mcp.metadata import protected_resource_metadata_endpoint
from mcp.protocol import InMemorySessionStore, McpProtocolHandler
from mcp.registry import Surface, ToolRegistry, create_placeholder_tool
from mcp.settings import McpSettings
from mcp.surfaces.docs import build_docs_registry

if TYPE_CHECKING:
    import httpx
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


def create_mcp_app(  # noqa: PLR0913
    settings: McpSettings | None = None,
    *,
    kanban_app: ASGIApp | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    internal_client: KanbanApiClient | None = None,
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

    # Shared session store across mounts
    session_store: Final[InMemorySessionStore] = InMemorySessionStore(
        ttl_s=active_settings.session_ttl_s,
        max_sessions=active_settings.max_sessions,
    )

    # Internal API client
    active_kanban_app = kanban_app
    in_process = active_settings.mode == "standalone_inprocess"
    if active_kanban_app is None and in_process and transport is None:
        active_kanban_app = Starlette()

    active_internal_client = internal_client
    if active_internal_client is None:
        active_internal_client = KanbanApiClient(
            active_settings,
            kanban_app=active_kanban_app,
            transport=transport,
        )

    # Construct 3 independent registries
    active_agent_reg = agent_registry
    if active_agent_reg is None:
        active_agent_reg = ToolRegistry(Surface.AGENT)
        active_agent_reg.register(create_placeholder_tool(Surface.AGENT))
    if not active_agent_reg.is_frozen:
        active_agent_reg.freeze()

    active_docs_reg = docs_registry
    if active_docs_reg is None:
        active_docs_reg = build_docs_registry(active_internal_client)
    elif not active_docs_reg.is_frozen:
        active_docs_reg.freeze()

    active_admin_reg = admin_registry
    if active_admin_reg is None:
        active_admin_reg = ToolRegistry(Surface.ADMIN)
        active_admin_reg.register(create_placeholder_tool(Surface.ADMIN))
    if not active_admin_reg.is_frozen:
        active_admin_reg.freeze()

    # Protocol handlers
    agent_handler: Final[McpProtocolHandler] = McpProtocolHandler(
        Surface.AGENT,
        active_agent_reg,
        session_store,
        active_settings,
        internal_client=active_internal_client,
    )
    docs_handler: Final[McpProtocolHandler] = McpProtocolHandler(
        Surface.DOCS,
        active_docs_reg,
        session_store,
        active_settings,
        internal_client=active_internal_client,
    )
    admin_handler: Final[McpProtocolHandler] = McpProtocolHandler(
        Surface.ADMIN,
        active_admin_reg,
        session_store,
        active_settings,
        internal_client=active_internal_client,
    )

    # Sub-apps
    agent_app = _build_surface_sub_app(agent_handler)
    docs_app = _build_surface_sub_app(docs_handler)
    admin_app = _build_surface_sub_app(admin_handler)

    routes = [
        # RFC 9728 Protected-Resource Metadata
        Route(
            "/.well-known/oauth-protected-resource/mcp/{surface}",
            protected_resource_metadata_endpoint,
            methods=["GET"],
        ),
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
    app.state.internal_client = active_internal_client
    app.state.agent_registry = active_agent_reg
    app.state.docs_registry = active_docs_reg
    app.state.admin_registry = active_admin_reg

    if active_settings.auth_enabled:
        app.add_middleware(
            McpAuthMiddleware,
            internal_client=active_internal_client,
            settings=active_settings,
        )

    return app
