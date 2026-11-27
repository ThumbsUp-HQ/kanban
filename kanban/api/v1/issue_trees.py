# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Issue tree creation endpoint for atomic hierarchical issue graphs (KB-P4-05)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.timing import timing_floor
from kanban.api.v1.schemas.issue_trees import IssueTreeNode, IssueTreeResponse
from kanban.issues import tree_service as svc

router = APIRouter(tags=["issues"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


@router.post(
    "/projects/{project_ref}/issue-trees",
    status_code=201,
    response_model=IssueTreeResponse,
    summary="Create an issue tree atomically",
)
async def create_issue_tree(
    project_ref: str,
    body: IssueTreeNode,
    caller: Caller,
    session: Session,
    response: Response,
) -> IssueTreeResponse:
    """Create a parent-child issue hierarchy inside a single atomic transaction."""
    async with timing_floor(floor_ms=25.0):
        result = await svc.create_issue_tree(session, caller, project_ref, body)
        response.headers["Location"] = f"/api/v1/issues/{result.root.key}"
        await session.commit()
        return result
