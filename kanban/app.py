"""ASGI application factory for the Kanban platform.

Mounts API routes, WebSocket rejection gates, SSE/MCP placeholder endpoints,
pre-compressed single page application static assets, and security middleware.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import APIRouter, FastAPI, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from kanban.api.deps import DenyAllResolver
from kanban.api.internal.mcp_introspect import router as mcp_introspect_router
from kanban.api.problems import (
    ProblemException,
    problem_exception_handler,
    starlette_http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from kanban.api.request_id import RequestIdMiddleware
from kanban.api.sse import handle_sse_endpoint
from kanban.api.v1 import build_v1_router
from kanban.api.ws import handle_ws_connection
from kanban.auth.sessions.csrf import CsrfMiddleware
from kanban.jobs import JobScheduler
from kanban.jobs import registry as jobs_registry
from kanban.security.headers import SecurityHeadersMiddleware
from kanban.services.notifications import register_notifications_listener
from kanban.settings import Settings
from kanban.web_static import PrecompressedSPAStaticApp

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from starlette.responses import Response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application lifespan, starting background workers and draining on shutdown."""
    hub = getattr(app.state, "realtime_hub", None)
    if hub is not None:
        await hub.start()

    scheduler = JobScheduler(jobs_registry)
    app.state.job_scheduler = scheduler
    app.state.job_registry = jobs_registry

    session_target = getattr(app.state, "session_factory", None)
    should_run = getattr(app.state, "enable_background_jobs", False)

    if should_run and session_target is not None:
        await scheduler.start(session_target)

    try:
        yield
    finally:
        if should_run and session_target is not None:
            await scheduler.stop()
        hub = getattr(app.state, "realtime_hub", None)
        if hub is not None:
            await hub.drain(timeout_seconds=3.0)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the canonical Kanban ASGI FastAPI application."""
    if settings is None:
        settings = Settings()

    app = FastAPI(
        title="👍kanban API",
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # Initialize default state dependencies
    app.state.settings = settings
    app.state.principal_resolver = DenyAllResolver()
    app.state.session_factory = None
    app.state.session_service = None
    app.state.broker = None
    app.state.realtime_hub = None

    # Register RFC 7807 problem exception handlers
    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, starlette_http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # Mount canonical /api/v1 router tree
    app.include_router(build_v1_router(), prefix="/api/v1")
    app.include_router(mcp_introspect_router)

    # Register activity listener for notifications and auto-subscriptions
    register_notifications_listener()

    # Fallback API router for legacy/subpath 404s
    api_router = APIRouter(prefix="/api")

    @api_router.api_route(
        "/{full_path:path}",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
        include_in_schema=False,
    )
    async def api_not_found(full_path: str) -> JSONResponse:
        del full_path
        return JSONResponse(
            status_code=404,
            content={
                "type": "about:blank",
                "title": "Not Found",
                "status": 404,
            },
            media_type="application/problem+json",
        )

    app.include_router(api_router)

    # Authenticated WebSocket realtime endpoint (/ws)
    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket) -> None:
        await handle_ws_connection(websocket)

    # Authenticated Server-Sent Events endpoint (/sse)
    @app.get("/sse", include_in_schema=False)
    async def sse_endpoint(request: Request) -> Response:
        return await handle_sse_endpoint(request)

    # MCP placeholders (/mcp/agent, /mcp/docs, /mcp/admin and subpaths): 501 Not Implemented
    @app.api_route(
        "/mcp/{surface:path}",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
        include_in_schema=False,
    )
    async def mcp_placeholder(surface: str) -> JSONResponse:
        del surface
        return JSONResponse(
            status_code=501,
            content={
                "type": "about:blank",
                "title": "Not Implemented",
                "status": 501,
            },
            media_type="application/problem+json",
        )

    # SPA Static assets mounted at root
    app.mount("/", PrecompressedSPAStaticApp(dist_dir=settings.web_dist))

    # Add CSRF protection middleware for unsafe API methods
    app.add_middleware(CsrfMiddleware)

    # Add RequestIdMiddleware so request-id is available inside all routes and middleware
    app.add_middleware(RequestIdMiddleware)

    # Add security headers and host protection middleware
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)

    return app
