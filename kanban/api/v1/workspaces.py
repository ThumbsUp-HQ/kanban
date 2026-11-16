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

from database.session import RLSContext
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
    from database.session import RLSSessionFactory
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
    stmt = text("SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])")
    is_server_admin = bool((await session.execute(stmt)).scalar_one())

    session_factory: RLSSessionFactory | None = getattr(request.app.state, "session_factory", None)
    workspaces: list[WorkspaceResponse] = []

    if session_factory is not None:
        anon_ctx = RLSContext(principal_id=caller.principal_id, workspace_id=uuid.UUID(int=0))
        async with session_factory.session(anon_ctx) as global_session:
            if is_server_admin:
                res = await global_session.execute(
                    text("SELECT id, name, slug FROM workspaces ORDER BY created_at ASC")
                )
                workspaces.extend(
                    WorkspaceResponse(
                        id=row.id,
                        name=row.name,
                        slug=row.slug,
                        is_current=(row.id == caller.workspace_id),
                        role="SERVER_ADMIN",
                    )
                    for row in res.fetchall()
                )
            else:
                u_res = await session.execute(
                    text("SELECT email FROM users WHERE id = :p_id"),
                    {"p_id": caller.principal_id},
                )
                user_email = u_res.scalar_one_or_none()

                found_ids: set[uuid.UUID] = set()
                if user_email:
                    q = text(
                        "SELECT DISTINCT w.id, w.name, w.slug, rb.role "
                        "FROM workspaces w "
                        "JOIN principals p ON p.workspace_id = w.id "
                        "JOIN users u ON u.id = p.id "
                        "LEFT JOIN role_bindings rb ON rb.workspace_id = w.id "
                        "AND rb.principal_id = p.id "
                        "WHERE lower(u.email) = lower(:email) AND p.status = 'ACTIVE' "
                        "ORDER BY w.name ASC"
                    )
                    for r in (await global_session.execute(q, {"email": user_email})).fetchall():
                        found_ids.add(r.id)
                        workspaces.append(
                            WorkspaceResponse(
                                id=r.id,
                                name=r.name,
                                slug=r.slug,
                                is_current=(r.id == caller.workspace_id),
                                role=r.role,
                            )
                        )

                if caller.workspace_id not in found_ids:
                    curr_q = text("SELECT id, name, slug FROM workspaces WHERE id = :ws_id")
                    curr_row = (
                        await global_session.execute(curr_q, {"ws_id": caller.workspace_id})
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
    else:
        res = await session.execute(
            text("SELECT id, name, slug FROM workspaces WHERE id = :ws_id"),
            {"ws_id": caller.workspace_id},
        )
        row = res.first()
        if row:
            workspaces.append(
                WorkspaceResponse(
                    id=row.id,
                    name=row.name,
                    slug=row.slug,
                    is_current=True,
                )
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
    session_factory: RLSSessionFactory | None = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        raise ProblemException(
            code="INTERNAL_ERROR",
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            title="Internal Server Error",
            detail="Session factory is not available.",
        )

    anon_ctx = RLSContext(principal_id=caller.principal_id, workspace_id=uuid.UUID(int=0))
    async with session_factory.session(anon_ctx) as global_session:
        existing = await global_session.execute(
            text("SELECT id FROM workspaces WHERE slug = :slug"),
            {"slug": body.slug},
        )
        if existing.scalar_one_or_none():
            raise ProblemException(
                code="WORKSPACE_SLUG_CONFLICT",
                status=status.HTTP_409_CONFLICT,
                title="Workspace Slug Conflict",
                detail=f"Workspace slug '{body.slug}' is already taken.",
            )

        caller_info = (
            (
                await session.execute(
                    text(
                        "SELECT u.email, p.display_name, o.canonical_key "
                        "FROM users u "
                        "JOIN principals p ON p.id = u.id "
                        "JOIN objects o ON o.id = u.id "
                        "WHERE u.id = :p_id"
                    ),
                    {"p_id": caller.principal_id},
                )
            )
            .mappings()
            .first()
        )

        new_ws_id = uuid.uuid4()
        new_principal_id = uuid.uuid4()

        email = caller_info["email"] if caller_info else "admin@local.kanban"
        display_name = caller_info["display_name"] if caller_info else "Workspace Admin"
        ckey = caller_info["canonical_key"] if caller_info else f"usr-{new_principal_id.hex[:12]}"

        # 1. Create workspace
        await global_session.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
            {"id": new_ws_id, "slug": body.slug, "name": body.name},
        )

        # 2. Register user object in new workspace
        await global_session.execute(
            text(
                "SELECT register_object("
                "  'user'::object_kind, :ws_id, NULL, :ckey, :name, :p_id, :p_id"
                ")"
            ),
            {"ws_id": new_ws_id, "ckey": ckey, "name": display_name, "p_id": new_principal_id},
        )

        # 3. Create principal
        await global_session.execute(
            text(
                "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
                "VALUES (:id, 'USER', :ws_id, :name, 'ACTIVE')"
            ),
            {"id": new_principal_id, "ws_id": new_ws_id, "name": display_name},
        )

        # 4. Create user record
        await global_session.execute(
            text(
                "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
                "VALUES (:id, 'user', 'USER', :ws_id, :email)"
            ),
            {"id": new_principal_id, "ws_id": new_ws_id, "email": email},
        )

        # 5. Bind WORKSPACE_ADMIN role
        await global_session.execute(
            text(
                "INSERT INTO role_bindings "
                "(id, workspace_id, principal_id, role, scope_type, project_id) "
                "VALUES (:id, :ws_id, :p_id, 'WORKSPACE_ADMIN', 'workspace', NULL)"
            ),
            {"id": uuid.uuid4(), "ws_id": new_ws_id, "p_id": new_principal_id},
        )

        # Check if caller has SERVER_ADMIN in current workspace
        stmt = text("SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])")
        is_server_admin = bool((await session.execute(stmt)).scalar_one())
        if is_server_admin:
            await global_session.execute(
                text(
                    "INSERT INTO role_bindings "
                    "(id, workspace_id, principal_id, role, scope_type, project_id) "
                    "VALUES (:id, :ws_id, :p_id, 'SERVER_ADMIN', 'server', NULL)"
                ),
                {"id": uuid.uuid4(), "ws_id": new_ws_id, "p_id": new_principal_id},
            )

        await global_session.commit()

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
async def switch_workspace_endpoint(  # noqa: C901
    workspace_id: uuid.UUID,
    caller: Annotated[PrincipalContext, Depends(get_principal)],
    _session: Annotated[AsyncSession, Depends(get_rls_session)],
    request: Request,
) -> Response:
    """Switch caller's active session to the target workspace."""
    session_factory: RLSSessionFactory | None = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        raise ProblemException(
            code="INTERNAL_ERROR",
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            title="Internal Server Error",
            detail="Session factory is not available.",
        )

    anon_ctx = RLSContext(principal_id=caller.principal_id, workspace_id=uuid.UUID(int=0))
    async with session_factory.session(anon_ctx) as global_session:
        target_ws = (
            await global_session.execute(
                text("SELECT id, name, slug FROM workspaces WHERE id = :id"),
                {"id": workspace_id},
            )
        ).first()

        if not target_ws:
            raise ProblemException(
                code="WORKSPACE_NOT_FOUND",
                status=status.HTTP_404_NOT_FOUND,
                title="Workspace Not Found",
                detail=f"Target workspace {workspace_id} does not exist.",
            )

        # Check if caller is SERVER_ADMIN anywhere on system
        server_admin_res = await global_session.execute(
            text(
                "SELECT 1 FROM role_bindings "
                "WHERE principal_id = :p_id AND role = 'SERVER_ADMIN' "
                "LIMIT 1"
            ),
            {"p_id": caller.principal_id},
        )
        is_server_admin = server_admin_res.scalar_one_or_none() is not None

        target_principal_id: uuid.UUID | None = None

        # Check if caller's principal_id belongs to target workspace
        direct_p = (
            await global_session.execute(
                text(
                    "SELECT id FROM principals "
                    "WHERE id = :p_id AND workspace_id = :ws_id AND status = 'ACTIVE'"
                ),
                {"p_id": caller.principal_id, "ws_id": workspace_id},
            )
        ).scalar_one_or_none()
        if direct_p:
            target_principal_id = direct_p

        if target_principal_id is None:
            u_res = await global_session.execute(
                text(
                    "SELECT email, display_name FROM users u "
                    "JOIN principals p ON p.id = u.id "
                    "WHERE u.id = :p_id"
                ),
                {"p_id": caller.principal_id},
            )
            caller_row = u_res.mappings().first()

            if caller_row and caller_row["email"]:
                target_p = (
                    await global_session.execute(
                        text(
                            "SELECT p.id FROM principals p "
                            "JOIN users u ON u.id = p.id "
                            "WHERE p.workspace_id = :ws_id "
                            "AND lower(u.email) = lower(:email) "
                            "AND p.status = 'ACTIVE' "
                            "LIMIT 1"
                        ),
                        {"ws_id": workspace_id, "email": caller_row["email"]},
                    )
                ).scalar_one_or_none()
                if target_p:
                    target_principal_id = target_p

        if target_principal_id is None:
            if is_server_admin:
                new_pid = uuid.uuid4()
                email = caller_row["email"] if caller_row else "server-admin@local.kanban"
                display_name = caller_row["display_name"] if caller_row else "Server Admin"
                ckey = f"usr-{new_pid.hex[:12]}"

                await global_session.execute(
                    text(
                        "SELECT register_object("
                        "  'user'::object_kind, :ws_id, NULL, :ckey, :name, :p_id, :p_id"
                        ")"
                    ),
                    {"ws_id": workspace_id, "ckey": ckey, "name": display_name, "p_id": new_pid},
                )
                await global_session.execute(
                    text(
                        "INSERT INTO principals "
                        "(id, principal_type, workspace_id, display_name, status) "
                        "VALUES (:id, 'USER', :ws_id, :name, 'ACTIVE')"
                    ),
                    {"id": new_pid, "ws_id": workspace_id, "name": display_name},
                )
                await global_session.execute(
                    text(
                        "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
                        "VALUES (:id, 'user', 'USER', :ws_id, :email)"
                    ),
                    {"id": new_pid, "ws_id": workspace_id, "email": email},
                )
                await global_session.execute(
                    text(
                        "INSERT INTO role_bindings "
                        "(id, workspace_id, principal_id, role, scope_type, project_id) "
                        "VALUES (:id, :ws_id, :p_id, 'SERVER_ADMIN', 'server', NULL)"
                    ),
                    {"id": uuid.uuid4(), "ws_id": workspace_id, "p_id": new_pid},
                )
                target_principal_id = new_pid
            else:
                raise ProblemException(
                    code="FORBIDDEN_WORKSPACE_SWITCH",
                    status=status.HTTP_403_FORBIDDEN,
                    title="Forbidden Workspace Switch",
                    detail="Principal is not a member of target workspace.",
                )

        session_service: SessionService | None = getattr(request.app.state, "session_service", None)
        if session_service is not None:
            issued = await session_service.create_after_login(
                global_session,
                principal_id=target_principal_id,
                workspace_id=workspace_id,
                aal_level=caller.aal_level,
                existing_cookie=request.cookies.get(SESSION_COOKIE_NAME),
            )
            await global_session.commit()

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
