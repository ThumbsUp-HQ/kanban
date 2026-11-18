# Copyright 2026 Kanban Platform Contributors
"""Docs and hierarchical Pages endpoints (S8.1, S12.2, S3.4)."""

from __future__ import annotations

import uuid  # noqa: TC003  # Required at runtime by FastAPI query parameter parsing
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.timing import timing_floor
from kanban.api.v1.schemas.docs import (
    DocCreate,
    DocResponse,
    DocSummaryResponse,
    DocUpdate,
    PageCreate,
    PageMove,
    PageResponse,
    PageTreeNode,
    PageUpdate,
    PageVersionResponse,
)
from kanban.services import docs as svc
from kanban.services.projects import get_project_or_404

router = APIRouter(tags=["docs"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


# =========================================================================
# DOCS ENDPOINTS
# =========================================================================


@router.get("/docs", response_model=list[DocSummaryResponse], summary="List readable docs")
async def list_docs(
    caller: Caller,
    session: Session,
    project: Annotated[uuid.UUID | None, Query()] = None,
) -> list[DocSummaryResponse]:
    """List documents visible to the caller filtered by workspace and optional project."""
    return await svc.list_docs(session, caller, project_id=project)


@router.post("/docs", status_code=201, response_model=DocResponse, summary="Create a document")
async def create_doc(
    body: DocCreate,
    caller: Caller,
    session: Session,
    response: Response,
) -> DocResponse:
    """Create a new top-level documentation entity."""
    result, etag = await svc.create_doc(session, caller, body)
    response.headers["ETag"] = etag
    response.headers["Location"] = f"/api/v1/docs/{result.canonical_key}"
    return result


@router.get("/docs/{doc_ref:path}/tree", response_model=list[PageTreeNode], summary="Get page tree")
async def get_doc_tree(
    doc_ref: str,
    caller: Caller,
    session: Session,
) -> list[PageTreeNode]:
    """Retrieve full hierarchical page tree with restricted ancestor masking."""
    return await svc.get_doc_tree(session, caller, doc_ref)


@router.get(
    "/projects/{project_ref}/docs/tree",
    response_model=list[PageTreeNode],
    summary="Get project page tree",
)
async def get_project_docs_tree(
    project_ref: str,
    caller: Caller,
    session: Session,
) -> list[PageTreeNode]:
    """Retrieve full hierarchical page tree for a project."""
    project = await get_project_or_404(session, caller, project_ref)
    docs = await svc.list_docs(session, caller, project_id=project.id)
    tree: list[PageTreeNode] = []
    for d in docs:
        sub = await svc.get_doc_tree(session, caller, str(d.id))
        tree.extend(sub)
    return tree


@router.post(
    "/projects/{project_ref}/docs/pages",
    status_code=201,
    response_model=PageResponse,
    summary="Create page in a project",
)
async def create_project_page(
    project_ref: str,
    body: PageCreate,
    caller: Caller,
    session: Session,
    response: Response,
) -> PageResponse:
    """Create a hierarchical page within a project, auto-creating a parent doc if needed."""
    result, etag = await svc.create_page(session, caller, project_ref, body)
    response.headers["ETag"] = etag
    response.headers["Location"] = f"/api/v1/pages/{result.canonical_key}"
    return result


@router.post(
    "/docs/{doc_ref:path}/pages",
    status_code=201,
    response_model=PageResponse,
    summary="Create a page",
)
async def create_page(
    doc_ref: str,
    body: PageCreate,
    caller: Caller,
    session: Session,
    response: Response,
) -> PageResponse:
    """Create a hierarchical page within a document."""
    result, etag = await svc.create_page(session, caller, doc_ref, body)
    response.headers["ETag"] = etag
    response.headers["Location"] = f"/api/v1/pages/{result.canonical_key}"
    return result


@router.get("/docs/{doc_ref:path}", response_model=DocResponse, summary="Get a document")
async def get_doc(
    doc_ref: str,
    caller: Caller,
    session: Session,
    response: Response,
    if_none_match: Annotated[str | None, Header()] = None,
) -> Response | DocResponse:
    """Return a document with ETag caching, or timing-equalized 404 when absent or unreadable."""
    async with timing_floor(floor_ms=25.0):
        result, etag = await svc.get_doc(session, caller, doc_ref)
        if if_none_match and (if_none_match.strip() in (etag, etag.strip('"'), "*")):
            return Response(status_code=304, headers={"ETag": etag})
        response.headers["ETag"] = etag
        return result


@router.patch("/docs/{doc_ref:path}", response_model=DocResponse, summary="Update a document")
async def update_doc(  # noqa: PLR0913
    doc_ref: str,
    body: DocUpdate,
    *,
    caller: Caller,
    session: Session,
    response: Response,
    if_match: Annotated[str | None, Header()] = None,
) -> DocResponse:
    """Update document metadata or body under optimistic concurrency."""
    result, etag = await svc.update_doc(session, caller, doc_ref, body, if_match)
    response.headers["ETag"] = etag
    return result


@router.delete("/docs/{doc_ref:path}", status_code=200, summary="Delete a document")
async def delete_doc(
    doc_ref: str,
    caller: Caller,
    session: Session,
) -> dict[str, str]:
    """Soft-trash document and all hierarchical pages."""
    await svc.delete_doc(session, caller, doc_ref)
    return {"status": "deleted"}


# =========================================================================
# PAGES ENDPOINTS
# =========================================================================


@router.post(
    "/pages/{page_ref:path}/versions/{version_seq:int}/restore",
    response_model=PageResponse,
    summary="Restore a historical page version",
)
async def restore_page_version(  # noqa: PLR0913
    page_ref: str,
    version_seq: int,
    *,
    caller: Caller,
    session: Session,
    response: Response,
    if_match: Annotated[str | None, Header()] = None,
) -> PageResponse:
    """Restore historical version content into the current page under If-Match concurrency."""
    result, etag = await svc.restore_page_version(session, caller, page_ref, version_seq, if_match)
    response.headers["ETag"] = etag
    return result


@router.get(
    "/pages/{page_ref:path}/versions/{version_seq:int}",
    response_model=PageVersionResponse,
    summary="Get a page version",
)
async def get_page_version(
    page_ref: str,
    version_seq: int,
    caller: Caller,
    session: Session,
) -> PageVersionResponse:
    """Retrieve a single historical version snapshot of a page."""
    async with timing_floor(floor_ms=25.0):
        return await svc.get_page_version(session, caller, page_ref, version_seq)


@router.get(
    "/pages/{page_ref:path}/versions",
    response_model=list[PageVersionResponse],
    summary="List page versions",
)
async def list_page_versions(
    page_ref: str,
    caller: Caller,
    session: Session,
    cursor: Annotated[int | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[PageVersionResponse]:
    """List historical version snapshots of a page with pagination."""
    async with timing_floor(floor_ms=25.0):
        return await svc.list_page_versions(session, caller, page_ref, cursor=cursor, limit=limit)


@router.post("/pages/{page_ref:path}/move", response_model=PageResponse, summary="Move a page")
async def move_page(
    page_ref: str,
    body: PageMove,
    caller: Caller,
    session: Session,
) -> PageResponse:
    """Move a page to a new parent or re-order among siblings."""
    return await svc.move_page(session, caller, page_ref, body)


@router.get("/pages/{page_ref:path}", response_model=PageResponse, summary="Get a page")
async def get_page(
    page_ref: str,
    caller: Caller,
    session: Session,
    response: Response,
    if_none_match: Annotated[str | None, Header()] = None,
) -> Response | PageResponse:
    """Return a page with ETag caching, or timing-equalized 404 when absent or unreadable."""
    async with timing_floor(floor_ms=25.0):
        result, etag = await svc.get_page(session, caller, page_ref)
        if if_none_match and (if_none_match.strip() in (etag, etag.strip('"'), "*")):
            return Response(status_code=304, headers={"ETag": etag})
        response.headers["ETag"] = etag
        return result


@router.patch("/pages/{page_ref:path}", response_model=PageResponse, summary="Update a page")
async def update_page(  # noqa: PLR0913
    page_ref: str,
    body: PageUpdate,
    *,
    caller: Caller,
    session: Session,
    response: Response,
    if_match: Annotated[str | None, Header()] = None,
) -> PageResponse:
    """Update page title or body under optimistic concurrency."""
    result, etag = await svc.update_page(session, caller, page_ref, body, if_match)
    response.headers["ETag"] = etag
    return result


@router.delete("/pages/{page_ref:path}", status_code=200, summary="Delete a page")
async def delete_page(
    page_ref: str,
    caller: Caller,
    session: Session,
) -> dict[str, str]:
    """Soft-trash page and all its hierarchical descendants."""
    await svc.delete_page(session, caller, page_ref)
    return {"status": "deleted"}
