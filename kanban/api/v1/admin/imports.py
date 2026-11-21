# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""REST API router for Plane and external imports administration (KB-P6-01, S1.3, S15.5)."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002  # Runtime dependency for FastAPI

from kanban.api.deps import PrincipalContext, get_rls_session
from kanban.api.problems import ProblemException
from kanban.api.v1.admin.auth_cards import require_server_admin
from kanban.auth.mfa.policy import require_admin_aal2
from kanban.importer.github_importer import GitHubIssuesImporter
from kanban.importer.jira_importer import JiraImporter
from kanban.importer.linear_importer import LinearImporter
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

    bundle_name: str | None = Field(
        default=None,
        description="Name of bundle folder in imports storage (alphanumeric/dash/underscore)",
    )
    bundle_data: dict[str, Any] | None = Field(
        default=None,
        description="Direct JSON bundle payload for upload/paste import",
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

    if not target_path.is_dir() and not target_path.is_file():
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
    client = PlaneClient()
    try:
        if req.bundle_data is not None:
            bundle = client.load_bundle_from_dict(req.bundle_data)
        elif req.bundle_name is not None:
            bundle_dir = _resolve_bundle_path(req.bundle_name)
            bundle = client.load_bundle_from_dir(bundle_dir)
        else:
            raise ProblemException(
                code="BUNDLE_REQUIRED",
                status=status.HTTP_422_UNPROCESSABLE_CONTENT,
                title="Bundle Required",
                detail="Either bundle_name or bundle_data must be provided.",
            )
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


class AdminGenericImportRequest(BaseModel):
    """Payload requesting execution or preview of Jira, GitHub, or Linear imports."""

    bundle_name: str | None = Field(
        default=None,
        description="Bundle file or folder name in imports storage",
    )
    bundle_data: Any | None = Field(
        default=None,
        description="Direct JSON or CSV data payload for upload/paste import",
    )
    project_key: str | None = Field(
        default=None,
        description="Target project key (e.g. JIRA, GH, LIN)",
    )
    dry_run: bool = Field(
        default=False,
        description="Simulate import and return diff report without persisting database changes",
    )
    user_map: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping from source user identifiers to Kanban handles",
    )
    workspace_slug: str | None = Field(
        default=None,
        description="Target workspace slug (defaults to caller active workspace)",
    )


def _load_generic_data(bundle_name: str | None, bundle_data: Any | None) -> Any:  # noqa: ANN401
    """Extract import data from either in-memory payload or storage path."""
    if bundle_data is not None:
        return bundle_data
    if bundle_name is not None:
        target = _resolve_bundle_path(bundle_name)
        if target.is_file():
            content = target.read_text(encoding="utf-8")
            try:
                return json.loads(content)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return content
        elif target.is_dir():
            for cand in (
                "issues.json",
                "export.json",
                "bundle.json",
                "jira.json",
                "github.json",
                "linear.json",
            ):
                cand_path = target / cand
                if cand_path.is_file():
                    return json.loads(cand_path.read_text(encoding="utf-8"))
            raise ProblemException(
                code="BUNDLE_INVALID",
                status=status.HTTP_422_UNPROCESSABLE_CONTENT,
                title="Bundle Invalid",
                detail=f"No JSON export file found in bundle directory '{bundle_name}'.",
            )
    raise ProblemException(
        code="BUNDLE_REQUIRED",
        status=status.HTTP_422_UNPROCESSABLE_CONTENT,
        title="Bundle Required",
        detail="Either bundle_name or bundle_data must be provided.",
    )


@router.post(
    "/imports/jira",
    response_model=ImportDiffReport,
    summary="Import or preview Jira export bundle (Server Admin + AAL2)",
)
async def import_jira_bundle(
    req: AdminGenericImportRequest,
    caller: Annotated[PrincipalContext, Depends(require_server_admin)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> ImportDiffReport:
    """Import a validated Jira JSON export into the workspace."""
    data = _load_generic_data(req.bundle_name, req.bundle_data)
    importer_caller = await _resolve_target_context(session, caller, req.workspace_slug)
    importer = JiraImporter(
        session=session,
        caller=importer_caller,
        user_map=req.user_map,
    )
    target_key = req.project_key or "JIRA"
    try:
        report = await importer.run_import(data, target_project_key=target_key, dry_run=req.dry_run)
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
        logger.exception("Unexpected error during Jira import")
        raise ProblemException(
            code="IMPORT_EXECUTION_ERROR",
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            title="Import Execution Error",
            detail=str(exc),
        ) from exc
    else:
        return report


@router.post(
    "/imports/github",
    response_model=ImportDiffReport,
    summary="Import or preview GitHub issues bundle (Server Admin + AAL2)",
)
async def import_github_bundle(
    req: AdminGenericImportRequest,
    caller: Annotated[PrincipalContext, Depends(require_server_admin)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> ImportDiffReport:
    """Import a validated GitHub issues JSON export into the workspace."""
    data = _load_generic_data(req.bundle_name, req.bundle_data)
    importer_caller = await _resolve_target_context(session, caller, req.workspace_slug)
    importer = GitHubIssuesImporter(
        session=session,
        caller=importer_caller,
        user_map=req.user_map,
    )
    target_key = req.project_key or "GH"
    try:
        report = await importer.run_import(data, target_project_key=target_key, dry_run=req.dry_run)
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
        logger.exception("Unexpected error during GitHub import")
        raise ProblemException(
            code="IMPORT_EXECUTION_ERROR",
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            title="Import Execution Error",
            detail=str(exc),
        ) from exc
    else:
        return report


@router.post(
    "/imports/linear",
    response_model=ImportDiffReport,
    summary="Import or preview Linear JSON/CSV export bundle (Server Admin + AAL2)",
)
async def import_linear_bundle(
    req: AdminGenericImportRequest,
    caller: Annotated[PrincipalContext, Depends(require_server_admin)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> ImportDiffReport:
    """Import a validated Linear JSON or CSV export into the workspace."""
    data = _load_generic_data(req.bundle_name, req.bundle_data)
    importer_caller = await _resolve_target_context(session, caller, req.workspace_slug)
    importer = LinearImporter(
        session=session,
        caller=importer_caller,
        user_map=req.user_map,
    )
    target_key = req.project_key or "LIN"
    try:
        report = await importer.run_import(data, target_project_key=target_key, dry_run=req.dry_run)
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
        logger.exception("Unexpected error during Linear import")
        raise ProblemException(
            code="IMPORT_EXECUTION_ERROR",
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            title="Import Execution Error",
            detail=str(exc),
        ) from exc
    else:
        return report
