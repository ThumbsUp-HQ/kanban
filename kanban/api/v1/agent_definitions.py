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
