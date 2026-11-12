"""ASGI application factory for the Kanban platform.

Mounts API routes, WebSocket rejection gates, SSE/MCP placeholder endpoints,
pre-compressed single page application static assets, and security middleware.
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI, WebSocket
from fastapi.responses import JSONResponse

from kanban.security.headers import SecurityHeadersMiddleware
from kanban.settings import Settings
from kanban.web_static import PrecompressedSPAStaticApp


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the canonical Kanban ASGI FastAPI application."""
    if settings is None:
        settings = Settings()

    app = FastAPI(
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    # API Router
    api_router = APIRouter(prefix="/api")

    @api_router.get("/v1/health")
    async def health_check() -> dict[str, str]:
        return {"status": "ok"}

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

    # WebSocket route: closes with code 1008 immediately before accept
    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket) -> None:
        await websocket.close(code=1008)

    # Server-Sent Events placeholder: 501 Not Implemented
    @app.get("/sse", include_in_schema=False)
    async def sse_endpoint() -> JSONResponse:
        return JSONResponse(
            status_code=501,
            content={
                "type": "about:blank",
                "title": "Not Implemented",
                "status": 501,
            },
            media_type="application/problem+json",
        )

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

    # Add security headers and host protection middleware
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)

    return app
