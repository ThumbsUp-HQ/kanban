# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""REST API router for custom field definitions (KB-P5-11, S13.1)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.timing import timing_floor
from kanban.api.v1.schemas.custom_fields import (
    CustomFieldCreateRequest,
    CustomFieldResponse,
    CustomFieldUpdateRequest,
)
from kanban.custom_fields.service import CustomFieldDefinitionService

router = APIRouter(tags=["custom-fields"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


@router.get(
    "/projects/{project}/custom-fields",
    response_model=list[CustomFieldResponse],
    summary="List custom field definitions for a project",
)
async def list_custom_fields(
    project: str,
    caller: Caller,
    session: Session,
) -> list[CustomFieldResponse]:
    """List custom field definitions visible to caller, redacting source for non-admins."""
    async with timing_floor(floor_ms=25.0):
        return await CustomFieldDefinitionService.list_definitions(session, caller, project)


@router.post(
    "/projects/{project}/custom-fields",
    status_code=status.HTTP_201_CREATED,
    response_model=CustomFieldResponse,
    summary="Create a custom field definition",
)
async def create_custom_field(
    project: str,
    body: CustomFieldCreateRequest,
    caller: Caller,
    session: Session,
    response: Response,
) -> CustomFieldResponse:
    """Create a new custom field definition (admin-only, requires AAL2 and CSRF)."""
    async with timing_floor(floor_ms=25.0):
        result = await CustomFieldDefinitionService.create_definition(
            session, caller, project, body
        )
        response.headers["Location"] = f"/api/v1/projects/{project}/custom-fields/{result.id}"
        return result


@router.patch(
    "/projects/{project}/custom-fields/{field_id}",
    response_model=CustomFieldResponse,
    summary="Update a custom field definition",
)
async def update_custom_field(
    project: str,
    field_id: str,
    body: CustomFieldUpdateRequest,
    caller: Caller,
    session: Session,
) -> CustomFieldResponse:
    """Update an existing custom field definition (admin-only, requires AAL2 and CSRF)."""
    async with timing_floor(floor_ms=25.0):
        return await CustomFieldDefinitionService.update_definition(
            session, caller, project, field_id, body
        )


@router.delete(
    "/projects/{project}/custom-fields/{field_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a custom field definition",
)
async def delete_custom_field(
    project: str,
    field_id: str,
    caller: Caller,
    session: Session,
) -> Response:
    """Delete an existing custom field definition (admin-only, requires AAL2 and CSRF)."""
    async with timing_floor(floor_ms=25.0):
        await CustomFieldDefinitionService.delete_definition(session, caller, project, field_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
