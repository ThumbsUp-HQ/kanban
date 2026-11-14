# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""REST API router for Plane and external imports administration (KB-P6-01, S1.3, S15.5)."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002  # Runtime dependency for FastAPI

from kanban.api.deps import PrincipalContext, get_rls_session
from kanban.api.problems import ProblemException
from kanban.api.v1.admin.auth_cards import require_server_admin
from kanban.auth.mfa.policy import require_admin_aal2
from kanban.importer.plane_client import PlaneClient, PlaneClientError
from kanban.importer.plane_importer import ImportDiffReport, ImportIntegrityError, PlaneImporter

logger = logging.getLogger(__name__)

SAFE_BUNDLE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")

router = APIRouter(
    prefix="/admin",
    tags=["Admin Imports"],
    dependencies=[Depends(require_admin_aal2)],
)


class AdminPlaneImportRequest(BaseModel):
    """Payload requesting execution or preview of a Plane export import."""

    bundle_name: str = Field(
        ...,
        description="Name of bundle folder in imports storage (alphanumeric/dash/underscore)",
    )
    dry_run: bool = Field(
        default=False,
        description="Simulate import and return diff report without persisting database changes",
    )
    user_map: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping from Plane user IDs to Kanban handles",
    )
    workspace_slug: str | None = Field(
        default=None,
        description="Target workspace slug (defaults to caller's active workspace)",
    )


def _resolve_bundle_path(bundle_name: str) -> Path:
    """Validate bundle name preventing traversal and resolve in imports root."""
    if (
        not SAFE_BUNDLE_NAME_RE.match(bundle_name)
        or ".." in bundle_name
        or "/" in bundle_name
        or "\\" in bundle_name
    ):
        raise ProblemException(
            code="PATH_TRAVERSAL_DETECTED",
            status=status.HTTP_422_UNPROCESSABLE_CONTENT,
            title="Path Traversal Detected",
            detail="Bundle name must be a simple alphanumeric token without path separators.",
        )

    base_dir = Path(os.environ.get("KANBAN_IMPORTS_DIR", "/var/lib/kanban/imports")).resolve()
    target_path = (base_dir / bundle_name).resolve()

    if not str(target_path).startswith(str(base_dir)):
        raise ProblemException(
            code="PATH_TRAVERSAL_DETECTED",
            status=status.HTTP_422_UNPROCESSABLE_CONTENT,
            title="Path Traversal Detected",
            detail="Resolved path escapes allowed imports directory.",
        )

    if not target_path.is_dir():
        raise ProblemException(
            code="BUNDLE_NOT_FOUND",
            status=status.HTTP_404_NOT_FOUND,
            title="Bundle Not Found",
            detail=f"Import bundle directory '{bundle_name}' not found under imports storage.",
        )

    return target_path


async def _resolve_target_context(
    session: AsyncSession,
    caller: PrincipalContext,
    workspace_slug: str | None,
) -> PrincipalContext:
    """Resolve target workspace and principal context for the import operation."""
    effective_workspace_id = caller.workspace_id
    if workspace_slug:
        ws_res = await session.execute(
            text("SELECT id FROM workspaces WHERE slug = :slug"),
            {"slug": workspace_slug},
        )
        found_ws = ws_res.scalar_one_or_none()
        if not found_ws:
            raise ProblemException(
                code="WORKSPACE_NOT_FOUND",
                status=status.HTTP_404_NOT_FOUND,
                title="Workspace Not Found",
                detail=f"Workspace '{workspace_slug}' does not exist.",
            )
        effective_workspace_id = found_ws

    target_principal_id = caller.principal_id
    if effective_workspace_id != caller.workspace_id:
        p_res = await session.execute(
            text(
                "SELECT principal_id FROM role_bindings "
                "WHERE workspace_id = :ws AND role::text IN ('WORKSPACE_ADMIN', 'SERVER_ADMIN') "
                "LIMIT 1"
            ),
            {"ws": effective_workspace_id},
        )
        found_p = p_res.scalar_one_or_none()
        if not found_p:
            p_fallback = await session.execute(
                text(
                    "SELECT id FROM principals "
                    "WHERE workspace_id = :ws AND principal_type = 'USER' LIMIT 1"
                ),
                {"ws": effective_workspace_id},
            )
            found_p = p_fallback.scalar_one_or_none()
        if found_p:
            target_principal_id = found_p

    return PrincipalContext(
        principal_id=target_principal_id,
        workspace_id=effective_workspace_id,
        aal_level=2,
    )


@router.post(
    "/imports/plane",
    response_model=ImportDiffReport,
    summary="Import or preview Plane export bundle (Server Admin + AAL2)",
)
@router.post(
    "/import/plane/preview",
    response_model=ImportDiffReport,
    include_in_schema=False,
)
@router.post(
    "/import/plane/execute",
    response_model=ImportDiffReport,
    include_in_schema=False,
)
async def import_plane_bundle(
    req: AdminPlaneImportRequest,
    caller: Annotated[PrincipalContext, Depends(require_server_admin)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> ImportDiffReport:
    """Import a validated Plane bundle into the workspace with sequence continuity."""
    bundle_dir = _resolve_bundle_path(req.bundle_name)

    client = PlaneClient()
    try:
        bundle = client.load_bundle_from_dir(bundle_dir)
    except PlaneClientError as exc:
        raise ProblemException(
            code="BUNDLE_INVALID",
            status=status.HTTP_422_UNPROCESSABLE_CONTENT,
            title="Bundle Invalid",
            detail=str(exc),
        ) from exc

    importer_caller = await _resolve_target_context(session, caller, req.workspace_slug)

    importer = PlaneImporter(
        session=session,
        caller=importer_caller,
        user_map=req.user_map,
    )

    try:
        report = await importer.run_import(bundle, dry_run=req.dry_run)
        if not req.dry_run:
            await session.commit()
    except ImportIntegrityError as exc:
        await session.rollback()
        raise ProblemException(
            code="IMPORT_INTEGRITY_FAILED",
            status=status.HTTP_422_UNPROCESSABLE_CONTENT,
            title="Import Integrity Failed",
            detail=str(exc),
        ) from exc
    except Exception as exc:
        await session.rollback()
        logger.exception("Unexpected error during Plane import")
        raise ProblemException(
            code="IMPORT_EXECUTION_ERROR",
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            title="Import Execution Error",
            detail=str(exc),
        ) from exc
    else:
        return report
