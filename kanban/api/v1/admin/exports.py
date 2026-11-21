# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""REST API router for Portable Workspace Bundles export administration (KB-P6-03)."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002  # Runtime dependency for FastAPI

from kanban.api.deps import PrincipalContext, get_rls_session
from kanban.api.problems import ProblemException
from kanban.api.v1.admin.auth_cards import require_server_admin
from kanban.auth.mfa.policy import require_admin_aal2
from kanban.exporter.portable_bundle import PortableWorkspaceExporter

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=["Admin Exports"],
    dependencies=[Depends(require_admin_aal2)],
)


class AdminPortableExportRequest(BaseModel):
    """Payload requesting portable deterministic workspace bundle export."""

    workspace_slug: str | None = Field(
        default=None,
        description="Target workspace slug (defaults to caller's active workspace)",
    )
    scrub: bool = Field(
        default=False,
        description="Scrub secrets and sensitive tokens from markdown and text fields",
    )


@router.post(
    "/exports/portable",
    summary="Export deterministic portable workspace bundle (Server Admin + AAL2)",
    response_class=Response,
    responses={
        200: {
            "content": {"application/gzip": {}},
            "description": (
                "Deterministic .tar.gz workspace archive with manifest.json SHA-256 digests"
            ),
        }
    },
)
async def export_portable_workspace(
    req: AdminPortableExportRequest,
    caller: Annotated[PrincipalContext, Depends(require_server_admin)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> Response:
    """Generate and return a deterministic .tar.gz portable bundle for the workspace."""
    effective_workspace_id = caller.workspace_id
    effective_workspace_slug = "workspace"

    if req.workspace_slug:
        ws_res = await session.execute(
            text("SELECT id, slug FROM workspaces WHERE slug = :slug"),
            {"slug": req.workspace_slug},
        )
        found_ws = ws_res.mappings().one_or_none()
        if not found_ws:
            raise ProblemException(
                code="WORKSPACE_NOT_FOUND",
                status=status.HTTP_404_NOT_FOUND,
                title="Workspace Not Found",
                detail=f"Workspace '{req.workspace_slug}' does not exist.",
            )
        effective_workspace_id = found_ws["id"]
        effective_workspace_slug = found_ws["slug"]
    else:
        ws_res = await session.execute(
            text("SELECT slug FROM workspaces WHERE id = :id"),
            {"id": caller.workspace_id},
        )
        row = ws_res.mappings().one_or_none()
        if row:
            effective_workspace_slug = row["slug"]

    exporter = PortableWorkspaceExporter(
        session=session,
        workspace_id=effective_workspace_id,
        caller=caller,
    )

    try:
        bundle_bytes = await exporter.export_bundle(scrub=req.scrub)
    except Exception as exc:
        logger.exception("Failed to generate portable workspace export")
        raise ProblemException(
            code="EXPORT_EXECUTION_ERROR",
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            title="Export Execution Error",
            detail=str(exc),
        ) from exc

    filename = f"kanban-{effective_workspace_slug}-portable.tar.gz"
    return Response(
        content=bundle_bytes,
        media_type="application/gzip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "application/gzip",
        },
    )
