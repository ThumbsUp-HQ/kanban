# Copyright 2026 Kanban Platform Contributors
"""Entity resolution endpoint for human-readable references and UUIDs (S11.1)."""

from __future__ import annotations

import uuid  # noqa: TC003
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.timing import timing_floor
from kanban.resolve.service import ResolutionService, ResolvedRef

__all__ = [
    "ResolvedRefResponse",
    "resolve_router",
    "router",
]

router: Final[APIRouter] = APIRouter(tags=["resolve"])
resolve_router: Final[APIRouter] = router
_SERVICE: Final[ResolutionService] = ResolutionService()


class ResolvedRefResponse(BaseModel):
    """Canonical JSON response representing a resolved entity reference."""

    id: uuid.UUID = Field(description="Unique entity identifier (UUIDv7)")
    kind: str = Field(description="Entity kind discriminator")
    key: str = Field(description="Primary human-readable key or handle")
    title: str = Field(description="Display title or name")
    workspace: str | None = Field(
        default=None, description="Workspace slug when resolved across or within workspace"
    )
    canonical_key: str | None = Field(
        default=None, description="Canonical issue key when resolved via legacy alias"
    )


@router.get(
    "/resolve",
    response_model=ResolvedRefResponse,
    response_model_exclude_none=True,
    summary="Resolve human-readable reference or UUID to canonical entity identity",
)
async def resolve_entity(  # noqa: PLR0913, PLR0917
    kind: Annotated[
        str,
        Query(description="Entity kind: project, issue, state, user, cycle, module, label, hook"),
    ],
    ref: Annotated[str, Query(description="Human key, handle, or UUID reference")],
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_rls_session)],
    principal: Annotated[PrincipalContext, Depends(get_principal)],
    project: Annotated[
        str | None,
        Query(description="Project key context required for project-scoped kinds"),
    ] = None,
    workspace: Annotated[
        str | None,
        Query(description="Workspace slug or UUID filter to constrain resolution scope"),
    ] = None,
) -> ResolvedRefResponse:
    """Resolve an entity key to UUID and metadata with timing equalization anti-enumeration."""
    service: ResolutionService = getattr(request.app.state, "resolution_service", _SERVICE)
    ws_ref = workspace or request.headers.get("x-kb-scope-workspace")
    caller_ws_id = (
        principal.workspace_id if principal.scope_tier != "global" and not ws_ref else None
    )
    async with timing_floor(floor_ms=25.0):
        resolved: ResolvedRef = await service.resolve(
            session=session,
            kind=kind,
            ref=ref,
            project_ref=project,
            caller_principal_id=principal.principal_id,
            caller_workspace_id=caller_ws_id,
            workspace_ref=ws_ref,
        )
        if resolved.is_alias or resolved.canonical_key:
            canonical = resolved.canonical_key or resolved.key
            response.headers["X-Kanban-Canonical-Key"] = canonical

        return ResolvedRefResponse(
            id=resolved.id,
            kind=resolved.kind,
            key=resolved.key,
            title=resolved.title,
            workspace=resolved.workspace,
            canonical_key=resolved.canonical_key if resolved.is_alias else None,
        )
