# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Security model contract test verifying route classification and security guards (KAN-320).

Validates that:
1. 100% of routes across create_app, create_internal_app, create_mcp_app, and create_agent_app
   are classified into an explicit entry-point tier (E1..E8).
2. 100% of administrative routes (/api/v1/admin/*) enforce require_admin_aal2.
3. 100% of internal service routes (/internal/*) enforce verify_internal_service_auth.
4. Complete Asset Matrix (A1..A6) and Entry Point Catalog (E1..E8) are documented in
   docs/SECURITY.md and thumbs-up-kanban.wiki/Security-and-STRIDE-Threat-Matrix.md.
5. Negative and boundary cases (unclassified routes, unguarded admin routes) fail closed.
"""

from __future__ import annotations

import enum
import inspect
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

import pytest
from fastapi import APIRouter, FastAPI
from starlette.routing import Mount, Route

from agent.asgi import create_agent_app
from kanban.app import create_app, create_internal_app
from kanban.auth.mfa.policy import assert_admin_routes_protected
from mcp.app import create_mcp_app

if TYPE_CHECKING:
    from starlette.types import ASGIApp


class EntrypointTier(enum.StrEnum):
    """Authoritative entry-point and trust boundary tiers (E1..E8)."""

    E1_REVERSE_PROXY = "E1"
    E2_PUBLIC_REST_API = "E2"
    E3_INTERNAL_SERVICE_API = "E3"
    E4_REALTIME_CHANNELS = "E4"
    E5_MCP_GATEWAY = "E5"
    E6_SANDBOX_HARNESS = "E6"
    E7_MEDIA_IMPORTER_EXPORTER = "E7"
    E8_OPERATOR_AGENT_CLI = "E8"


def extract_all_routes(
    app_or_router: ASGIApp | object,
    prefix: str = "",
) -> list[tuple[str, list[str], object]]:
    """Recursively extract flattened (path, methods, route_obj) from Starlette applications."""
    extracted: list[tuple[str, list[str], object]] = []
    routes = getattr(app_or_router, "routes", [])

    for r in routes:
        path = getattr(r, "path", "")
        # Starlette Mount with sub-app
        if isinstance(r, Mount):
            mount_path = prefix + path if not path.startswith(prefix) else path
            sub_routes = extract_all_routes(r.app, mount_path.rstrip("/"))
            extracted.extend(sub_routes)
        # FastAPI _IncludedRouter with effective_route_contexts
        elif hasattr(r, "effective_route_contexts") and callable(r.effective_route_contexts):
            for ctx in r.effective_route_contexts():
                ctx_path = getattr(ctx, "path", "")
                methods = list(getattr(ctx, "methods", []))
                extracted.append((ctx_path, methods, ctx))
        # Nested router with sub-routes
        elif hasattr(r, "routes"):
            extracted.extend(extract_all_routes(r, prefix))
        else:
            methods = list(getattr(r, "methods", []))
            full_path = prefix + path if not path.startswith(prefix) else path
            extracted.append((full_path, methods, r))

    return extracted


def classify_route(path: str, methods: list[str] | None = None) -> EntrypointTier:
    """Classify any mounted route path into an authoritative entry-point tier (E1..E8).

    Raises ValueError if the path does not belong to an approved classification pattern.
    """
    del methods
    p = path.strip()

    # E3: Dedicated Internal Service ASGI App
    if p.startswith(("/internal", "/internal/")):
        return EntrypointTier.E3_INTERNAL_SERVICE_API

    # E4: Realtime Multiplexers & Runner Channels
    realtime_paths = ("/ws", "/api/v1/ws", "/sse", "/api/v1/agent-runners/ws")
    if p in realtime_paths or p.startswith("/api/v1/runners/ws"):
        return EntrypointTier.E4_REALTIME_CHANNELS

    # E5: 3-Surface Model Context Protocol (MCP) Gateway
    if p == "/mcp" or p.startswith(("/mcp/", "/.well-known/oauth-protected-resource")):
        return EntrypointTier.E5_MCP_GATEWAY

    # E7: Media Proxy, Attachments, Importers & Exporters
    e7_prefixes = (
        "/api/v1/media-proxy",
        "/api/v1/admin/imports",
        "/api/v1/admin/exports",
        "/api/v1/reports",
    )
    if p.startswith(e7_prefixes) or "/attachments" in p or "/report-templates" in p:
        return EntrypointTier.E7_MEDIA_IMPORTER_EXPORTER

    # E2: Primary Public Web & REST ASGI Application
    meta_paths = (
        "/api/openapi.json",
        "/openapi.json",
        "/manifest.webmanifest",
        "/manifest.json",
        "/api/redoc",
        "/favicon.ico",
        "/api/{full_path:path}",
        "/",
        "",
    )
    e2_prefixes = (
        "/api/v1/",
        "/oauth",
        "/api/docs",
        "/llms",
        "/.well-known/openid-configuration",
        "/.well-known/oauth-authorization-server",
    )
    if p.startswith(e2_prefixes) or p in meta_paths:
        return EntrypointTier.E2_PUBLIC_REST_API

    msg = f"Unclassified route path outside security model catalog: {path}"
    raise ValueError(msg)


class RouteAuditReport(TypedDict):
    """Structured report returned by audit_security_model_routes."""

    total_routes: int
    classified_counts: dict[str, int]
    unclassified_routes: list[str]
    unprotected_admin_routes: list[str]


def audit_security_model_routes(app: object) -> RouteAuditReport:
    """Audit all mounted routes in an ASGI app, classifying each and verifying guards."""
    routes = extract_all_routes(app)
    classified: dict[str, int] = {tier.value: 0 for tier in EntrypointTier}
    unclassified: list[str] = []

    for path, methods, _route_obj in routes:
        try:
            tier = classify_route(path, methods)
            classified[tier.value] += 1
        except ValueError:
            unclassified.append(path)

    return {
        "total_routes": len(routes),
        "classified_counts": classified,
        "unclassified_routes": unclassified,
        "unprotected_admin_routes": assert_admin_routes_protected(app),
    }


def test_create_app_routes_100_percent_classified() -> None:
    """Positive test: Introspects create_app and asserts 100% of routes are classified."""
    app = create_app()
    report = audit_security_model_routes(app)
    unclassified = report["unclassified_routes"]
    unprotected = report["unprotected_admin_routes"]
    counts = report["classified_counts"]
    assert isinstance(counts, dict)

    assert report["total_routes"] > 0, "create_app returned zero routes"
    assert unclassified == [], f"Found unclassified routes in create_app: {unclassified}"
    assert counts["E2"] > 0, "No E2 Public REST routes found"
    assert counts["E4"] > 0, "No E4 Realtime routes found"
    assert counts["E5"] > 0, "No E5 MCP Gateway routes found"
    assert counts["E7"] > 0, "No E7 Media/Attachment/Import routes found"
    assert unprotected == [], f"Unprotected admin routes: {unprotected}"


def test_create_internal_app_routes_100_percent_classified() -> None:
    """Positive test: Introspects create_internal_app and asserts 100% are E3 internal routes."""
    internal_app = create_internal_app()
    report = audit_security_model_routes(internal_app)
    counts = report["classified_counts"]
    assert isinstance(counts, dict)

    assert report["total_routes"] > 0, "create_internal_app returned zero routes"
    assert report["unclassified_routes"] == [], "Found unclassified internal routes"
    assert counts["E3"] == report["total_routes"], "Expected all internal routes to be E3"


def test_create_mcp_app_routes_100_percent_classified() -> None:
    """Positive test: Introspects create_mcp_app and asserts 100% are E5 MCP Gateway routes."""
    mcp_app = create_mcp_app()
    report = audit_security_model_routes(mcp_app)
    counts = report["classified_counts"]
    assert isinstance(counts, dict)

    assert report["total_routes"] > 0, "create_mcp_app returned zero routes"
    assert report["unclassified_routes"] == [], "Found unclassified MCP routes"
    assert counts["E5"] == report["total_routes"], "Expected all MCP routes to be E5"


def test_create_agent_app_routes_100_percent_classified() -> None:
    """Positive test: Introspects create_agent_app and asserts all routes are classified."""
    agent_app = create_agent_app()
    report = audit_security_model_routes(agent_app)
    unclassified = report["unclassified_routes"]
    unprotected = report["unprotected_admin_routes"]

    assert report["total_routes"] > 0, "create_agent_app returned zero routes"
    assert unclassified == [], f"Found unclassified agent routes: {unclassified}"
    assert unprotected == [], f"Unprotected admin routes in agent_app: {unprotected}"


def test_all_admin_routes_enforce_require_admin_aal2() -> None:
    """Positive test: Every /api/v1/admin/* route must declare Depends(require_admin_aal2)."""
    app = create_app()
    unprotected = assert_admin_routes_protected(app)
    assert unprotected == [], f"Found administrative routes lacking AAL2: {unprotected}"


def test_all_internal_routes_enforce_verify_internal_service_auth() -> None:
    """Positive test: Every /internal/* endpoint enforces verify_internal_service_auth."""
    internal_app = create_internal_app()
    routes = extract_all_routes(internal_app)

    assert len(routes) > 0, "Zero internal routes found"
    for path, _methods, route_obj in routes:
        protected = False
        dependant = getattr(route_obj, "dependant", None)
        if dependant is not None:
            for dep in getattr(dependant, "dependencies", []):
                call_fn = getattr(dep, "call", None)
                if call_fn is not None and "verify_internal_service_auth" in inspect.getsource(
                    call_fn
                ):
                    protected = True
                    break
        endpoint = getattr(route_obj, "endpoint", None)
        if endpoint is not None and "verify_internal_service_auth" in inspect.getsource(endpoint):
            protected = True
        assert protected, f"Internal endpoint for {path} does not call verify_internal_service_auth"


def test_docs_and_wiki_contain_all_asset_and_entrypoint_tiers() -> None:
    """Positive test: Verifies docs/SECURITY.md and wiki contain all Asset and Entry Point tiers."""
    repo_root = Path(__file__).resolve().parents[3]
    security_md = repo_root / "docs" / "SECURITY.md"
    assert security_md.is_file(), f"docs/SECURITY.md missing at {security_md}"

    content = security_md.read_text(encoding="utf-8")
    for asset_idx in range(1, 7):
        assert f"A{asset_idx}" in content, f"docs/SECURITY.md missing asset tag A{asset_idx}"

    for entry_idx in range(1, 9):
        assert f"E{entry_idx}" in content, f"docs/SECURITY.md missing entry tag E{entry_idx}"

    wiki_candidates = [
        Path("/home/adamoutler/kanban/thumbs-up-kanban.wiki/Security-and-STRIDE-Threat-Matrix.md"),
        repo_root / "thumbs-up-kanban.wiki" / "Security-and-STRIDE-Threat-Matrix.md",
        repo_root / "kanban" / "web" / "src" / "features" / "docs-center" / "wikiManifest.ts",
    ]
    wiki_file = next((p for p in wiki_candidates if p.is_file()), None)
    assert wiki_file is not None, "Wiki Security-and-STRIDE-Threat-Matrix.md missing"

    wiki_content = wiki_file.read_text(encoding="utf-8")
    for asset_idx in range(1, 7):
        assert f"A{asset_idx}" in wiki_content, f"Wiki missing asset tag A{asset_idx}"
    for entry_idx in range(1, 9):
        assert f"E{entry_idx}" in wiki_content, f"Wiki missing entry point tag E{entry_idx}"


def test_negative_unclassified_route_fails_closed() -> None:
    """Negative test: An unclassified route path raises ValueError and fails closed."""
    unclassified_path = "/unknown-alien-subsystem/execute"
    with pytest.raises(ValueError, match="Unclassified route path"):
        classify_route(unclassified_path)

    app = FastAPI()
    router = APIRouter()

    @router.get("/unknown-alien-subsystem/execute")
    def alien_endpoint() -> dict[str, str]:
        return {"status": "unauthorized"}

    assert alien_endpoint()["status"] == "unauthorized"
    app.include_router(router)
    report = audit_security_model_routes(app)
    unclass = report["unclassified_routes"]
    assert isinstance(unclass, list)
    assert len(unclass) > 0
    assert "/unknown-alien-subsystem/execute" in unclass


def test_negative_admin_route_without_aal2_fails_closed() -> None:
    """Negative test: Admin route mounted without require_admin_aal2 is flagged immediately."""
    app = FastAPI()
    admin_router = APIRouter(prefix="/api/v1/admin")

    @admin_router.post("/canary-unprotected-purge")
    def unprotected_admin_endpoint() -> dict[str, bool]:
        return {"purged": True}

    assert unprotected_admin_endpoint()["purged"] is True
    app.include_router(admin_router)
    unprotected = assert_admin_routes_protected(app)
    assert "/api/v1/admin/canary-unprotected-purge" in unprotected


def test_boundary_empty_or_mount_route_handling() -> None:
    """Boundary test: Verifies empty paths, sub-mounts, and root routes are classified properly."""
    assert classify_route("/") == EntrypointTier.E2_PUBLIC_REST_API
    assert classify_route("") == EntrypointTier.E2_PUBLIC_REST_API
    assert classify_route("/mcp") == EntrypointTier.E5_MCP_GATEWAY
    assert classify_route("/internal") == EntrypointTier.E3_INTERNAL_SERVICE_API
    assert classify_route("/api/v1/media-proxy") == EntrypointTier.E7_MEDIA_IMPORTER_EXPORTER
    assert classify_route("/ws") == EntrypointTier.E4_REALTIME_CHANNELS

    dummy_route = Route("/test-dummy", endpoint=lambda: None)
    app = FastAPI()
    app.routes.append(dummy_route)
    with pytest.raises(ValueError, match="Unclassified route path"):
        classify_route("/test-dummy")

    sub_router = APIRouter()
    sub_router.add_api_route("/sub-test", lambda: None)
    parent_router = APIRouter(prefix="/api/v1")
    parent_router.include_router(sub_router)
    extracted = extract_all_routes(parent_router)
    assert len(extracted) > 0
