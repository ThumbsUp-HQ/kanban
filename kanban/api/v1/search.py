# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Search API endpoints for issues, docs, pages, and stickies (S11.2, S11.3, S12.2, KB-P3-17)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.timing import timing_floor
from kanban.api.v1.schemas.search import (
    IssueSearchRequest,
    IssueSearchResponse,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    SearchMode,
    SearchResponse,
)
from kanban.security.read_taint import TaintRecorder, get_taint_recorder
from kanban.services import search as svc

router = APIRouter(prefix="/search", tags=["search"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


@router.get("", response_model=SearchResponse, summary="Unified cross-entity search")
async def search_unified(  # noqa: PLR0913, PLR0917
    caller: Caller,
    session: Session,
    taint_recorder: Annotated[TaintRecorder, Depends(get_taint_recorder)],
    q: Annotated[str, Query(description="Search query string")] = "",
    kinds: Annotated[
        str | None,
        Query(description="Comma-separated entity kinds (issue,doc,page,sticky)"),
    ] = None,
    project: Annotated[
        str | None,
        Query(description="Project identifier or UUID scope filter"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=50, description="Page size (1..50)")] = 20,
    cursor: Annotated[
        str | None,
        Query(description="Opaque HMAC-signed keyset pagination cursor"),
    ] = None,
    mode: Annotated[
        SearchMode,
        Query(description="Search mode: lexical or hybrid"),
    ] = "lexical",
) -> SearchResponse:
    """Execute unified search under caller RLS."""
    async with timing_floor(floor_ms=25.0):
        kinds_list = [k.strip() for k in kinds.split(",") if k.strip()] if kinds else None
        res = await svc.search_unified(
            session=session,
            caller=caller,
            query=q,
            kinds=kinds_list,
            project_ref=project,
            limit=limit,
            cursor=cursor,
            mode=mode,
        )
        pids = {item.project_identifier for item in res.items if item.project_identifier}
        if pids:
            await taint_recorder.record_project_ids(pids)
        return res


@router.post("/issues", response_model=IssueSearchResponse, summary="Structured issue search")
async def search_issues(
    body: IssueSearchRequest,
    caller: Caller,
    session: Session,
    request: Request,
    taint_recorder: Annotated[TaintRecorder, Depends(get_taint_recorder)],
) -> IssueSearchResponse:
    """Execute issue-scoped search composed with FilterSpec DSL predicates."""
    ws_scope = body.workspace or request.headers.get("x-kb-scope-workspace")
    effective_body = body
    if ws_scope and not body.workspace:
        effective_body = body.model_copy(update={"workspace": ws_scope})
    async with timing_floor(floor_ms=25.0):
        res = await svc.search_issues(
            session=session,
            caller=caller,
            request=effective_body,
        )
        pids = {item.project_identifier for item in res.items if item.project_identifier}
        if pids:
            await taint_recorder.record_project_ids(pids)
        return res


@router.post(
    "/knowledge",
    response_model=KnowledgeSearchResponse,
    summary="Knowledge search across docs, pages, and stickies",
)
async def search_knowledge(
    body: KnowledgeSearchRequest,
    caller: Caller,
    session: Session,
    taint_recorder: Annotated[TaintRecorder, Depends(get_taint_recorder)],
) -> KnowledgeSearchResponse:
    """Execute knowledge search across docs, pages, and stickies under caller RLS."""
    async with timing_floor(floor_ms=25.0):
        res = await svc.search_knowledge(
            session=session,
            caller=caller,
            request=body,
        )
        pids = {item.project_identifier for item in res.items if item.project_identifier}
        if pids:
            await taint_recorder.record_project_ids(pids)
        return res
