# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""REST API router for Workload Identity Federation policies (KB-AUTH-OIDC-EXCHANGE-01, KAN-74)."""

from __future__ import annotations

import uuid  # noqa: TC003
from datetime import datetime  # noqa: TC003
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.workload_identity import WorkloadIdentityPolicy
from kanban.api.deps import PrincipalContext, get_rls_session
from kanban.api.problems import not_found
from kanban.auth.mfa.policy import require_admin_aal2

router = APIRouter(
    prefix="/admin/workload-identities",
    tags=["admin-workload-identities"],
    dependencies=[Depends(require_admin_aal2)],
)

Caller = Annotated[PrincipalContext, Depends(require_admin_aal2)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


class WorkloadPolicyCreateRequest(BaseModel):
    """Payload for creating a workload identity policy."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    issuer: str = Field(min_length=1, max_length=500)
    client_id: str = Field(min_length=1, max_length=255)
    subject_pattern: str = Field(min_length=1, max_length=500)
    required_claims_json: dict[str, Any] = Field(default_factory=dict)
    surface: Literal["agent", "docs"]
    scopes: list[str] = Field(default_factory=list)
    allowed_project_ids: list[uuid.UUID] | None = None
    capability_mask: int = Field(default=255, ge=0, le=255)
    allowed_cidrs: list[str] | None = None
    max_ttl_seconds: int = Field(default=3600, ge=60, le=86400)
    is_enabled: bool = True


class WorkloadPolicyUpdateRequest(BaseModel):
    """Payload for updating an existing workload identity policy."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    issuer: str | None = Field(default=None, min_length=1, max_length=500)
    client_id: str | None = Field(default=None, min_length=1, max_length=255)
    subject_pattern: str | None = Field(default=None, min_length=1, max_length=500)
    required_claims_json: dict[str, Any] | None = None
    surface: Literal["agent", "docs"] | None = None
    scopes: list[str] | None = None
    allowed_project_ids: list[uuid.UUID] | None = None
    capability_mask: int | None = Field(default=None, ge=0, le=255)
    allowed_cidrs: list[str] | None = None
    max_ttl_seconds: int | None = Field(default=None, ge=60, le=86400)
    is_enabled: bool | None = None


class WorkloadPolicyResponse(BaseModel):
    """Public representation of a workload identity policy."""

    model_config = ConfigDict(extra="ignore")

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: str | None = None
    issuer: str
    client_id: str
    subject_pattern: str
    required_claims_json: dict[str, Any]
    surface: str
    scopes: list[str]
    allowed_project_ids: list[uuid.UUID] | None = None
    capability_mask: int
    allowed_cidrs: list[str] | None = None
    max_ttl_seconds: int
    is_enabled: bool
    created_by_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


def _to_response(policy: WorkloadIdentityPolicy) -> WorkloadPolicyResponse:
    return WorkloadPolicyResponse(
        id=policy.id,
        workspace_id=policy.workspace_id,
        name=policy.name,
        description=policy.description,
        issuer=policy.issuer,
        client_id=policy.client_id,
        subject_pattern=policy.subject_pattern,
        required_claims_json=policy.required_claims_json or {},
        surface=policy.surface,
        scopes=policy.scopes or [],
        allowed_project_ids=policy.allowed_project_ids,
        capability_mask=policy.capability_mask,
        allowed_cidrs=policy.allowed_cidrs,
        max_ttl_seconds=policy.max_ttl_seconds,
        is_enabled=policy.is_enabled,
        created_by_id=policy.created_by_id,
        created_at=policy.created_at,
        updated_at=policy.updated_at,
    )


@router.get(
    "",
    response_model=list[WorkloadPolicyResponse],
    summary="List workload identity federation policies",
)
async def list_workload_policies(
    caller: Caller,
    session: Session,
    workspace_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[WorkloadPolicyResponse]:
    """Retrieve workload federation policies visible to administrator."""
    ws = workspace_id or caller.workspace_id
    stmt = select(WorkloadIdentityPolicy)
    if ws is not None:
        stmt = stmt.where(WorkloadIdentityPolicy.workspace_id == ws)
    stmt = stmt.order_by(WorkloadIdentityPolicy.created_at.desc())

    result = await session.execute(stmt)
    policies = result.scalars().all()
    return [_to_response(p) for p in policies]


@router.post(
    "",
    response_model=WorkloadPolicyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create workload identity federation policy",
)
async def create_workload_policy(
    body: WorkloadPolicyCreateRequest,
    caller: Caller,
    session: Session,
) -> WorkloadPolicyResponse:
    """Create a new workload federation policy bound to caller's workspace."""
    policy = WorkloadIdentityPolicy(
        workspace_id=caller.workspace_id,
        name=body.name,
        description=body.description,
        issuer=body.issuer,
        client_id=body.client_id,
        subject_pattern=body.subject_pattern,
        required_claims_json=body.required_claims_json,
        surface=body.surface,
        scopes=body.scopes,
        allowed_project_ids=body.allowed_project_ids,
        capability_mask=body.capability_mask,
        allowed_cidrs=body.allowed_cidrs,
        max_ttl_seconds=body.max_ttl_seconds,
        is_enabled=body.is_enabled,
        created_by_id=caller.principal_id,
    )
    session.add(policy)
    await session.commit()
    await session.refresh(policy)
    return _to_response(policy)


@router.get(
    "/{policy_id}",
    response_model=WorkloadPolicyResponse,
    summary="Get workload identity federation policy",
)
async def get_workload_policy(
    policy_id: uuid.UUID,
    session: Session,
) -> WorkloadPolicyResponse:
    """Retrieve single workload policy by ID."""
    stmt = select(WorkloadIdentityPolicy).where(WorkloadIdentityPolicy.id == policy_id)
    policy = (await session.execute(stmt)).scalar_one_or_none()
    if policy is None:
        raise not_found()
    return _to_response(policy)


@router.patch(
    "/{policy_id}",
    response_model=WorkloadPolicyResponse,
    summary="Update workload identity federation policy",
)
async def update_workload_policy(
    policy_id: uuid.UUID,
    body: WorkloadPolicyUpdateRequest,
    session: Session,
) -> WorkloadPolicyResponse:
    """Update fields on an existing workload federation policy."""
    stmt = select(WorkloadIdentityPolicy).where(WorkloadIdentityPolicy.id == policy_id)
    policy = (await session.execute(stmt)).scalar_one_or_none()
    if policy is None:
        raise not_found()

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(policy, field, value)

    await session.commit()
    await session.refresh(policy)
    return _to_response(policy)


@router.delete(
    "/{policy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete workload identity federation policy",
)
async def delete_workload_policy(
    policy_id: uuid.UUID,
    session: Session,
) -> Response:
    """Delete a workload federation policy and all associated replay records."""
    stmt = select(WorkloadIdentityPolicy).where(WorkloadIdentityPolicy.id == policy_id)
    policy = (await session.execute(stmt)).scalar_one_or_none()
    if policy is None:
        raise not_found()

    await session.delete(policy)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
