# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""REST API router for project repository bindings (KB-P5-19b, S14.2, S14.3, S11.4)."""

from __future__ import annotations

import logging
import re
import shutil
import uuid
from datetime import datetime  # noqa: TC003
from typing import Annotated, Final, Literal

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.repo_binding import ProjectRepoBinding
from database.models.workspace_settings import WorkspaceSettings
from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.problems import ProblemException, not_found
from kanban.api.timing import timing_floor
from kanban.repos.mirror import (
    MirrorManager,
    MirrorPolicy,
    MirrorSizeLimitError,
    MirrorTimeoutError,
)
from kanban.repos.url_policy import validate_remote_url
from kanban.security.envelope import KekProvider, StaticKekProvider, seal_bound
from kanban.services.projects import get_project_or_404

__all__ = [
    "RepoBindingCreateRequest",
    "RepoBindingResponse",
    "router",
]

logger = logging.getLogger(__name__)
router = APIRouter(tags=["repo-bindings"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]

_SLUG_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
_REF_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")
_AAL2_MIN_LEVEL: Final[int] = 2


class RepoBindingCreateRequest(BaseModel):
    """Payload for creating a project repository binding."""

    model_config = ConfigDict(extra="forbid", strict=True)

    slug: str = Field(description="URL-safe binding slug matching ^[a-z0-9][a-z0-9-]{1,62}$")
    remote_url: str = Field(description="Remote Git URL (https or ssh)", max_length=2048)
    default_ref: str = Field(default="main", description="Default branch or commit ref")
    access_mode: Literal["bare_git_tools", "ro_vfs_mount"] = Field(
        description="Agent repository mount and access mode"
    )
    credential: str | None = Field(
        default=None,
        description="Optional deploy key or access token (write-only)",
    )

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        """Validate slug against naming regex."""
        if not _SLUG_RE.match(v):
            msg = f"Invalid slug '{v}'; must match '^[a-z0-9][a-z0-9-]{{1,62}}$'"
            raise ValueError(msg)
        return v

    @field_validator("default_ref")
    @classmethod
    def validate_ref(cls, v: str) -> str:
        """Validate git ref disallowing directory traversal or command injection."""
        if ".." in v or not _REF_RE.match(v) or ";" in v:
            msg = (
                f"Invalid default_ref '{v}'; must match '^[A-Za-z0-9._/-]{{1,200}}$' "
                "and not contain '..'"
            )
            raise ValueError(msg)
        return v


class RepoBindingResponse(BaseModel):
    """Public representation of a project repository binding (credentials omitted)."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    workspace_id: uuid.UUID
    project_id: uuid.UUID
    slug: str
    remote_url: str
    default_ref: str
    access_mode: str
    last_fetched_commit: str | None = None
    last_fetched_at: datetime | None = None
    last_fetch_error: str | None = None
    created_by: uuid.UUID
    created_at: datetime


def _get_kek(request: Request) -> KekProvider:
    """Retrieve KEK provider from app state or return fallback."""
    kek: KekProvider | None = getattr(request.app.state, "kek_provider", None)
    if kek is not None:
        return kek
    key_material = getattr(request.app.state, "key_material", None)
    if key_material is not None:
        resolved = StaticKekProvider(
            {key_material.master_kek_kid: key_material.master_kek},
            current=key_material.master_kek_kid,
        )
        request.app.state.kek_provider = resolved
        return resolved
    fallback = StaticKekProvider({"kek-v1": b"k" * 32}, current="kek-v1")
    request.app.state.kek_provider = fallback
    return fallback


async def _is_project_admin(session: AsyncSession, project_id: uuid.UUID) -> bool:
    """Return True if caller holds admin capability on the project."""
    stmt = text(
        "SELECT app_principal_has_role(:project_id, "
        "ARRAY['PROJECT_ADMIN', 'WORKSPACE_ADMIN', 'SERVER_ADMIN']) "
        "OR app_has_object_capability(:project_id, 64)"
    )
    return bool((await session.execute(stmt, {"project_id": project_id})).scalar_one())


def _require_aal2(caller: PrincipalContext) -> None:
    """Ensure caller has active AAL2 session for mutating operations."""
    if caller.aal_level < _AAL2_MIN_LEVEL:
        raise ProblemException(
            code="AAL2_REQUIRED",
            status=403,
            title="AAL2 Authentication Required",
            detail="This operation requires multi-factor authentication (AAL2).",
        )


async def _check_binding_in_use(session: AsyncSession, binding: ProjectRepoBinding) -> bool:
    """Check if repository binding is referenced by an enabled workflow hook with repo access."""
    res_table = await session.execute(
        text("SELECT to_regclass('workflow_transition_hooks') IS NOT NULL")
    )
    table_exists = res_table.scalar_one()
    if not table_exists:
        return False

    stmt = text(
        "SELECT 1 FROM workflow_transition_hooks wth "
        "JOIN agent_definitions ad ON ad.id = wth.agent_definition_id "
        "WHERE wth.project_id = :project_id "
        "  AND wth.is_enabled = TRUE "
        "  AND ad.repo_access_mode != 'none' "
        "LIMIT 1"
    )
    res = await session.execute(stmt, {"project_id": binding.project_id})
    return res.scalar_one_or_none() is not None


@router.get(
    "/projects/{project}/repo-bindings",
    response_model=list[RepoBindingResponse],
    summary="List repository bindings for a project",
)
async def list_repo_bindings(
    project: str,
    caller: Caller,
    session: Session,
) -> list[RepoBindingResponse]:
    """List repository bindings for project. S3.4: returns 404 for non-admins."""
    async with timing_floor(floor_ms=25.0):
        proj = await get_project_or_404(session, caller, project)
        if not await _is_project_admin(session, proj.id):
            not_found()

        stmt = (
            select(ProjectRepoBinding)
            .where(
                ProjectRepoBinding.project_id == proj.id,
                ProjectRepoBinding.workspace_id == caller.workspace_id,
            )
            .order_by(ProjectRepoBinding.slug)
        )
        rows = list((await session.execute(stmt)).scalars().all())
        return [
            RepoBindingResponse(
                id=r.id,
                workspace_id=r.workspace_id,
                project_id=r.project_id,
                slug=r.slug,
                remote_url=r.remote_url,
                default_ref=r.default_ref,
                access_mode=r.access_mode,
                last_fetched_commit=r.last_fetched_commit,
                last_fetched_at=r.last_fetched_at,
                last_fetch_error=r.last_fetch_error,
                created_by=r.created_by,
                created_at=r.created_at,
            )
            for r in rows
        ]


@router.post(
    "/projects/{project}/repo-bindings",
    status_code=status.HTTP_201_CREATED,
    response_model=RepoBindingResponse,
    summary="Create a repository binding for a project",
)
async def create_repo_binding(  # noqa: PLR0913, PLR0917
    project: str,
    body: RepoBindingCreateRequest,
    caller: Caller,
    session: Session,
    request: Request,
    response: Response,
) -> RepoBindingResponse:
    """Create project repository binding and initialize mirror."""
    async with timing_floor(floor_ms=25.0):
        proj = await get_project_or_404(session, caller, project)
        if not await _is_project_admin(session, proj.id):
            not_found()
        _require_aal2(caller)

        # Check existing slug uniqueness
        existing_stmt = select(ProjectRepoBinding.id).where(
            ProjectRepoBinding.project_id == proj.id,
            ProjectRepoBinding.slug == body.slug,
        )
        if (await session.execute(existing_stmt)).scalar_one_or_none() is not None:
            raise ProblemException(
                code="SLUG_ALREADY_EXISTS",
                status=409,
                title="Slug Already Exists",
                detail=(
                    f"A repository binding with slug '{body.slug}' already exists in this project"
                ),
            )

        # Load workspace settings for air gap and CIDR policies
        ws_stmt = select(WorkspaceSettings.air_gap_mode).where(
            WorkspaceSettings.workspace_id == caller.workspace_id
        )
        air_gap_mode = (await session.execute(ws_stmt)).scalar_one_or_none() or False
        allowed_cidrs = getattr(request.app.state, "allowed_git_cidrs", None)
        dns_resolver = getattr(request.app.state, "git_dns_resolver", None)

        # Strict URL validation
        validated = validate_remote_url(
            body.remote_url,
            allowed_git_cidrs=allowed_cidrs,
            air_gap_mode=air_gap_mode,
            resolver=dns_resolver,
        )

        binding_id = uuid.uuid4()
        credential_ct: bytes | None = None
        credential_kid: str | None = None

        if body.credential:
            kek = _get_kek(request)
            aad = f"kanban/repo-binding/v1|{binding_id}|{proj.id}".encode()
            sealed = seal_bound(body.credential.encode(), aad, kek)
            wrapped_len = len(sealed.wrapped_dek).to_bytes(2, "big")
            credential_ct = wrapped_len + sealed.wrapped_dek + sealed.encrypted_secret_blob
            credential_kid = sealed.dek_kid

        binding = ProjectRepoBinding(
            id=binding_id,
            workspace_id=caller.workspace_id,
            project_id=proj.id,
            slug=body.slug,
            remote_url=body.remote_url,
            default_ref=body.default_ref,
            access_mode=body.access_mode,
            credential_ciphertext=credential_ct,
            credential_dek_kid=credential_kid,
            created_by=caller.principal_id,
        )
        session.add(binding)
        await session.flush()

        # Execute mirror clone
        mirror_mgr = getattr(request.app.state, "mirror_manager", None)
        if mirror_mgr is None:
            mirror_mgr = MirrorManager(
                policy=MirrorPolicy(allow_file_protocol=False),
                kek_provider=_get_kek(request),
            )
        else:
            mirror_mgr.kek_provider = _get_kek(request)

        try:
            await mirror_mgr.clone_or_fetch(
                binding,
                allowed_git_cidrs=allowed_cidrs,
                air_gap_mode=air_gap_mode,
                resolver=dns_resolver,
                pinned_ip=validated.pinned_ip,
            )
        except (RuntimeError, OSError, MirrorSizeLimitError, MirrorTimeoutError) as exc:
            logger.warning("Initial mirror clone failed: %s", exc)

        await session.flush()
        response.headers["Location"] = f"/api/v1/projects/{project}/repo-bindings/{binding.id}"

        return RepoBindingResponse(
            id=binding.id,
            workspace_id=binding.workspace_id,
            project_id=binding.project_id,
            slug=binding.slug,
            remote_url=binding.remote_url,
            default_ref=binding.default_ref,
            access_mode=binding.access_mode,
            last_fetched_commit=binding.last_fetched_commit,
            last_fetched_at=binding.last_fetched_at,
            last_fetch_error=binding.last_fetch_error,
            created_by=binding.created_by,
            created_at=binding.created_at,
        )


@router.post(
    "/repo-bindings/{binding_id}/refresh",
    response_model=RepoBindingResponse,
    summary="Refresh repository mirror",
)
async def refresh_repo_binding(
    binding_id: uuid.UUID,
    caller: Caller,
    session: Session,
    request: Request,
) -> RepoBindingResponse:
    """Fetch latest updates for bare Git mirror."""
    async with timing_floor(floor_ms=25.0):
        stmt = select(ProjectRepoBinding).where(
            ProjectRepoBinding.id == binding_id,
            ProjectRepoBinding.workspace_id == caller.workspace_id,
        )
        binding = (await session.execute(stmt)).scalar_one_or_none()
        if binding is None:
            not_found()

        if not await _is_project_admin(session, binding.project_id):
            not_found()
        _require_aal2(caller)

        ws_stmt = select(WorkspaceSettings.air_gap_mode).where(
            WorkspaceSettings.workspace_id == caller.workspace_id
        )
        air_gap_mode = (await session.execute(ws_stmt)).scalar_one_or_none() or False
        allowed_cidrs = getattr(request.app.state, "allowed_git_cidrs", None)
        dns_resolver = getattr(request.app.state, "git_dns_resolver", None)

        mirror_mgr = getattr(request.app.state, "mirror_manager", None)
        if mirror_mgr is None:
            mirror_mgr = MirrorManager(
                policy=MirrorPolicy(allow_file_protocol=False),
                kek_provider=_get_kek(request),
            )
        else:
            mirror_mgr.kek_provider = _get_kek(request)

        try:
            await mirror_mgr.clone_or_fetch(
                binding,
                allowed_git_cidrs=allowed_cidrs,
                air_gap_mode=air_gap_mode,
                resolver=dns_resolver,
            )
        except (RuntimeError, OSError, MirrorSizeLimitError, MirrorTimeoutError) as exc:
            logger.warning("Repository refresh failed: %s", exc)

        await session.flush()
        return RepoBindingResponse(
            id=binding.id,
            workspace_id=binding.workspace_id,
            project_id=binding.project_id,
            slug=binding.slug,
            remote_url=binding.remote_url,
            default_ref=binding.default_ref,
            access_mode=binding.access_mode,
            last_fetched_commit=binding.last_fetched_commit,
            last_fetched_at=binding.last_fetched_at,
            last_fetch_error=binding.last_fetch_error,
            created_by=binding.created_by,
            created_at=binding.created_at,
        )


@router.delete(
    "/repo-bindings/{binding_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a repository binding",
)
async def delete_repo_binding(
    binding_id: uuid.UUID,
    caller: Caller,
    session: Session,
    request: Request,
) -> Response:
    """Delete repository binding and prune bare mirror from filesystem."""
    async with timing_floor(floor_ms=25.0):
        stmt = select(ProjectRepoBinding).where(
            ProjectRepoBinding.id == binding_id,
            ProjectRepoBinding.workspace_id == caller.workspace_id,
        )
        binding = (await session.execute(stmt)).scalar_one_or_none()
        if binding is None:
            not_found()

        if not await _is_project_admin(session, binding.project_id):
            not_found()
        _require_aal2(caller)

        in_use = await _check_binding_in_use(session, binding)
        if in_use:
            msg_in_use = (
                "Repository binding is referenced by an enabled workflow hook "
                "with active repository access"
            )
            raise ProblemException(
                code="REPO_BINDING_IN_USE",
                status=409,
                title="Repository Binding In Use",
                detail=msg_in_use,
            )

        mirror_mgr = getattr(request.app.state, "mirror_manager", None)
        if mirror_mgr is None:
            mirror_mgr = MirrorManager(policy=MirrorPolicy(allow_file_protocol=False))
        m_path = mirror_mgr.mirror_path(binding)
        if m_path.exists():
            shutil.rmtree(m_path, ignore_errors=True)

        await session.delete(binding)
        await session.flush()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
