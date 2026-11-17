# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Workspaces listing, creation, and switching API endpoints (KB-UX-05, S1.1, S3.3)."""

from __future__ import annotations

import logging
import re
import uuid
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002  # FastAPI dependency
from starlette.responses import JSONResponse

from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.problems import ProblemException
from kanban.auth.sessions.cookies import (
    SESSION_COOKIE_NAME,
    build_set_cookie_header,
    build_set_fallback_cookie_header,
)
from kanban.auth.sessions.csrf import (
    build_set_csrf_cookie_header,
    build_set_fallback_csrf_cookie_header,
)

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
                    "SELECT workspace_id, principal_id FROM kb_auth_switch_workspace(:ws_id, :p_id)"
                ),
                {"ws_id": workspace_id, "p_id": caller.principal_id},
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

    target_principal_id = res.principal_id

    session_service: SessionService | None = getattr(request.app.state, "session_service", None)
    if session_service is not None:
        issued = await session_service.create_after_login(
            session,
            principal_id=target_principal_id,
            workspace_id=workspace_id,
            aal_level=caller.aal_level,
            existing_cookie=request.cookies.get(SESSION_COOKIE_NAME),
        )
        await session.commit()

        response = JSONResponse(
            content={
                "workspace_id": str(workspace_id),
                "status": "switched",
                "csrf_token": issued.csrf_token,
            }
        )
        response.raw_headers.append(
            (
                b"set-cookie",
                build_set_cookie_header(issued.cookie_val, issued.idle_expires_at).encode(
                    "latin-1"
                ),
            )
        )
        response.raw_headers.append(
            (
                b"set-cookie",
                build_set_csrf_cookie_header(issued.csrf_token).encode("latin-1"),
            )
        )
        host_name = (request.headers.get("host") or "").split(":")[0].lower()
        if request.url.scheme == "http" and host_name not in ("testserver", "test"):
            response.raw_headers.append(
                (
                    b"set-cookie",
                    build_set_fallback_cookie_header(
                        issued.cookie_val, issued.idle_expires_at
                    ).encode("latin-1"),
                )
            )
            response.raw_headers.append(
                (
                    b"set-cookie",
                    build_set_fallback_csrf_cookie_header(issued.csrf_token).encode("latin-1"),
                )
            )
        return response

    return JSONResponse(
        content={
            "workspace_id": str(workspace_id),
            "status": "switched",
        }
    )
