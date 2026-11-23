# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Workspaces listing, creation, and switching API endpoints (KB-UX-05, S1.1, S3.3)."""

from __future__ import annotations

import logging
import re
import uuid
from typing import TYPE_CHECKING, Annotated, Literal, Self

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002  # FastAPI dependency
from starlette.responses import JSONResponse

from database.models.spine import Workspace
from database.models.workspace_settings import WorkspaceSettings
from kanban.admin import principal_service
from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.problems import FieldError, ProblemException
from kanban.api.v1.admin.workspace_settings import (
    WorkspaceSettingsResponse,
    WorkspaceSettingsUpdate,
    _get_or_create_settings,
)
from kanban.auth.mfa.policy import require_admin_aal2
from kanban.auth.sessions.cookies import (
    FALLBACK_SESSION_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    attach_session_and_csrf_cookies,
    build_clear_fallback_cookie_header,
    extract_session_cookie,
    is_plain_http,
)
from kanban.auth.sessions.csrf import (
    FALLBACK_CSRF_COOKIE_NAME,
    build_clear_fallback_csrf_cookie_header,
)
from kanban.security.granular_permissions import GranularPermission, require_permissions

if TYPE_CHECKING:
    from kanban.auth.sessions.service import SessionService

logger = logging.getLogger(__name__)

SLUG_REGEX = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
MAX_WORKSPACE_NAME_LEN = 200

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


class WorkspaceResponse(BaseModel):
    """Workspace metadata descriptor."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    name: str
    slug: str
    is_current: bool = False
    role: str | None = None


class CreateWorkspaceRequest(BaseModel):
    """Payload for creating a new tenant workspace."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        ...,
        min_length=1,
        max_length=MAX_WORKSPACE_NAME_LEN,
        description="Workspace display name",
    )
    slug: str = Field(
        ...,
        min_length=2,
        max_length=63,
        description="Lowercase URL-safe slug (^[a-z0-9][a-z0-9-]{1,62}$)",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate trimmed name length."""
        trimmed = v.strip()
        if not (1 <= len(trimmed) <= MAX_WORKSPACE_NAME_LEN):
            msg = f"name must be between 1 and {MAX_WORKSPACE_NAME_LEN} characters"
            raise ValueError(msg)
        return trimmed

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        """Validate lowercase URL-safe slug matching regex."""
        cleaned = v.strip().lower()
        if not SLUG_REGEX.match(cleaned):
            msg = "slug must match ^[a-z0-9][a-z0-9-]{1,62}$"
            raise ValueError(msg)
        return cleaned


class SwitchWorkspaceResponse(BaseModel):
    """Result of switching active workspace session."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: uuid.UUID
    status: str = "switched"
    csrf_token: str | None = None


@router.get(
    "",
    response_model=list[WorkspaceResponse],
    summary="List available workspaces for caller",
)
async def list_workspaces_endpoint(
    caller: Annotated[PrincipalContext, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
    request: Request,
) -> list[WorkspaceResponse]:
    """List all workspaces accessible to the authenticated principal."""
    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        res = await session.execute(
            text("SELECT id, name, slug FROM workspaces WHERE id = :ws_id"),
            {"ws_id": caller.workspace_id},
        )
        row = res.first()
        if row:
            return [
                WorkspaceResponse(
                    id=row.id,
                    name=row.name,
                    slug=row.slug,
                    is_current=True,
                )
            ]
        return []

    res = await session.execute(
        text("SELECT id, name, slug, role FROM kb_auth_list_user_workspaces(:p_id)"),
        {"p_id": caller.principal_id},
    )
    workspaces = [
        WorkspaceResponse(
            id=row.id,
            name=row.name,
            slug=row.slug,
            is_current=(row.id == caller.workspace_id),
            role=row.role,
        )
        for row in res.fetchall()
    ]

    found_ids = {w.id for w in workspaces}
    if caller.workspace_id not in found_ids:
        curr_row = (
            await session.execute(
                text("SELECT id, name, slug FROM workspaces WHERE id = :ws_id"),
                {"ws_id": caller.workspace_id},
            )
        ).first()
        if curr_row:
            workspaces.insert(
                0,
                WorkspaceResponse(
                    id=curr_row.id,
                    name=curr_row.name,
                    slug=curr_row.slug,
                    is_current=True,
                    role=None,
                ),
            )

    return workspaces


@router.post(
    "",
    response_model=WorkspaceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new workspace and bind creator as WORKSPACE_ADMIN",
)
async def create_workspace_endpoint(
    body: CreateWorkspaceRequest,
    caller: Annotated[PrincipalContext, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
    request: Request,
) -> WorkspaceResponse:
    """Create a new workspace, auto-initialize settings, and assign WORKSPACE_ADMIN."""
    await require_permissions(
        session, caller, caller.workspace_id, {GranularPermission.WORKSPACE_CREATE.value}
    )
    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        raise ProblemException(
            code="INTERNAL_ERROR",
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            title="Internal Server Error",
            detail="Session factory is not available.",
        )
    try:
        res = (
            await session.execute(
                text(
                    "SELECT workspace_id, principal_id "
                    "FROM kb_auth_create_workspace(:name, :slug, :p_id)"
                ),
                {"name": body.name, "slug": body.slug, "p_id": caller.principal_id},
            )
        ).first()
        await session.commit()
    except Exception as exc:
        err_msg = str(exc)
        if "WORKSPACE_SLUG_CONFLICT" in err_msg or "23505" in err_msg:
            raise ProblemException(
                code="WORKSPACE_SLUG_CONFLICT",
                status=status.HTTP_409_CONFLICT,
                title="Workspace Slug Conflict",
                detail=f"Workspace slug '{body.slug}' is already taken.",
            ) from exc
        raise

    new_ws_id = res.workspace_id if res else uuid.uuid4()
    return WorkspaceResponse(
        id=new_ws_id,
        name=body.name,
        slug=body.slug,
        is_current=False,
        role="WORKSPACE_ADMIN",
    )


async def _execute_workspace_switch_proc(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    principal_id: uuid.UUID,
) -> uuid.UUID:
    """Execute kb_auth_switch_workspace procedure and handle error codes."""
    try:
        res = (
            await session.execute(
                text(
                    "SELECT workspace_id, principal_id FROM kb_auth_switch_workspace(:ws_id, :p_id)"
                ),
                {"ws_id": workspace_id, "p_id": principal_id},
            )
        ).first()
    except Exception as exc:
        err_msg = str(exc)
        if "WORKSPACE_NOT_FOUND" in err_msg or "P0002" in err_msg:
            raise ProblemException(
                code="WORKSPACE_NOT_FOUND",
                status=status.HTTP_404_NOT_FOUND,
                title="Workspace Not Found",
                detail=f"Target workspace {workspace_id} does not exist.",
            ) from exc
        if "FORBIDDEN" in err_msg or "42501" in err_msg:
            raise ProblemException(
                code="FORBIDDEN_WORKSPACE_SWITCH",
                status=status.HTTP_403_FORBIDDEN,
                title="Forbidden Workspace Switch",
                detail="Principal is not a member of target workspace.",
            ) from exc
        raise

    if not res:
        raise ProblemException(
            code="WORKSPACE_NOT_FOUND",
            status=status.HTTP_404_NOT_FOUND,
            title="Workspace Not Found",
            detail=f"Target workspace {workspace_id} does not exist.",
        )
    val = res.principal_id
    if isinstance(val, uuid.UUID):
        return val
    return uuid.UUID(str(val))


@router.post(
    "/{workspace_id}/switch",
    response_model=SwitchWorkspaceResponse,
    summary="Switch active workspace session",
)
async def switch_workspace_endpoint(
    workspace_id: uuid.UUID,
    caller: Annotated[PrincipalContext, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
    request: Request,
) -> Response:
    """Switch caller's active session to the target workspace."""
    if caller.session_id is None:
        raise ProblemException(
            code="SESSION_REQUIRED",
            status=status.HTTP_401_UNAUTHORIZED,
            title="Session Required",
            detail="Workspace switching requires an active browser session.",
        )

    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        raise ProblemException(
            code="INTERNAL_ERROR",
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            title="Internal Server Error",
            detail="Session factory is not available.",
        )

    target_principal_id = await _execute_workspace_switch_proc(
        session, workspace_id, caller.principal_id
    )

    session_service: SessionService | None = getattr(request.app.state, "session_service", None)
    if session_service is not None:
        cookie_hdr = request.headers.get("cookie")
        existing_sess = (
            extract_session_cookie(cookie_hdr)
            or request.cookies.get(SESSION_COOKIE_NAME)
            or request.cookies.get(FALLBACK_SESSION_COOKIE_NAME)
        )
        orig_session = getattr(request.state, "user_session", None)
        try:
            issued = await session_service.rotate_for_workspace_switch(
                session,
                target_principal_id=target_principal_id,
                target_workspace_id=workspace_id,
                old_session_id=caller.session_id,
                existing_cookie=existing_sess,
                originating_session=orig_session,
            )
        except ValueError as exc:
            raise ProblemException(
                code="SESSION_EXPIRED",
                status=status.HTTP_401_UNAUTHORIZED,
                title="Session Expired",
                detail=str(exc),
            ) from exc

        await session.commit()

        response = JSONResponse(
            content={
                "workspace_id": str(workspace_id),
                "status": "switched",
                "csrf_token": issued.csrf_token,
            }
        )
        attach_session_and_csrf_cookies(
            response,
            request,
            issued,
            issued.csrf_token,
            persistent=issued.is_persistent,
        )
        if not is_plain_http(request):
            if FALLBACK_SESSION_COOKIE_NAME in request.cookies:
                response.raw_headers.append(
                    (b"set-cookie", build_clear_fallback_cookie_header().encode("latin-1"))
                )
            if FALLBACK_CSRF_COOKIE_NAME in request.cookies:
                response.raw_headers.append(
                    (b"set-cookie", build_clear_fallback_csrf_cookie_header().encode("latin-1"))
                )
        return response

    return JSONResponse(
        content={
            "workspace_id": str(workspace_id),
            "status": "switched",
        }
    )


class UpdateWorkspaceRequest(BaseModel):
    """Payload for updating workspace name or slug."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_WORKSPACE_NAME_LEN,
        description="Updated workspace display name",
    )
    slug: str | None = Field(
        default=None,
        min_length=2,
        max_length=63,
        description="Updated lowercase URL-safe slug",
    )


@router.patch(
    "/{workspace_id}",
    response_model=WorkspaceResponse,
    summary="Update workspace name or slug",
    dependencies=[Depends(require_admin_aal2)],
)
async def update_workspace_endpoint(
    workspace_id: uuid.UUID,
    body: UpdateWorkspaceRequest,
    caller: Annotated[PrincipalContext, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> WorkspaceResponse:
    """Update workspace name or slug. Requires WORKSPACE_ADMIN or SERVER_ADMIN."""
    target_id = (
        caller.workspace_id if str(workspace_id) == str(caller.workspace_id) else workspace_id
    )
    await require_permissions(
        session, caller, target_id, {GranularPermission.WORKSPACE_EDIT_SETTINGS.value}
    )
    ws_stmt = select(Workspace).where(Workspace.id == target_id)
    ws = (await session.execute(ws_stmt)).scalar_one_or_none()
    if ws is None:
        raise ProblemException(
            code="NOT_FOUND",
            status=status.HTTP_404_NOT_FOUND,
            title="Not Found",
            detail="Workspace not found.",
        )

    if body.name is not None:
        cleaned_name = body.name.strip()
        ws.name = cleaned_name
        set_stmt = select(WorkspaceSettings).where(WorkspaceSettings.workspace_id == target_id)
        settings = (await session.execute(set_stmt)).scalar_one_or_none()
        if settings is not None:
            settings.display_name = cleaned_name[:80]

    if body.slug is not None:
        cleaned_slug = body.slug.strip().lower()
        if not SLUG_REGEX.match(cleaned_slug):
            raise ProblemException(
                code="VALIDATION_FAILED",
                status=422,
                title="Validation Failed",
                detail="slug must match ^[a-z0-9][a-z0-9-]{1,62}$",
            )
        if cleaned_slug != ws.slug:
            existing_ws_id = (
                await session.execute(
                    text("SELECT resolve_workspace_by_slug_or_id(:ident)"),
                    {"ident": cleaned_slug},
                )
            ).scalar_one_or_none()
            if existing_ws_id is not None and str(existing_ws_id) != str(target_id):
                raise ProblemException(
                    code="WORKSPACE_SLUG_CONFLICT",
                    status=status.HTTP_409_CONFLICT,
                    title="Workspace Slug Conflict",
                    detail=f"Workspace slug '{cleaned_slug}' is already taken.",
                )
            ws.slug = cleaned_slug

    await session.flush()
    await session.commit()
    return WorkspaceResponse(
        id=ws.id,
        name=ws.name,
        slug=ws.slug,
        is_current=(ws.id == caller.workspace_id),
        role="WORKSPACE_ADMIN",
    )


class WorkspaceRoleBindingRequest(BaseModel):
    """Schema for workspace-scoped role binding accepting both role and role_name."""

    model_config = ConfigDict(extra="ignore")

    principal_id: uuid.UUID = Field(
        description="Target principal UUID receiving the role assignment"
    )
    role: str | None = Field(default=None)
    role_name: str | None = Field(default=None)
    scope_type: Literal["server", "workspace", "project"] = "workspace"
    scope_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def resolve_role_field(self) -> Self:
        """Resolve role from role or role_name."""
        resolved = self.role or self.role_name
        if not resolved:
            msg = "role or role_name is required"
            raise ProblemException(
                code="VALIDATION_FAILED",
                status=422,
                title="Validation Failed",
                detail=msg,
                errors=[FieldError(path="role", message=msg)],
            )
        self.role = resolved
        self.role_name = resolved
        return self


@router.post(
    "/{workspace_id}/role-bindings",
    summary="Bind RBAC role to principal in workspace",
    dependencies=[Depends(require_admin_aal2)],
)
async def bind_workspace_role_endpoint(
    workspace_id: uuid.UUID,
    body: WorkspaceRoleBindingRequest,
    caller: Annotated[PrincipalContext, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> dict[str, object]:
    """Bind role to principal at workspace scope."""
    await require_permissions(
        session, caller, workspace_id, {GranularPermission.WORKSPACE_MANAGE_MEMBERS.value}
    )
    res = await principal_service.bind_role(
        session,
        workspace_id,
        caller.principal_id,
        principal_id=body.principal_id,
        role_name=body.role,  # type: ignore[arg-type]
        scope_type=body.scope_type,
        project_id=body.scope_id,
    )
    await session.commit()
    return res


@router.delete(
    "/{workspace_id}/role-bindings",
    summary="Unbind RBAC role from principal in workspace",
    dependencies=[Depends(require_admin_aal2)],
)
async def unbind_workspace_role_endpoint(
    workspace_id: uuid.UUID,
    body: WorkspaceRoleBindingRequest,
    caller: Annotated[PrincipalContext, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> dict[str, object]:
    """Unbind role from principal at workspace scope."""
    await require_permissions(
        session, caller, workspace_id, {GranularPermission.WORKSPACE_MANAGE_MEMBERS.value}
    )
    res = await principal_service.unbind_role(
        session,
        workspace_id,
        caller.principal_id,
        principal_id=body.principal_id,
        role_name=body.role,  # type: ignore[arg-type]
        scope_type=body.scope_type,
        project_id=body.scope_id,
    )
    await session.commit()
    return res


@router.get(
    "/{workspace_ref}/settings",
    response_model=WorkspaceSettingsResponse,
    summary="Get workspace settings by workspace slug or ID",
)
async def get_workspace_settings_by_ref(
    workspace_ref: str,
    _caller: Annotated[PrincipalContext, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> WorkspaceSettingsResponse:
    """Retrieve workspace settings by slug or UUID."""
    ws_res = await session.execute(
        text("SELECT resolve_workspace_by_slug_or_id(:ident)"),
        {"ident": workspace_ref},
    )
    ws_id = ws_res.scalar_one_or_none()
    if not ws_id:
        raise ProblemException(
            code="WORKSPACE_NOT_FOUND",
            status=status.HTTP_404_NOT_FOUND,
            title="Workspace Not Found",
            detail=f"Workspace '{workspace_ref}' not found.",
        )
    settings = await _get_or_create_settings(session, ws_id)
    ws_stmt = select(Workspace).where(Workspace.id == ws_id)
    ws = (await session.execute(ws_stmt)).scalar_one_or_none()
    return WorkspaceSettingsResponse(
        workspace_id=settings.workspace_id,
        name=ws.name if ws else settings.display_name,
        slug=ws.slug if ws else "default",
        display_name=settings.display_name,
        default_project_visibility=settings.default_project_visibility,  # type: ignore[arg-type]
        session_idle_timeout_min=settings.session_idle_timeout_min,
        session_absolute_timeout_min=settings.session_absolute_timeout_min,
        trash_retention_days=settings.trash_retention_days,
        mcp_key_max_ttl_days=settings.mcp_key_max_ttl_days,
        air_gap_mode=settings.air_gap_mode,
        default_skip_loaded_sequence_numbers=settings.default_skip_loaded_sequence_numbers,
        issue_export_enabled=settings.issue_export_enabled,
        issue_import_enabled=settings.issue_import_enabled,
        issue_export_allowed_roles=list(
            settings.issue_export_allowed_roles or ["workspace_admin", "project_admin", "member"]
        ),
        updated_at=settings.updated_at,
    )


@router.patch(
    "/{workspace_ref}/settings",
    response_model=WorkspaceSettingsResponse,
    summary="Update workspace settings by workspace slug or ID",
)
async def update_workspace_settings_by_ref(  # noqa: C901, PLR0912
    workspace_ref: str,
    body: WorkspaceSettingsUpdate,
    _caller: Annotated[PrincipalContext, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> WorkspaceSettingsResponse:
    """Update workspace settings by slug or UUID. Requires WORKSPACE_ADMIN or SERVER_ADMIN."""
    ws_res = await session.execute(
        text("SELECT resolve_workspace_by_slug_or_id(:ident)"),
        {"ident": workspace_ref},
    )
    ws_id = ws_res.scalar_one_or_none()
    if not ws_id:
        raise ProblemException(
            code="WORKSPACE_NOT_FOUND",
            status=status.HTTP_404_NOT_FOUND,
            title="Workspace Not Found",
            detail=f"Workspace '{workspace_ref}' not found.",
        )

    admin_check = await session.execute(
        text("SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])")
    )
    if not bool(admin_check.scalar_one()):
        raise ProblemException(
            code="INSUFFICIENT_CAPABILITY",
            status=status.HTTP_403_FORBIDDEN,
            title="Insufficient Capability",
            detail="Operation requires SERVER_ADMIN or WORKSPACE_ADMIN role.",
        )

    settings = await _get_or_create_settings(session, ws_id)
    ws_stmt = select(Workspace).where(Workspace.id == ws_id)
    ws = (await session.execute(ws_stmt)).scalar_one_or_none()

    if body.issue_export_enabled is not None:
        settings.issue_export_enabled = body.issue_export_enabled
    if body.issue_import_enabled is not None:
        settings.issue_import_enabled = body.issue_import_enabled
    if body.issue_export_allowed_roles is not None:
        settings.issue_export_allowed_roles = body.issue_export_allowed_roles
    if body.display_name is not None:
        settings.display_name = body.display_name
    if body.default_project_visibility is not None:
        settings.default_project_visibility = body.default_project_visibility
    if body.session_idle_timeout_min is not None:
        settings.session_idle_timeout_min = body.session_idle_timeout_min
    if body.session_absolute_timeout_min is not None:
        settings.session_absolute_timeout_min = body.session_absolute_timeout_min
    if body.trash_retention_days is not None:
        settings.trash_retention_days = body.trash_retention_days
    if body.mcp_key_max_ttl_days is not None:
        settings.mcp_key_max_ttl_days = body.mcp_key_max_ttl_days
    if body.air_gap_mode is not None:
        settings.air_gap_mode = body.air_gap_mode
    if body.default_skip_loaded_sequence_numbers is not None:
        settings.default_skip_loaded_sequence_numbers = body.default_skip_loaded_sequence_numbers

    await session.commit()
    return WorkspaceSettingsResponse(
        workspace_id=settings.workspace_id,
        name=ws.name if ws else settings.display_name,
        slug=ws.slug if ws else "default",
        display_name=settings.display_name,
        default_project_visibility=settings.default_project_visibility,  # type: ignore[arg-type]
        session_idle_timeout_min=settings.session_idle_timeout_min,
        session_absolute_timeout_min=settings.session_absolute_timeout_min,
        trash_retention_days=settings.trash_retention_days,
        mcp_key_max_ttl_days=settings.mcp_key_max_ttl_days,
        air_gap_mode=settings.air_gap_mode,
        default_skip_loaded_sequence_numbers=settings.default_skip_loaded_sequence_numbers,
        issue_export_enabled=settings.issue_export_enabled,
        issue_import_enabled=settings.issue_import_enabled,
        issue_export_allowed_roles=list(
            settings.issue_export_allowed_roles or ["workspace_admin", "project_admin", "member"]
        ),
        updated_at=settings.updated_at,
    )
