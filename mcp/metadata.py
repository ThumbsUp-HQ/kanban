# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""RFC 9728 protected-resource metadata endpoints for MCP surfaces (KB-P4-02b, KB-P4-15)."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Final

from starlette.responses import JSONResponse, Response

if TYPE_CHECKING:
    from starlette.requests import Request

__all__ = [
    "SURFACE_SCOPES",
    "build_protected_resource_metadata",
    "protected_resource_metadata_endpoint",
    "resolve_public_base_url",
]

SURFACE_SCOPES: Final[dict[str, list[str]]] = {
    "agent": ["agent:read", "agent:write"],
    "docs": ["docs:read", "docs:write"],
    "admin": ["admin:read", "admin:write", "admin:destructive"],
}


def resolve_public_base_url(request: Request | None = None) -> str:
    """Resolve canonical public base URL from settings, proxy headers, or request base URL."""
    env_origin = os.environ.get("KANBAN_PUBLIC_ORIGIN", "").strip()
    if env_origin:
        return env_origin.rstrip("/")

    if request is not None:
        proto = request.headers.get("x-forwarded-proto")
        host = request.headers.get("x-forwarded-host") or request.headers.get("host")
        if proto:
            proto = proto.split(",")[0].strip()
        if host:
            host = host.split(",")[0].strip()
        if proto and host:
            return f"{proto}://{host}".rstrip("/")
        if host:
            has_url = hasattr(request, "url")
            scheme = request.url.scheme if has_url and request.url.scheme else "http"
            return f"{scheme}://{host}".rstrip("/")
        if hasattr(request, "base_url"):
            return str(request.base_url).rstrip("/")

    return "http://localhost:8000"


def build_protected_resource_metadata(
    surface: str,
    base_url: str,
    issuer: str | None = None,
    *,
    workspace_slug: str | None = None,
    project_key: str | None = None,
) -> dict[str, Any] | None:
    """Construct RFC 9728 metadata document for a given MCP surface and optional scope."""
    normalized_surface = surface.lower().strip()
    if not normalized_surface or normalized_surface == "mcp":
        normalized_surface = "agent"
    scopes = SURFACE_SCOPES.get(normalized_surface)
    if scopes is None:
        return None

    clean_base = base_url.rstrip("/")
    clean_issuer = issuer.rstrip("/") if issuer else clean_base

    resource = f"{clean_base}/mcp/{normalized_surface}"
    if workspace_slug:
        resource += f"/w/{workspace_slug}"
        if project_key:
            resource += f"/p/{project_key}"

    return {
        "resource": resource,
        "authorization_servers": [clean_issuer],
        "scopes_supported": scopes,
        "bearer_methods_supported": ["header"],
    }


async def protected_resource_metadata_endpoint(request: Request) -> Response:
    """Handle GET /.well-known/oauth-protected-resource.

    Supports surface in path, bare /mcp, and optional [/w/...[/p/...]] suffixes.
    """
    surface = request.path_params.get("surface", "").strip()
    workspace_slug = request.path_params.get("workspace_slug")
    project_key = request.path_params.get("project_key")

    path = request.url.path.rstrip("/")
    prefix = "/.well-known/oauth-protected-resource"
    if path.startswith(prefix):
        sub = path[len(prefix) :].strip("/")
        parts = [p for p in sub.split("/") if p]
        if parts:
            if parts[0] == "mcp":
                parts = parts[1:]
            if parts and parts[0] in ("agent", "docs", "admin"):
                surface = parts[0]
                parts = parts[1:]
            else:
                surface = surface or "agent"
            if parts and parts[0] == "w" and len(parts) >= 2:  # noqa: PLR2004
                workspace_slug = parts[1]
                if len(parts) >= 4 and parts[2] == "p":  # noqa: PLR2004
                    project_key = parts[3]

    if not surface or surface == "mcp":
        surface = "agent"

    base_url = resolve_public_base_url(request)

    metadata = build_protected_resource_metadata(
        surface,
        base_url,
        workspace_slug=workspace_slug,
        project_key=project_key,
    )
    if metadata is None:
        return JSONResponse(
            {"error": "not_found", "message": f"Unknown surface {surface!r}"},
            status_code=404,
        )

    return JSONResponse(
        metadata,
        headers={
            "Content-Type": "application/json",
            "Cache-Control": "public, max-age=3600",
        },
    )
