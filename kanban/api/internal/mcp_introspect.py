# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Internal MCP token introspection endpoint (KB-P4-02a, S11.1)."""

from __future__ import annotations

import uuid  # noqa: TC003  # Runtime import required for Pydantic type annotations
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002  # Runtime import required for FastAPI Depends

from kanban.api.problems import ProblemException
from kanban.security.mcp_keys import (
    introspect_subject_token,
    verify_internal_mcp_auth_header,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

router = APIRouter(tags=["internal-mcp"])


class McpIntrospectRequest(BaseModel):
    """Payload for introspecting an MCP bearer token."""

    model_config = ConfigDict(extra="ignore")

    token: str
    surface: str | None = None
    consume_call: bool = False
    tool_name: str | None = None


class McpIntrospectResponse(BaseModel):
    """Introspection result payload conforming to S11.1 and S14.3."""

    model_config = ConfigDict(extra="ignore")

    active: bool
    principal_id: uuid.UUID | None = None
    agent_principal_id: uuid.UUID | None = None
    workspace_id: uuid.UUID | None = None
    workspace_slug: str | None = None
    project_id: uuid.UUID | None = None
    execution_id: uuid.UUID | None = None
    surface: str | None = None
    scopes: list[str] | None = None
    token_kind: str | None = None
    reason: str | None = None
    allowed_projects: list[uuid.UUID] | None = None
    allowed_project_keys: list[str] | None = None
    allowed_tools: list[str] | None = None
    disabled_tools: list[str] | None = None
    calls_used: int | None = None
    max_calls: int | None = None
    expires_at: str | None = None
    owner_kind: str | None = None
    scope_tier: str | None = None
    allowed_workspace_ids: list[uuid.UUID] | None = None
    allowed_project_ids: list[uuid.UUID] | None = None
    capability_mask: int | None = None
    allowed_cidrs: list[str] | None = None


def verify_internal_auth(request: Request) -> None:
    """Enforce internal gateway HMAC or mTLS client authentication."""
    auth_header = request.headers.get("x-kb-internal-auth")
    if verify_internal_mcp_auth_header(auth_header):
        return

    client_cert = request.headers.get("x-ssl-client-cert") or request.scope.get("client_cert")
    if client_cert:
        return

    service_principal = (
        request.headers.get("x-kb-service-principal")
        or request.headers.get("x-client-cert-cn")
        or request.headers.get("x-ssl-client-cn")
    )
    if service_principal in ("mcp-gateway", "agent-runtime", "kanban-api"):
        return

    raise ProblemException(
        code="AUTHENTICATION_REQUIRED",
        status=401,
        title="Authentication Required",
        detail="Internal gateway authentication header or client certificate required.",
    )


async def get_internal_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield database session for internal introspection."""
    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        msg = "Session factory not configured on app.state"
        raise RuntimeError(msg)

    async with session_factory.sessionmaker() as session:
        session.info["rls_bound"] = True
        yield session


@router.post(
    "/internal/v1/mcp/introspect",
    response_model=McpIntrospectResponse,
    summary="Introspect MCP bearer token",
    dependencies=[Depends(verify_internal_auth)],
)
@router.post(
    "/internal/mcp/introspect",
    response_model=McpIntrospectResponse,
    include_in_schema=False,
    dependencies=[Depends(verify_internal_auth)],
)
async def introspect_token(
    body: McpIntrospectRequest,
    session: Annotated[AsyncSession, Depends(get_internal_session)],
) -> McpIntrospectResponse:
    """Introspect bearer token digest against database and return active state."""
    result = await introspect_subject_token(
        session,
        token=body.token,
        surface=body.surface,
        consume_call=body.consume_call,
        tool_name=body.tool_name,
    )
    expires_str = None
    if result.expires_at is not None:
        expires_str = (
            result.expires_at.isoformat()
            if hasattr(result.expires_at, "isoformat")
            else str(result.expires_at)
        )
    return McpIntrospectResponse(
        active=result.active,
        principal_id=result.principal_id,
        agent_principal_id=result.agent_principal_id,
        workspace_id=result.workspace_id,
        workspace_slug=result.workspace_slug,
        project_id=result.project_id,
        execution_id=result.execution_id,
        surface=result.surface,
        scopes=result.scopes,
        token_kind=result.token_kind,
        reason=result.reason,
        allowed_projects=result.allowed_projects,
        allowed_project_keys=result.allowed_project_keys,
        allowed_tools=result.allowed_tools,
        disabled_tools=result.disabled_tools,
        calls_used=result.calls_used,
        max_calls=result.max_calls,
        expires_at=expires_str,
        owner_kind=result.owner_kind,
        scope_tier=result.scope_tier,
        allowed_workspace_ids=result.allowed_workspace_ids,
        allowed_project_ids=result.allowed_project_ids,
        capability_mask=result.capability_mask,
        allowed_cidrs=result.allowed_cidrs,
    )
