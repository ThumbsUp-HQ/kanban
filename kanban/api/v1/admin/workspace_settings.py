# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""REST API router for Workspace Settings administration (KB-P4-09a, S11.4, S4.1, S10.2)."""

from __future__ import annotations

import logging
import uuid  # noqa: TC003
from datetime import datetime  # noqa: TC003
from typing import Annotated, Any, Final, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.spine import Workspace
from database.models.workspace_settings import WorkspaceSettings
from kanban.api.deps import PrincipalContext, get_rls_session
from kanban.api.problems import ProblemException
from kanban.auth.mfa.policy import require_admin_aal2
from kanban.services.activity import ActivityEventType, record_activity

logger = logging.getLogger(__name__)

_AAL2_MIN_LEVEL: Final[int] = 2


class WorkspaceSettingsResponse(BaseModel):
    """Schema representing current workspace settings."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    workspace_id: uuid.UUID
    display_name: str
    default_project_visibility: Literal["private", "workspace"]
    session_idle_timeout_min: int
    session_absolute_timeout_min: int
    trash_retention_days: int
    mcp_key_max_ttl_days: int
    air_gap_mode: bool
    updated_at: datetime


class WorkspaceSettingsUpdate(BaseModel):
    """Schema for updating workspace settings fields."""

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    default_project_visibility: Literal["private", "workspace"] | None = None
    session_idle_timeout_min: int | None = Field(default=None, ge=5, le=720)
    session_absolute_timeout_min: int | None = Field(default=None, ge=60, le=10080)
    trash_retention_days: int | None = Field(default=None, ge=1, le=365)
    mcp_key_max_ttl_days: int | None = Field(default=None, ge=1, le=365)
    air_gap_mode: bool | None = None


async def require_workspace_or_server_admin(
    caller: Annotated[PrincipalContext, Depends(require_admin_aal2)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> PrincipalContext:
    """Verify caller possesses SERVER_ADMIN or WORKSPACE_ADMIN role."""
    stmt = text("SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])")
    is_admin = bool((await session.execute(stmt)).scalar_one())
    if not is_admin:
        raise ProblemException(
            code="INSUFFICIENT_CAPABILITY",
            status=403,
            title="Insufficient Capability",
            detail="Operation requires SERVER_ADMIN or WORKSPACE_ADMIN role.",
        )
    return caller


router = APIRouter(
    prefix="/admin/workspace-settings",
    tags=["admin-workspace-settings"],
    dependencies=[Depends(require_admin_aal2), Depends(require_workspace_or_server_admin)],
)

Caller = Annotated[PrincipalContext, Depends(require_workspace_or_server_admin)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


async def _get_or_create_settings(
    session: AsyncSession,
    workspace_id: uuid.UUID,
) -> WorkspaceSettings:
    """Retrieve existing WorkspaceSettings row or create default for the workspace."""
    stmt = (
        select(WorkspaceSettings)
        .where(WorkspaceSettings.workspace_id == workspace_id)
        .with_for_update()
    )
    result = await session.execute(stmt)
    settings = result.scalar_one_or_none()
    if settings is not None:
        return settings

    # Fetch workspace metadata
    ws_stmt = select(Workspace).where(Workspace.id == workspace_id)
    ws = (await session.execute(ws_stmt)).scalar_one_or_none()
    display_name = ws.name[:80] if ws and ws.name else "Workspace"
    trash_days = ws.trash_retention_days if ws and ws.trash_retention_days else 30

    settings = WorkspaceSettings(
        workspace_id=workspace_id,
        display_name=display_name,
        default_project_visibility="private",
        session_idle_timeout_min=60,
        session_absolute_timeout_min=720,
        trash_retention_days=trash_days,
        mcp_key_max_ttl_days=90,
        air_gap_mode=False,
    )
    session.add(settings)
    await session.flush()
    await session.refresh(settings)
    return settings


@router.get(
    "",
    response_model=WorkspaceSettingsResponse,
    summary="Get workspace settings",
)
async def get_workspace_settings(
    caller: Caller,
    session: Session,
) -> WorkspaceSettingsResponse:
    """Retrieve security defaults, timeouts, and air-gap mode for active workspace."""
    settings = await _get_or_create_settings(session, caller.workspace_id)
    return WorkspaceSettingsResponse.model_validate(settings)


@router.patch(
    "",
    response_model=WorkspaceSettingsResponse,
    summary="Update workspace settings",
)
async def update_workspace_settings(  # noqa: C901
    body: WorkspaceSettingsUpdate,
    caller: Caller,
    session: Session,
) -> WorkspaceSettingsResponse:
    """Update workspace settings, enforce timeout invariants, and record audit activity."""
    settings = await _get_or_create_settings(session, caller.workspace_id)

    # Validate relative timeout constraint
    eff_idle = (
        body.session_idle_timeout_min
        if body.session_idle_timeout_min is not None
        else settings.session_idle_timeout_min
    )
    eff_abs = (
        body.session_absolute_timeout_min
        if body.session_absolute_timeout_min is not None
        else settings.session_absolute_timeout_min
    )
    if eff_abs < eff_idle:
        raise ProblemException(
            code="VALIDATION_FAILED",
            status=422,
            title="Validation Failed",
            detail="session_absolute_timeout_min must be >= session_idle_timeout_min.",
        )

    # Check AAL2 enforcement when toggling air_gap_mode
    air_gap_toggled = body.air_gap_mode is not None and body.air_gap_mode != settings.air_gap_mode
    if air_gap_toggled and caller.aal_level < _AAL2_MIN_LEVEL:
        raise ProblemException(
            code="AAL2_REQUIRED",
            status=403,
            title="AAL2 Required",
            detail="Toggling air_gap_mode requires AAL2 authentication.",
        )

    before: dict[str, Any] = {
        "display_name": settings.display_name,
        "default_project_visibility": settings.default_project_visibility,
        "session_idle_timeout_min": settings.session_idle_timeout_min,
        "session_absolute_timeout_min": settings.session_absolute_timeout_min,
        "trash_retention_days": settings.trash_retention_days,
        "mcp_key_max_ttl_days": settings.mcp_key_max_ttl_days,
        "air_gap_mode": settings.air_gap_mode,
    }

    diff: dict[str, Any] = {}
    if body.display_name is not None and body.display_name != settings.display_name:
        diff["display_name"] = body.display_name
        settings.display_name = body.display_name

    if (
        body.default_project_visibility is not None
        and body.default_project_visibility != settings.default_project_visibility
    ):
        diff["default_project_visibility"] = body.default_project_visibility
        settings.default_project_visibility = body.default_project_visibility

    if (
        body.session_idle_timeout_min is not None
        and body.session_idle_timeout_min != settings.session_idle_timeout_min
    ):
        diff["session_idle_timeout_min"] = body.session_idle_timeout_min
        settings.session_idle_timeout_min = body.session_idle_timeout_min

    if (
        body.session_absolute_timeout_min is not None
        and body.session_absolute_timeout_min != settings.session_absolute_timeout_min
    ):
        diff["session_absolute_timeout_min"] = body.session_absolute_timeout_min
        settings.session_absolute_timeout_min = body.session_absolute_timeout_min

    if (
        body.trash_retention_days is not None
        and body.trash_retention_days != settings.trash_retention_days
    ):
        diff["trash_retention_days"] = body.trash_retention_days
        settings.trash_retention_days = body.trash_retention_days
        # Synchronize with workspaces.trash_retention_days
        ws_stmt = select(Workspace).where(Workspace.id == caller.workspace_id)
        ws = (await session.execute(ws_stmt)).scalar_one_or_none()
        if ws is not None:
            ws.trash_retention_days = body.trash_retention_days

    if (
        body.mcp_key_max_ttl_days is not None
        and body.mcp_key_max_ttl_days != settings.mcp_key_max_ttl_days
    ):
        diff["mcp_key_max_ttl_days"] = body.mcp_key_max_ttl_days
        settings.mcp_key_max_ttl_days = body.mcp_key_max_ttl_days

    old_air_gap = settings.air_gap_mode
    if air_gap_toggled:
        diff["air_gap_mode"] = body.air_gap_mode
        settings.air_gap_mode = bool(body.air_gap_mode)

    if diff:
        await session.flush()
        await session.refresh(settings)

        after: dict[str, Any] = {
            "display_name": settings.display_name,
            "default_project_visibility": settings.default_project_visibility,
            "session_idle_timeout_min": settings.session_idle_timeout_min,
            "session_absolute_timeout_min": settings.session_absolute_timeout_min,
            "trash_retention_days": settings.trash_retention_days,
            "mcp_key_max_ttl_days": settings.mcp_key_max_ttl_days,
            "air_gap_mode": settings.air_gap_mode,
        }

        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.WORKSPACE_SETTINGS_CHANGED,
            payload={"diff": diff, "before": before, "after": after},
        )

        if air_gap_toggled:
            await record_activity(
                session,
                workspace_id=caller.workspace_id,
                actor_principal_id=caller.principal_id,
                event_type=ActivityEventType.AIR_GAP_MODE_CHANGED,
                payload={"air_gap_mode": settings.air_gap_mode, "previous": old_air_gap},
            )

    return WorkspaceSettingsResponse.model_validate(settings)
