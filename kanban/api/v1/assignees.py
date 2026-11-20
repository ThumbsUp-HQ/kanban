# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Hybrid assignees and autocomplete suggestions endpoints (S7.2 8b, S3.4; KB-P3-03)."""

from __future__ import annotations

import uuid  # noqa: TC003  # Required at runtime by FastAPI path parameter resolution
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession  # Required by FastAPI dependency injection

from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.timing import timing_floor
from kanban.api.v1.schemas.assignees import (
    AssigneeCreate,
    AssigneeResponse,
    AssigneeSuggestionsResponse,
)
from kanban.services import assignees as svc

router = APIRouter(tags=["assignees"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


@router.post(
    "/issues/{issue_ref}/assignees",
    status_code=201,
    response_model=AssigneeResponse,
    summary="Add an assignee to an issue",
)
async def add_assignee(
    issue_ref: str,
    body: AssigneeCreate,
    caller: Caller,
    session: Session,
) -> AssigneeResponse:
    """Assign an eligible project viewer or free-text external label to an issue (EDIT required)."""
    async with timing_floor(floor_ms=25.0):
        return await svc.add_assignee(session, caller, issue_ref, body)


@router.delete(
    "/issues/{issue_ref}/assignees/{assignee_id}",
    status_code=204,
    summary="Remove an assignee from an issue",
)
async def remove_assignee(
    issue_ref: str,
    assignee_id: uuid.UUID,
    caller: Caller,
    session: Session,
) -> Response:
    """Remove an assignee join from an issue (EDIT required)."""
    async with timing_floor(floor_ms=25.0):
        await svc.remove_assignee(session, caller, issue_ref, assignee_id)
        return Response(status_code=204)


@router.get(
    "/projects/{project_ref}/assignee-suggestions",
    response_model=AssigneeSuggestionsResponse,
    summary="Get access-filtered assignee suggestions",
)
async def get_assignee_suggestions(
    project_ref: str,
    caller: Caller,
    session: Session,
    q: Annotated[
        str,
        Query(
            description="Case-insensitive prefix query (0..64 chars)",
            min_length=0,
            max_length=64,
        ),
    ] = "",
    limit: Annotated[int, Query(description="Max suggestions to return (1..20)", ge=1, le=20)] = 10,
) -> AssigneeSuggestionsResponse:
    """Return autocomplete suggestions of active project viewers with zero cross-scope leakage."""
    async with timing_floor(floor_ms=25.0):
        return await svc.get_assignee_suggestions(session, caller, project_ref, q, limit)
