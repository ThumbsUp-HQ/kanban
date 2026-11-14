# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""REST API router for Project Blueprint administration (KB-P4-10, S11.4)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from kanban.api.deps import PrincipalContext, get_rls_session
from kanban.auth.mfa.policy import require_admin_aal2
from kanban.projects.blueprint_service import (
    ProjectBlueprint,
)
from kanban.projects.blueprint_service import (
    apply_blueprint as svc_apply_blueprint,
)
from kanban.projects.blueprint_service import (
    compute_plan as svc_compute_plan,
)
from kanban.projects.blueprint_service import (
    get_blueprint as svc_get_blueprint,
)

router = APIRouter(tags=["admin-project-blueprint"], dependencies=[Depends(require_admin_aal2)])

Caller = Annotated[PrincipalContext, Depends(require_admin_aal2)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


class BlueprintPlanRequest(BaseModel):
    """Payload for computing a declarative project blueprint diff."""

    model_config = ConfigDict(extra="forbid")

    blueprint: ProjectBlueprint


class BlueprintPlanResponse(BaseModel):
    """Response returned when a project blueprint diff plan is generated."""

    model_config = ConfigDict(extra="forbid")

    project: str
    plan_sha256: str
    changes: dict[str, Any]


class BlueprintApplyRequest(BaseModel):
    """Payload for applying a pre-calculated project blueprint plan."""

    model_config = ConfigDict(extra="forbid")

    blueprint: ProjectBlueprint
    plan_sha256: str


class BlueprintApplyResponse(BaseModel):
    """Response returned when a project blueprint plan is successfully applied."""

    model_config = ConfigDict(extra="forbid")

    project: str
    status: str = "applied"
    plan_sha256: str
    changes: dict[str, Any]


@router.get(
    "/admin/projects/{project_ref}/blueprint",
    response_model=ProjectBlueprint,
    summary="Get current declarative project blueprint",
)
async def get_project_blueprint(
    project_ref: str,
    caller: Caller,
    session: Session,
) -> ProjectBlueprint:
    """Read the complete declarative blueprint representation of a project."""
    return await svc_get_blueprint(session, caller, project_ref)


@router.post(
    "/admin/projects/blueprint:plan",
    response_model=BlueprintPlanResponse,
    summary="Compute project configuration diff plan",
)
async def plan_project_blueprint(
    body: BlueprintPlanRequest,
    caller: Caller,
    session: Session,
) -> BlueprintPlanResponse:
    """Compute declarative changes and canonical plan_sha256 without applying."""
    changes, plan_sha256 = await svc_compute_plan(session, caller, body.blueprint)
    return BlueprintPlanResponse(
        project=body.blueprint.identifier,
        plan_sha256=plan_sha256,
        changes=changes,
    )


@router.post(
    "/admin/projects/blueprint:apply",
    response_model=BlueprintApplyResponse,
    summary="Atomically apply project configuration plan",
)
async def apply_project_blueprint(
    body: BlueprintApplyRequest,
    caller: Caller,
    session: Session,
) -> BlueprintApplyResponse:
    """Atomically apply declarative blueprint changes in a single transaction."""
    res = await svc_apply_blueprint(session, caller, body.blueprint, body.plan_sha256)
    return BlueprintApplyResponse(
        project=res["project"],
        status=res["status"],
        plan_sha256=res["plan_sha256"],
        changes=res["changes"],
    )
