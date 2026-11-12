# Copyright 2026 Kanban Platform Contributors
"""Entity resolution endpoint for human-readable references and UUIDs (S11.1)."""

from __future__ import annotations

import uuid  # noqa: TC003
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Query, Request
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


@router.get(
    "/resolve",
    response_model=ResolvedRefResponse,
    summary="Resolve human-readable reference or UUID to canonical entity identity",
)
async def resolve_entity(  # noqa: PLR0913, PLR0917
    kind: Annotated[
        str,
        Query(description="Entity kind: project, issue, state, user, cycle, module, label, hook"),
    ],
    ref: Annotated[str, Query(description="Human key, handle, or UUID reference")],
    request: Request,
    session: Annotated[AsyncSession, Depends(get_rls_session)],
    principal: Annotated[PrincipalContext, Depends(get_principal)],
    project: Annotated[
        str | None,
        Query(description="Project key context required for project-scoped kinds"),
    ] = None,
) -> ResolvedRefResponse:
    """Resolve an entity key to UUID and metadata with timing equalization anti-enumeration."""
    service: ResolutionService = getattr(request.app.state, "resolution_service", _SERVICE)
    async with timing_floor(floor_ms=25.0):
        resolved: ResolvedRef = await service.resolve(
            session=session,
            kind=kind,
            ref=ref,
            project_ref=project,
            caller_principal_id=principal.principal_id,
            caller_workspace_id=principal.workspace_id,
        )
        return ResolvedRefResponse(
            id=resolved.id,
            kind=resolved.kind,
            key=resolved.key,
            title=resolved.title,
        )
