# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""FastAPI router for silent per-issue Agent Workpad slot (KB-AGENT-WORKPAD-01, KAN-71)."""

from __future__ import annotations

import uuid  # noqa: TC003
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.timing import timing_floor
from kanban.issues.workpad_service import get_issue_workpad, put_issue_workpad
from kanban.security.ratelimit import ISSUE_WORKPAD_RATE_LIMIT, rate_limited

router = APIRouter(tags=["issue-workpad"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


async def _principal_rate_key(request: Request) -> list[str]:
    """Extract authenticated principal ID for rate limiting."""
    caller = await get_principal(request)
    return [str(caller.principal_id)]


class PutIssueWorkpadRequest(BaseModel):
    """Payload for updating or creating silent agent workpad slot."""

    model_config = ConfigDict(extra="forbid")

    body_markdown: Annotated[str, Field(max_length=65536)]
    revision: int | None = None


def _parse_if_match_revision(if_match: str | None, body_revision: int | None) -> int | None:
    """Extract integer revision from If-Match ETag header or request body."""
    if if_match is not None:
        clean = if_match.strip().strip('"').strip("'")
        if clean.isdigit():
            return int(clean)
    return body_revision


@router.get(
    "/issues/{issue_key}/workpad",
    summary="Retrieve silent agent workpad slot",
    dependencies=[Depends(rate_limited(ISSUE_WORKPAD_RATE_LIMIT, key_func=_principal_rate_key))],
)
async def api_get_workpad(
    issue_key: str,
    caller: Caller,
    session: Session,
    principal_id: Annotated[uuid.UUID | None, Query()] = None,
) -> JSONResponse:
    """Retrieve the workpad slot for an issue without emitting notifications."""
    async with timing_floor(floor_ms=25.0):
        workpad = await get_issue_workpad(session, caller, issue_key, principal_id=principal_id)
        sha_hex = workpad.body_sha256.hex() if workpad.body_sha256 is not None else None
        data = {
            "id": str(workpad.id),
            "workspace_id": str(workpad.workspace_id),
            "project_id": str(workpad.project_id),
            "issue_id": str(workpad.issue_id),
            "principal_id": str(workpad.principal_id),
            "body_markdown": workpad.body_markdown,
            "body_sha256": sha_hex,
            "revision": workpad.revision,
            "updated_at": workpad.updated_at.isoformat(),
        }
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=data,
            headers={"ETag": f'"{workpad.revision}"'},
        )


@router.put(
    "/issues/{issue_key}/workpad",
    summary="Update silent agent workpad slot with CAS revision protection",
    dependencies=[Depends(rate_limited(ISSUE_WORKPAD_RATE_LIMIT, key_func=_principal_rate_key))],
)
async def api_put_workpad(
    issue_key: str,
    body: PutIssueWorkpadRequest,
    caller: Caller,
    session: Session,
    if_match: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    """Update or create the workpad slot without emitting comments or notifications."""
    async with timing_floor(floor_ms=25.0):
        req_revision = _parse_if_match_revision(if_match, body.revision)
        workpad = await put_issue_workpad(
            session,
            caller,
            issue_key,
            body.body_markdown,
            if_match_revision=req_revision,
        )
        await session.commit()

        sha_hex = workpad.body_sha256.hex() if workpad.body_sha256 is not None else None
        data = {
            "id": str(workpad.id),
            "workspace_id": str(workpad.workspace_id),
            "project_id": str(workpad.project_id),
            "issue_id": str(workpad.issue_id),
            "principal_id": str(workpad.principal_id),
            "body_markdown": workpad.body_markdown,
            "body_sha256": sha_hex,
            "revision": workpad.revision,
            "updated_at": workpad.updated_at.isoformat(),
        }
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=data,
            headers={"ETag": f'"{workpad.revision}"'},
        )
