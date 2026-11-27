"""Issue move endpoint with 25ms timing floor (KB-P3-12, S6.4)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.timing import timing_floor
from kanban.api.v1.schemas.issue_move import (
    IssueMoveRequest,
    IssueMoveResponse,
)
from kanban.services.issue_keys import resolve_issue_ref
from kanban.services.issue_move import move_issue

router = APIRouter(tags=["issues"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


@router.post(
    "/issues/{issue_ref}/move",
    response_model=IssueMoveResponse,
    response_model_exclude_none=False,
    summary="Move or reorder an issue on the board",
)
async def post_issue_move(
    issue_ref: str,
    body: IssueMoveRequest,
    caller: Caller,
    session: Session,
    response: Response,
) -> IssueMoveResponse:
    """Move an issue across columns or reorder it within a column (S6.4)."""
    async with timing_floor(floor_ms=25.0):
        await resolve_issue_ref(session, caller, issue_ref)
        res = await move_issue(session, caller, issue_ref, body, response=response)
        await session.commit()
        return res
