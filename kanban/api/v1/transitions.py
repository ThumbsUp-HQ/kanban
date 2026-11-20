# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Issue workflow transition endpoint (KB-P5-17a, KB-P5-18, S14.1, S14.2)."""

from __future__ import annotations

import logging
import uuid  # noqa: TC003
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.problems import ProblemException
from kanban.workflows.engine import TransitionEngine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["transitions"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


class TransitionRequest(BaseModel):
    """Request payload for executing an issue workflow transition."""

    model_config = ConfigDict(extra="forbid")

    to_state: Annotated[
        str, Field(min_length=1, max_length=100, description="Target workflow state name or UUID")
    ]
    comment_markdown: Annotated[
        str | None, Field(max_length=65536, description="Optional transition comment")
    ] = None


class TransitionResponse(BaseModel):
    """Response payload for an approved workflow transition."""

    model_config = ConfigDict(extra="allow")

    execution_id: uuid.UUID
    status: str
    state: str
    sync_duration_ms: float | None = None


class PendingGateResponse(BaseModel):
    """Response payload for an asynchronous agent transition gate hold (HTTP 202)."""

    model_config = ConfigDict(extra="allow")

    status: str = "pending_agent_gate"
    execution_id: uuid.UUID
    active_agent: str
    hook_name: str
    harness_kind: str
    state: str


class CancelTransitionResponse(BaseModel):
    """Response payload for cancelling a pending workflow transition."""

    model_config = ConfigDict(extra="forbid")

    status: str = "cancelled"
    execution_id: uuid.UUID


async def _attach_issue_etag(
    session: AsyncSession, caller: PrincipalContext, issue_key: str, headers: dict[str, str]
) -> None:
    """Attempt to resolve and attach fresh ETag header for issue."""
    try:
        from kanban.services.issues import get_issue_or_404, serialize_issue  # noqa: PLC0415

        issue_row = await get_issue_or_404(session, caller, issue_key)
        serialized = await serialize_issue(session, caller, issue_row)
        if serialized.etag:
            headers["ETag"] = serialized.etag
    except Exception:  # noqa: BLE001
        logger.debug("Could not attach fresh ETag for %s", issue_key)


@router.post(
    "/issues/{issue_key}/transitions",
    response_model=TransitionResponse,
    responses={
        200: {"model": TransitionResponse},
        202: {"model": PendingGateResponse},
    },
    summary="Execute workflow state transition through validation pipeline",
)
async def post_issue_transition(
    issue_key: str,
    body: TransitionRequest,
    caller: Caller,
    session: Session,
    if_match: Annotated[str | None, Header()] = None,
) -> Response:
    """Execute synchronous Tier A validator/mutator transition pipeline and update issue state."""
    try:
        outcome = await TransitionEngine.request_transition(
            session=session,
            issue_key=issue_key,
            to_state=body.to_state,
            actor=caller,
            if_match=if_match,
            comment_markdown=body.comment_markdown,
        )
    except ProblemException as exc:
        if session.is_active:
            if exc.code == "TRANSITION_PENDING":
                await session.rollback()
            else:
                try:
                    await session.commit()
                except SQLAlchemyError:
                    await session.rollback()
        raise

    if outcome.execution_id is None or outcome.state is None:
        msg = "Transition outcome missing required execution_id or state"
        raise RuntimeError(msg)

    if outcome.status_code == status.HTTP_202_ACCEPTED or outcome.status == "pending_agent_gate":
        if session.is_active:
            await session.commit()
        content: dict[str, Any] = {
            "status": "pending_agent_gate",
            "execution_id": str(outcome.execution_id),
            "active_agent": outcome.field_updates.get("active_agent", "agent"),
            "hook_name": outcome.hook_name or outcome.field_updates.get("hook_name", "agent_gate"),
            "harness_kind": outcome.field_updates.get("harness_kind", "in_app_sdk"),
            "state": outcome.state,
        }
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=content)

    headers: dict[str, str] = {}
    await _attach_issue_etag(session, caller, issue_key, headers)

    if session.is_active:
        await session.commit()

    resp_data = TransitionResponse(
        execution_id=outcome.execution_id,
        status=outcome.status,
        state=outcome.state,
        sync_duration_ms=outcome.sync_duration_ms,
    )
    content_dict = resp_data.model_dump(mode="json")
    if "ETag" in headers:
        content_dict["etag"] = headers["ETag"]
    return JSONResponse(
        status_code=200,
        content=content_dict,
        headers=headers or None,
    )


@router.delete(
    "/transitions/{execution_id}",
    response_model=CancelTransitionResponse,
    summary="Cancel a pending asynchronous workflow transition",
)
async def cancel_transition(
    execution_id: uuid.UUID,
    caller: Caller,
    session: Session,
) -> CancelTransitionResponse:
    """Cancel a pending asynchronous workflow transition hold.

    Releases held locks on the target issue.
    """
    from kanban.workflows.async_gate import GateCoordinator  # noqa: PLC0415

    execution = await GateCoordinator.cancel(session, execution_id, caller)
    await session.commit()
    return CancelTransitionResponse(
        status="cancelled",
        execution_id=execution.id,
    )
