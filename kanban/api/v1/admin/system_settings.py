# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""REST API router for System Settings administration (KAN-316)."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from kanban.api.deps import PrincipalContext  # noqa: TC001  # FastAPI runtime dependency resolution
from kanban.api.v1.admin.auth_cards import require_server_admin
from kanban.auth.mfa.policy import require_admin_aal2
from kanban.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/system-settings",
    tags=["admin-system-settings"],
    dependencies=[Depends(require_admin_aal2), Depends(require_server_admin)],
)


class SystemSettingsResponse(BaseModel):
    """System-level operational and governance settings."""

    model_config = ConfigDict(extra="forbid")

    enable_issue_export: bool = True
    enable_issue_import: bool = True
    deployment_mode: str = "production"
    air_gap_mode: bool = False


class SystemSettingsUpdate(BaseModel):
    """Payload for updating system-level governance settings."""

    model_config = ConfigDict(extra="forbid")

    enable_issue_export: bool | None = None
    enable_issue_import: bool | None = None


@router.get(
    "",
    response_model=SystemSettingsResponse,
    summary="Get system settings (Server Admin + AAL2)",
)
async def get_system_settings(
    _caller: Annotated[PrincipalContext, Depends(require_server_admin)],
) -> SystemSettingsResponse:
    """Retrieve system-level governance and feature flags."""
    settings = get_settings()
    return SystemSettingsResponse(
        enable_issue_export=settings.enable_issue_export,
        enable_issue_import=settings.enable_issue_import,
        deployment_mode=settings.deployment_mode,
        air_gap_mode=settings.air_gap_mode,
    )


@router.patch(
    "",
    response_model=SystemSettingsResponse,
    summary="Update system settings (Server Admin + AAL2)",
)
async def update_system_settings(
    body: SystemSettingsUpdate,
    _caller: Annotated[PrincipalContext, Depends(require_server_admin)],
) -> SystemSettingsResponse:
    """Update system-level governance flags."""
    settings = get_settings()
    if body.enable_issue_export is not None:
        settings.enable_issue_export = body.enable_issue_export
        logger.info("System setting enable_issue_export updated to %s", body.enable_issue_export)
    if body.enable_issue_import is not None:
        settings.enable_issue_import = body.enable_issue_import
        logger.info("System setting enable_issue_import updated to %s", body.enable_issue_import)
    return SystemSettingsResponse(
        enable_issue_export=settings.enable_issue_export,
        enable_issue_import=settings.enable_issue_import,
        deployment_mode=settings.deployment_mode,
        air_gap_mode=settings.air_gap_mode,
    )
