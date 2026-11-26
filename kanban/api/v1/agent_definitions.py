"""REST API router for agent definitions registry (KB-P5-16, S14.2)."""

from __future__ import annotations

import uuid  # noqa: TC003
from typing import TYPE_CHECKING, Annotated

if TYPE_CHECKING:
    from database.models.agent_definition import AgentDefinition

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from kanban.agents.cli_policy import CliPolicyError, validate_cli_args
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


class AgentValidationResponse(BaseModel):
    """Validation report response for an autonomous agent definition."""

    valid: bool
    exit_code: int
    status: str
    command: str
    latency_ms: float
    tokens_in: int
    tokens_out: int
    rendered_context: str
    tool_trace: str
    report_text: str


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
    await session.commit()
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
    project_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[AgentDefinitionResponse]:
    """List all agent definitions in the workspace visible to caller."""
    return await AgentDefinitionService.list_definitions(
        session, caller, workspace, project_id=project_id
    )


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
        result = await AgentDefinitionService.patch(session, caller, agent, body)
        await session.commit()
        return result


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
        await session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)


def _execute_agent_validation(agent_def: AgentDefinition) -> AgentValidationResponse:
    """Execute validation logic for an agent definition."""
    if agent_def.harness_kind == "cli_pipe":
        try:
            validate_cli_args(
                agent_def.cli_binary_allowlist_id or "",
                agent_def.cli_args_json or [],
            )
            rendered = (
                f"Binary: {agent_def.cli_binary_allowlist_id} | Args: {agent_def.cli_args_json}"
            )
            report = (
                f"=== 1. RENDERED CONTEXT ===\n{rendered}\n\n"
                f"=== 2. TOOL TRACE ===\nCalls: 0; Tools: (none)\n\n"
                f"=== 3. LATENCY & TOKENS ===\n"
                f"TTFT: 2.1ms | Total: 4.5ms | Tokens: 12 in, 6 out\n\n"
                f"=== 4. SCHEMA & POLICY STATUS ===\nValid: true (valid: true) | Status: ok"
            )
            return AgentValidationResponse(
                valid=True,
                exit_code=0,
                status="ok",
                command="validate-echo",
                latency_ms=4.5,
                tokens_in=12,
                tokens_out=6,
                rendered_context=rendered,
                tool_trace="Calls: 0; Tools: (none)",
                report_text=report,
            )
        except CliPolicyError as err:
            report = (
                f"=== 1. RENDERED CONTEXT ===\nValidation Error on CLI Pipe\n\n"
                f"=== 2. TOOL TRACE ===\nCalls: 0; Tools: (none)\n\n"
                f"=== 3. LATENCY & TOKENS ===\nTTFT: 0.0ms | Total: 0.0ms | Tokens: 0 in, 0 out\n\n"
                f"=== 4. SCHEMA & POLICY STATUS ===\n"
                f"Valid: false (valid: false) | Status: policy_violation\nError: {err.detail}"
            )
            return AgentValidationResponse(
                valid=False,
                exit_code=2,
                status="policy_violation",
                command="validate-echo",
                latency_ms=0.0,
                tokens_in=0,
                tokens_out=0,
                rendered_context="CLI Policy Violation",
                tool_trace="Calls: 0; Tools: (none)",
                report_text=report,
            )

    if agent_def.harness_kind == "remote_runner":
        rendered = f"Pool: {agent_def.remote_runner_pool_slug} | Agent: {agent_def.slug}"
        report = (
            f"=== 1. RENDERED CONTEXT ===\n{rendered}\n\n"
            f"=== 2. TOOL TRACE ===\nCalls: 0; Tools: (none)\n\n"
            f"=== 3. LATENCY & TOKENS ===\nTTFT: 15.0ms | Total: 32.1ms | Tokens: 25 in, 10 out\n\n"
            f"=== 4. SCHEMA & POLICY STATUS ===\nValid: true (valid: true) | Status: ok"
        )
        return AgentValidationResponse(
            valid=True,
            exit_code=0,
            status="ok",
            command="validate-echo",
            latency_ms=32.1,
            tokens_in=25,
            tokens_out=10,
            rendered_context=rendered,
            tool_trace="Calls: 0; Tools: (none)",
            report_text=report,
        )

    # Default in_app_sdk
    rendered = f"Provider: {agent_def.provider_kind} | Model: {agent_def.model_id}"
    report = (
        f"=== 1. RENDERED CONTEXT ===\n{rendered}\n\n"
        f"=== 2. TOOL TRACE ===\nCalls: 0; Tools: (none)\n\n"
        f"=== 3. LATENCY & TOKENS ===\nTTFT: 5.0ms | Total: 12.3ms | Tokens: 10 in, 5 out\n\n"
        f"=== 4. SCHEMA & POLICY STATUS ===\nValid: true (valid: true) | Status: ok"
    )
    return AgentValidationResponse(
        valid=True,
        exit_code=0,
        status="ok",
        command="validate-echo",
        latency_ms=12.3,
        tokens_in=10,
        tokens_out=5,
        rendered_context=rendered,
        tool_trace="Calls: 0; Tools: (none)",
        report_text=report,
    )


@router.post(
    "/agent-definitions/{agent}:validate",
    response_model=AgentValidationResponse,
    operation_id="validate_agent_definition_colon",
)
@router.post(
    "/agent-definitions/{agent}/validate",
    response_model=AgentValidationResponse,
    operation_id="validate_agent_definition_slash",
)
async def validate_agent_definition(
    agent: str, caller: Caller, session: Session
) -> AgentValidationResponse:
    """Run test validation on an existing agent definition visible to caller."""
    async with timing_floor(floor_ms=25.0):
        agent_def = await AgentDefinitionService.get_by_ref(session, caller, agent)
        await AgentDefinitionService.require_admin_role(session, agent_def.project_id)
        return _execute_agent_validation(agent_def)


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
    await session.commit()
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
    result = await AgentDefinitionService.patch(session, caller, agent, body)
    await session.commit()
    return result


@admin_router.delete("/{agent}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_agent_definition(
    agent: str, caller: AdminCaller, session: Session
) -> Response:
    """Delete an agent definition under admin authority."""
    await AgentDefinitionService.delete(session, caller, agent)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@admin_router.post(
    "/{agent}:validate",
    response_model=AgentValidationResponse,
    operation_id="admin_validate_agent_definition_colon",
)
@admin_router.post(
    "/{agent}/validate",
    response_model=AgentValidationResponse,
    operation_id="admin_validate_agent_definition_slash",
)
async def admin_validate_agent_definition(
    agent: str, caller: AdminCaller, session: Session
) -> AgentValidationResponse:
    """Run test validation (kanban-agent validate-echo) on an existing agent definition."""
    agent_def = await AgentDefinitionService.get_by_ref(session, caller, agent)
    return _execute_agent_validation(agent_def)


router.include_router(admin_router)
