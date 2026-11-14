# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""RFC 9728 protected-resource metadata endpoints for MCP surfaces (KB-P4-02b, KB-P4-15)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from starlette.responses import JSONResponse, Response

if TYPE_CHECKING:
    from starlette.requests import Request

__all__ = [
    "SURFACE_SCOPES",
    "build_protected_resource_metadata",
    "protected_resource_metadata_endpoint",
]

SURFACE_SCOPES: Final[dict[str, list[str]]] = {
    "agent": ["agent:read", "agent:write"],
    "docs": ["docs:read", "docs:write"],
    "admin": ["admin:read", "admin:write", "admin:destructive"],
}


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
    """Handle GET /.well-known/oauth-protected-resource/mcp/{surface}.

    Supports optional [/w/{workspace_slug}[/p/{project_key}]] suffixes.
    """
    surface = request.path_params.get("surface", "")
    workspace_slug = request.path_params.get("workspace_slug")
    project_key = request.path_params.get("project_key")
    base_url = str(request.base_url).rstrip("/")

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
