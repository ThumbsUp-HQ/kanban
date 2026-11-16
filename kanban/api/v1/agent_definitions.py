"""REST API router for agent definitions registry (KB-P5-16, S14.2)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from kanban.agents.schemas import (
    AgentDefinitionCreate,
    AgentDefinitionPatch,
    AgentDefinitionResponse,
)
from kanban.agents.service import AgentDefinitionService
from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.timing import timing_floor
from kanban.auth.mfa.policy import require_admin_aal2

router = APIRouter(tags=["agent-definitions"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


@router.post(
    "/workspaces/{workspace}/agent-definitions",
    status_code=status.HTTP_201_CREATED,
    response_model=AgentDefinitionResponse,
    summary="Register a new agent definition",
)
async def create_agent_definition(
    workspace: str,
    body: AgentDefinitionCreate,
    caller: Caller,
    session: Session,
    response: Response,
) -> AgentDefinitionResponse:
    """Register a new agent definition and AGENT principal."""
    result = await AgentDefinitionService.create(session, caller, workspace, body)
    response.headers["Location"] = f"/api/v1/agent-definitions/{result.id}"
    return result


@router.get(
    "/workspaces/{workspace}/agent-definitions",
    response_model=list[AgentDefinitionResponse],
    summary="List agent definitions in workspace",
)
async def list_agent_definitions(
    workspace: str,
    caller: Caller,
    session: Session,
) -> list[AgentDefinitionResponse]:
    """List all agent definitions in the workspace visible to caller."""
    return await AgentDefinitionService.list_definitions(session, caller, workspace)


@router.get(
    "/agent-definitions/{agent}",
    response_model=AgentDefinitionResponse,
    summary="Get an agent definition",
)
async def get_agent_definition(
    agent: str,
    caller: Caller,
    session: Session,
) -> AgentDefinitionResponse:
    """Retrieve an agent definition by UUID or slug with timing-equalized 404."""
    async with timing_floor(floor_ms=25.0):
        return await AgentDefinitionService.get(session, caller, agent)


@router.patch(
    "/agent-definitions/{agent}",
    response_model=AgentDefinitionResponse,
    summary="Update an agent definition",
)
async def patch_agent_definition(
    agent: str,
    body: AgentDefinitionPatch,
    caller: Caller,
    session: Session,
) -> AgentDefinitionResponse:
    """Update mutable configuration of an existing agent definition."""
    async with timing_floor(floor_ms=25.0):
        return await AgentDefinitionService.patch(session, caller, agent, body)


@router.delete(
    "/agent-definitions/{agent}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an agent definition",
)
async def delete_agent_definition(
    agent: str,
    caller: Caller,
    session: Session,
) -> Response:
    """Delete an agent definition, returning 409 if referenced by transition hooks."""
    async with timing_floor(floor_ms=25.0):
        await AgentDefinitionService.delete(session, caller, agent)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


admin_router = APIRouter(
    prefix="/admin/agent-definitions",
    tags=["admin-agent-definitions"],
    dependencies=[Depends(require_admin_aal2)],
)
AdminCaller = Annotated[PrincipalContext, Depends(require_admin_aal2)]


@admin_router.get("", response_model=list[AgentDefinitionResponse])
async def admin_list_agent_definitions(
    caller: AdminCaller, session: Session
) -> list[AgentDefinitionResponse]:
    """List agent definitions in caller's workspace under admin authority."""
    return await AgentDefinitionService.list_definitions(session, caller, str(caller.workspace_id))


@admin_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=AgentDefinitionResponse,
)
async def admin_create_agent_definition(
    body: AgentDefinitionCreate,
    caller: AdminCaller,
    session: Session,
    response: Response,
) -> AgentDefinitionResponse:
    """Create a new agent definition in caller's workspace under admin authority."""
    result = await AgentDefinitionService.create(session, caller, str(caller.workspace_id), body)
    response.headers["Location"] = f"/api/v1/agent-definitions/{result.id}"
    return result


@admin_router.get("/{agent}", response_model=AgentDefinitionResponse)
async def admin_get_agent_definition(
    agent: str, caller: AdminCaller, session: Session
) -> AgentDefinitionResponse:
    """Retrieve an agent definition under admin authority."""
    return await AgentDefinitionService.get(session, caller, agent)


@admin_router.patch("/{agent}", response_model=AgentDefinitionResponse)
async def admin_patch_agent_definition(
    agent: str,
    body: AgentDefinitionPatch,
    caller: AdminCaller,
    session: Session,
) -> AgentDefinitionResponse:
    """Update an existing agent definition under admin authority."""
    return await AgentDefinitionService.patch(session, caller, agent, body)


@admin_router.delete("/{agent}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_agent_definition(
    agent: str, caller: AdminCaller, session: Session
) -> Response:
    """Delete an agent definition under admin authority."""
    await AgentDefinitionService.delete(session, caller, agent)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


router.include_router(admin_router)
