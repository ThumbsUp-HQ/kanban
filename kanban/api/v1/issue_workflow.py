# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Composite issue workflow transition endpoints (KB-P4-06)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse

from database.models.spine import ObjectRecord
from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.timing import timing_floor
from kanban.issues.lease_service import (
    DEFAULT_LEASE_TTL_SECONDS,
    heartbeat_issue_lease,
    release_issue_lease,
)
from kanban.issues.workflow_service import begin_work, complete_work, transition_ticket
from kanban.security.read_taint import TaintGuard, get_taint_guard
from kanban.services import issues as svc

router = APIRouter(tags=["issue-workflow"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


class BeginWorkRequest(BaseModel):
    """Payload for initiating work on an issue."""

    model_config = ConfigDict(extra="forbid")

    plan_markdown: Annotated[str, Field(min_length=1, max_length=65536)]
    ttl_seconds: Annotated[int | None, Field(ge=60, le=7200)] = None
    fencing_token: int | None = None


class TransitionTicketRequest(BaseModel):
    """Payload for transitioning issue state."""

    model_config = ConfigDict(extra="forbid")

    to_state: Annotated[str, Field(min_length=1, max_length=100)]
    comment_markdown: Annotated[str | None, Field(max_length=65536)] = None
    verification_proof: dict[str, Any] | None = None
    fencing_token: int | None = None
    lease_action: str | None = None


class CompleteWorkRequest(BaseModel):
    """Payload for completing work with verification proof."""

    model_config = ConfigDict(extra="forbid")

    summary_markdown: Annotated[str, Field(min_length=1, max_length=65536)]
    verification_proof: dict[str, Any]
    to_state: Annotated[str | None, Field(max_length=100)] = None
    fencing_token: int | None = None
    lease_action: str | None = None


class LeaseHeartbeatRequest(BaseModel):
    """Payload for heartbeat renewal of an active issue lease."""

    model_config = ConfigDict(extra="forbid")

    ttl_seconds: Annotated[int, Field(ge=60, le=7200)] = DEFAULT_LEASE_TTL_SECONDS
    fencing_token: int | None = None


@router.post(
    "/issues/{issue_key}/begin-work",
    summary="Atomically assign caller, attach active cycle, move to started state, and post plan",
)
async def api_begin_work(  # noqa: PLR0913, PLR0917
    issue_key: str,
    body: BeginWorkRequest,
    caller: Caller,
    session: Session,
    taint_guard: Annotated[TaintGuard, Depends(get_taint_guard)],
    if_match: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    """Initiate work on an issue in a single atomic transaction.

    Moves workflow state, assigns caller as assignee, and records execution plan.
    """
    async with timing_floor(floor_ms=25.0):
        pre_issue = await svc.get_issue_or_404(session, caller, issue_key)
        await taint_guard.check_write(pre_issue.project_id, tool_name="begin_work")
        issue, from_state, started_state, comment_ref, gate_hold, lease = await begin_work(
            session,
            caller,
            issue_key,
            body.plan_markdown,
            if_match=if_match,
            ttl_seconds=body.ttl_seconds or DEFAULT_LEASE_TTL_SECONDS,
            fencing_token=body.fencing_token,
        )

        if gate_hold is not None:
            await session.commit()
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content={
                    "status": "pending_agent_gate",
                    "execution_id": str(gate_hold.execution_id),
                    "active_agent": gate_hold.active_agent,
                    "from_state": gate_hold.from_state,
                    "to_state": gate_hold.to_state,
                    "lease_id": str(lease.id),
                    "fencing_token": lease.fencing_token,
                    "lease_expires_at": lease.expires_at.isoformat(),
                },
            )

        await session.flush()
        await session.refresh(issue)
        obj_rec = await session.get(ObjectRecord, issue.id, populate_existing=True)
        if obj_rec is not None:
            await session.refresh(obj_rec)

        serialized = await svc.serialize_issue(session, caller, issue)
        issue_dict = serialized.model_dump(mode="json")
        issue_dict["status"] = "started"
        issue_dict["workflow_status"] = "started"
        issue_dict["from_state"] = {
            "id": str(from_state.id),
            "name": from_state.name,
            "group": from_state.state_group,
        }
        issue_dict["to_state"] = {
            "id": str(started_state.id),
            "name": started_state.name,
            "group": started_state.state_group,
        }
        issue_dict["comment_ref"] = comment_ref
        issue_dict["comment_id"] = comment_ref
        issue_dict["lease_id"] = str(lease.id)
        issue_dict["fencing_token"] = lease.fencing_token
        issue_dict["lease_expires_at"] = lease.expires_at.isoformat()

        await session.commit()
        headers = {"ETag": serialized.etag} if serialized.etag else {}
        return JSONResponse(status_code=status.HTTP_200_OK, content=issue_dict, headers=headers)


@router.post(
    "/issues/{issue_key}/transition",
    summary="Transition issue to intermediate workflow state",
)
async def api_transition_ticket(  # noqa: PLR0913, PLR0917
    issue_key: str,
    body: TransitionTicketRequest,
    caller: Caller,
    session: Session,
    taint_guard: Annotated[TaintGuard, Depends(get_taint_guard)],
    if_match: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    """Transition an issue state under concurrency and gate hook evaluation."""
    async with timing_floor(floor_ms=25.0):
        pre_issue = await svc.get_issue_or_404(session, caller, issue_key)
        await taint_guard.check_write(pre_issue.project_id, tool_name="transition_ticket")
        issue, from_state, target_state, gate_hold = await transition_ticket(
            session,
            caller,
            issue_key,
            body.to_state,
            comment_markdown=body.comment_markdown,
            verification_proof=body.verification_proof,
            if_match=if_match,
            fencing_token=body.fencing_token,
            lease_action=body.lease_action,
        )

        if gate_hold is not None:
            await session.commit()
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content={
                    "status": "pending_agent_gate",
                    "execution_id": str(gate_hold.execution_id),
                    "active_agent": gate_hold.active_agent,
                    "from_state": gate_hold.from_state,
                    "to_state": gate_hold.to_state,
                },
            )

        await session.flush()
        await session.refresh(issue)
        obj_rec = await session.get(ObjectRecord, issue.id, populate_existing=True)
        if obj_rec is not None:
            await session.refresh(obj_rec)

        serialized = await svc.serialize_issue(session, caller, issue)
        issue_dict = serialized.model_dump(mode="json")
        issue_dict["status"] = "transitioned"
        issue_dict["workflow_status"] = "transitioned"
        issue_dict["target_state"] = target_state.name
        issue_dict["from_state"] = {
            "id": str(from_state.id),
            "name": from_state.name,
            "group": from_state.state_group,
        }
        issue_dict["to_state"] = {
            "id": str(target_state.id),
            "name": target_state.name,
            "group": target_state.state_group,
        }

        await session.commit()
        headers = {"ETag": serialized.etag} if serialized.etag else {}
        return JSONResponse(status_code=status.HTTP_200_OK, content=issue_dict, headers=headers)


@router.post(
    "/issues/{issue_key}/complete-work",
    summary="Verify blockers and QA gate, transition to completed, and log proof",
)
async def api_complete_work(  # noqa: PLR0913, PLR0917
    issue_key: str,
    body: CompleteWorkRequest,
    caller: Caller,
    session: Session,
    taint_guard: Annotated[TaintGuard, Depends(get_taint_guard)],
    if_match: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    """Verify preconditions, complete issue workflow, and record WORK_COMPLETED activity."""
    async with timing_floor(floor_ms=25.0):
        pre_issue = await svc.get_issue_or_404(session, caller, issue_key)
        await taint_guard.check_write(pre_issue.project_id, tool_name="complete_work")
        issue, from_state, target_state, proof, comment_ref, gate_hold = await complete_work(
            session,
            caller,
            issue_key,
            body.summary_markdown,
            body.verification_proof,
            to_state_ref=body.to_state,
            if_match=if_match,
            fencing_token=body.fencing_token,
            lease_action=body.lease_action,
        )

        if gate_hold is not None:
            await session.commit()
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content={
                    "status": "pending_agent_gate",
                    "execution_id": str(gate_hold.execution_id),
                    "active_agent": gate_hold.active_agent,
                    "from_state": gate_hold.from_state,
                    "to_state": gate_hold.to_state,
                },
            )

        await session.flush()
        await session.refresh(issue)
        obj_rec = await session.get(ObjectRecord, issue.id, populate_existing=True)
        if obj_rec is not None:
            await session.refresh(obj_rec)

        serialized = await svc.serialize_issue(session, caller, issue)
        issue_dict = serialized.model_dump(mode="json")
        issue_dict["status"] = "completed"
        issue_dict["workflow_status"] = "completed"
        issue_dict["target_state"] = target_state.name
        issue_dict["from_state"] = {
            "id": str(from_state.id),
            "name": from_state.name,
            "group": from_state.state_group,
        }
        issue_dict["to_state"] = {
            "id": str(target_state.id),
            "name": target_state.name,
            "group": target_state.state_group,
        }
        issue_dict["comment_ref"] = comment_ref
        issue_dict["comment_id"] = comment_ref
        issue_dict["proof"] = proof

        await session.commit()
        headers = {"ETag": serialized.etag} if serialized.etag else {}
        return JSONResponse(status_code=status.HTTP_200_OK, content=issue_dict, headers=headers)


@router.post(
    "/issues/{issue_key}/lease/heartbeat",
    summary="Extend lease expiration for active issue lease held by caller",
)
async def api_lease_heartbeat(
    issue_key: str,
    body: LeaseHeartbeatRequest,
    caller: Caller,
    session: Session,
    taint_guard: Annotated[TaintGuard, Depends(get_taint_guard)],
) -> JSONResponse:
    """Heartbeat and extend lease TTL on an actively leased issue."""
    async with timing_floor(floor_ms=25.0):
        pre_issue = await svc.get_issue_or_404(session, caller, issue_key)
        await taint_guard.check_write(pre_issue.project_id, tool_name="lease_heartbeat")
        lease = await heartbeat_issue_lease(
            session,
            caller,
            issue_key,
            ttl_seconds=body.ttl_seconds,
            fencing_token=body.fencing_token,
        )
        await session.commit()
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "lease_id": str(lease.id),
                "issue_id": str(lease.issue_id),
                "principal_id": str(lease.principal_id),
                "fencing_token": lease.fencing_token,
                "expires_at": lease.expires_at.isoformat(),
                "heartbeat_at": lease.heartbeat_at.isoformat(),
            },
        )


@router.delete(
    "/issues/{issue_key}/lease",
    summary="Release active issue lease held by caller or admin",
)
async def api_release_lease(
    issue_key: str,
    caller: Caller,
    session: Session,
    taint_guard: Annotated[TaintGuard, Depends(get_taint_guard)],
    fencing_token: int | None = None,
) -> JSONResponse:
    """Release active issue claim lease."""
    async with timing_floor(floor_ms=25.0):
        pre_issue = await svc.get_issue_or_404(session, caller, issue_key)
        await taint_guard.check_write(pre_issue.project_id, tool_name="release_lease")
        released = await release_issue_lease(
            session,
            caller,
            issue_key,
            fencing_token=fencing_token,
        )
        await session.commit()
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"released": released, "issue_key": issue_key},
        )
