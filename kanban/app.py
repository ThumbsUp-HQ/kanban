"""ASGI application factory for the Kanban platform.

Mounts API routes, WebSocket rejection gates, SSE/MCP placeholder endpoints,
pre-compressed single page application static assets, and security middleware.
"""

from __future__ import annotations

import importlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Final

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, FastAPI, Request, Response, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import HTMLResponse, RedirectResponse

from database.session import RLSSessionFactory
from kanban.api.deps import DenyAllResolver
from kanban.api.internal.mcp_ephemeral import router as mcp_ephemeral_router
from kanban.api.internal.mcp_introspect import router as mcp_introspect_router
from kanban.api.middleware.script_depth import ScriptDepthGuardMiddleware
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
from kanban.api.v1.oauth import OAuth2Error, oauth_root_router
from kanban.api.ws import handle_ws_connection
from kanban.api_docs import (
    DOCS_CSS,
    MANIFEST_BYTES,
    get_redoc_html,
    get_swagger_ui_html,
)
from kanban.auth.identity_service import DatabaseIdentityResolver
from kanban.auth.sessions.csrf import CsrfMiddleware
from kanban.auth.sessions.resolver import SessionCookieResolver
from kanban.auth.sessions.service import SessionService
from kanban.auth.setup import mint_setup_token_if_uninitialized
from kanban.jobs import JobScheduler
from kanban.jobs import registry as jobs_registry
from kanban.logging import configure_logging
from kanban.sandbox.nsjail_runner import TierBNsjailRunner
from kanban.security.envelope import StaticKekProvider
from kanban.security.headers import SecurityHeadersMiddleware
from kanban.security.keys import load_key_material
from kanban.services.notifications import register_notifications_listener
from kanban.settings import Settings
from kanban.web_static import PrecompressedSPAStaticApp

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncEngine
    from starlette.types import ASGIApp, Receive, Scope, Send

    from mcp.settings import McpSettings

_FAVICON_SVG: Final[str] = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
    '<text y=".9em" font-size="90">👍</text></svg>'
)


def _mount_api_docs_and_manifest(app: FastAPI) -> None:
    """Mount OpenAPI redirect, web manifest, and interactive API doc routes."""

    @app.api_route("/openapi.json", methods=["GET", "HEAD"], include_in_schema=False)
    async def openapi_redirect() -> RedirectResponse:
        return RedirectResponse(url="/api/openapi.json", status_code=307)

    @app.get("/manifest.json", include_in_schema=False)
    @app.get("/manifest.webmanifest", include_in_schema=False)
    async def manifest_endpoint() -> Response:
        return Response(
            content=MANIFEST_BYTES,
            media_type="application/manifest+json",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    @app.get("/api/docs/docs.css", include_in_schema=False)
    async def api_docs_css_endpoint() -> Response:
        return Response(
            content=DOCS_CSS.encode("utf-8"),
            media_type="text/css; charset=utf-8",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    @app.get("/api/docs", include_in_schema=False)
    async def swagger_ui_endpoint(request: Request) -> HTMLResponse:
        return HTMLResponse(
            content=get_swagger_ui_html(request.app.openapi()),
            status_code=200,
            headers={"Cache-Control": "public, max-age=3600"},
        )

    @app.get("/api/redoc", include_in_schema=False)
    async def redoc_endpoint(request: Request) -> HTMLResponse:
        return HTMLResponse(
            content=get_redoc_html(request.app.openapi()),
            status_code=200,
            headers={"Cache-Control": "public, max-age=3600"},
        )


async def verify_schema_head(session_factory: RLSSessionFactory) -> None:
    """Verify that database schema head matches code Alembic migration head."""
    ini_candidates = [Path("alembic.ini"), Path("database/alembic.ini")]
    ini_file = next((p for p in ini_candidates if p.is_file()), None)
    if not ini_file:
        return

    try:
        cfg = Config(str(ini_file))
        script = ScriptDirectory.from_config(cfg)
        code_heads = set(script.get_heads())
        if not code_heads:
            return

        engine = getattr(session_factory, "_engine", None)
        if engine is None:
            return

        db_heads: set[str] = set()
        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT version_num FROM alembic_version"))
            rows = res.fetchall()
            db_heads = {str(row[0]) for row in rows}

        if not code_heads.issubset(db_heads):
            logger.error(
                "❌ Database schema is out of date: database head %s is behind code head %s. "
                "Run migrations before starting the application.",
                db_heads or "none",
                code_heads,
            )
        else:
            logger.info("Database schema head verified: %s", db_heads)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Database schema head check skipped or failed: %s", exc)


def _bootstrap_runtime_state(app: FastAPI) -> AsyncEngine | None:
    """Initialize RLSSessionFactory and auth state from settings when not pre-configured."""
    app_settings = getattr(app.state, "settings", None)
    if (
        getattr(app.state, "session_factory", None) is not None
        or app_settings is None
        or not app_settings.database_url
    ):
        return None

    try:
        km = getattr(app.state, "key_material", None) or load_key_material()
        engine = create_async_engine(
            app_settings.database_url,
            pool_size=10,
            max_overflow=10,
        )
        session_factory = RLSSessionFactory(engine)
        app.state.engine = engine
        app.state.session_factory = session_factory
        app.state.key_material = km
        if getattr(app.state, "kek_provider", None) is None:
            app.state.kek_provider = StaticKekProvider(
                {km.master_kek_kid: km.master_kek},
                km.master_kek_kid,
            )
        if getattr(app.state, "session_service", None) is None:
            app.state.session_service = SessionService(session_hmac_key=km.session_hmac_key)
        if isinstance(getattr(app.state, "principal_resolver", None), DenyAllResolver):
            app.state.principal_resolver = SessionCookieResolver(
                app.state.session_service,
                session_factory,
            )
    except Exception:
        logger.debug("Automatic runtime database/auth wiring skipped", exc_info=True)
        return None
    else:
        return engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application lifespan, starting background workers and draining on shutdown."""
    hub = getattr(app.state, "realtime_hub", None)
    if hub is not None:
        await hub.start()

    scheduler = JobScheduler(jobs_registry)
    app.state.job_scheduler = scheduler
    app.state.job_registry = jobs_registry

    owned_engine = _bootstrap_runtime_state(app)
    session_target = getattr(app.state, "session_factory", None)
    should_run = getattr(app.state, "enable_background_jobs", False)

    if session_target is not None:
        try:
            await verify_schema_head(session_target)
        except Exception:
            logger.debug("Startup schema-head check skipped or failed", exc_info=True)
        try:
            key_material = getattr(app.state, "key_material", None)
            app_settings = getattr(app.state, "settings", None)
            await mint_setup_token_if_uninitialized(
                session_target,
                key_material=key_material,
                settings=app_settings,
            )
        except Exception:
            logger.debug("First-boot setup token check bypassed or failed", exc_info=True)

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
        if owned_engine is not None:
            await owned_engine.dispose()


def _mount_mcp_surfaces(app: FastAPI, mcp_settings: McpSettings | None = None) -> None:
    """Mount live MCP surfaces and RFC 9728 protected-resource metadata endpoints."""
    mcp_app = getattr(app.state, "mcp_app", None)
    if mcp_app is None:
        try:
            mcp_app_mod = importlib.import_module("mcp.app")
            mcp_settings_mod = importlib.import_module("mcp.settings")
            create_mcp_app = mcp_app_mod.create_mcp_app
            mcp_settings_cls = mcp_settings_mod.McpSettings

            active_settings = (
                mcp_settings
                if mcp_settings is not None
                else mcp_settings_cls(mode="standalone_inprocess", auth_enabled=True)
            )
            mcp_app = create_mcp_app(active_settings, kanban_app=app)
            app.state.mcp_app = mcp_app
        except Exception:
            logger.debug("Automatic live MCP application mounting skipped", exc_info=True)
            return

    class _McpProxyApp:
        """ASGI proxy forwarding requests to the live MCP Starlette application."""

        def __init__(self, owner_app: FastAPI, default_target: ASGIApp) -> None:
            self._owner_app = owner_app
            self._default_target = default_target

        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            target = getattr(self._owner_app.state, "mcp_app", None) or self._default_target
            if scope["type"] == "http":
                scope_copy = dict(scope)
                path = scope.get("path", "")
                root_path = scope.get("root_path", "")
                if root_path and not path.startswith(root_path):
                    path = root_path + path
                scope_copy["path"] = path
                scope_copy["root_path"] = ""
                await target(scope_copy, receive, send)
            else:
                await target(scope, receive, send)

    proxy = _McpProxyApp(app, mcp_app)
    app.mount("/.well-known/oauth-protected-resource", proxy)
    app.mount("/mcp", proxy)


def create_app(
    settings: Settings | None = None,
    mcp_settings: McpSettings | None = None,
) -> FastAPI:
    """Create and configure the canonical Kanban ASGI FastAPI application."""
    configure_logging()
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
    app.state.identity_resolver = DatabaseIdentityResolver()
    app.state.session_factory = None
    app.state.session_service = None
    app.state.broker = None
    app.state.realtime_hub = None
    app.state.tier_b_runner = TierBNsjailRunner()

    # Register RFC 7807 problem exception handlers
    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, starlette_http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)

    @app.exception_handler(OAuth2Error)
    async def oauth2_error_handler(request: Request, exc: OAuth2Error) -> JSONResponse:
        logger.warning(
            "OAuth2Error [%s / %d] on %s %s: %s",
            exc.error,
            exc.status_code,
            request.method,
            request.url.path,
            exc.description,
        )
        return JSONResponse(
            {"error": exc.error, "error_description": exc.description},
            status_code=exc.status_code,
            headers=exc.headers,
        )

    # Mount canonical /api/v1 router tree
    app.include_router(build_v1_router(), prefix="/api/v1")
    app.include_router(mcp_introspect_router)
    app.include_router(mcp_ephemeral_router)
    app.include_router(oauth_root_router)

    # Register activity listener for notifications and auto-subscriptions
    register_notifications_listener()

    # Mount OpenAPI redirect, web manifest, and interactive API documentation routes
    _mount_api_docs_and_manifest(app)

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

    # RFC 9728 Protected-Resource Metadata
    @app.get("/.well-known/oauth-protected-resource", include_in_schema=False)
    @app.get("/.well-known/oauth-protected-resource/{subpath:path}", include_in_schema=False)
    async def oauth_protected_resource_endpoint(
        request: Request, subpath: str | None = None
    ) -> Response:
        del subpath
        mcp_meta = importlib.import_module("mcp.metadata")
        resp: Response = await mcp_meta.protected_resource_metadata_endpoint(request)
        return resp

    # Serve favicon.ico with 200 OK and Cache-Control
    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon_endpoint() -> Response:
        return Response(
            content=_FAVICON_SVG.encode("utf-8"),
            media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    # Mount live MCP surfaces and RFC 9728 metadata endpoints
    _mount_mcp_surfaces(app, mcp_settings)

    # SPA Static assets mounted at root
    app.mount("/", PrecompressedSPAStaticApp(dist_dir=settings.web_dist))

    # Add CSRF protection middleware for unsafe API methods
    app.add_middleware(CsrfMiddleware)

    # Add RequestIdMiddleware so request-id is available inside all routes and middleware
    app.add_middleware(RequestIdMiddleware)

    # Add script recursion depth guard middleware
    app.add_middleware(ScriptDepthGuardMiddleware)

    # Add security headers and host protection middleware
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)

    return app
