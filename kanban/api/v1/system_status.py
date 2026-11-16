# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""System status, standalone encrypted backup, and Docker Compose export endpoints (KB-P3-52)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002  # Runtime dependency for FastAPI

from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.problems import ProblemException
from kanban.auth.mfa.policy import require_admin_aal2
from kanban.services.activity import ActivityEventType, record_activity
from kanban.standalone.export_service import (
    encrypt_backup,
    generate_compose_export,
    get_standalone_status,
    run_pg_dump,
)

logger = logging.getLogger(__name__)

MIN_PASSPHRASE_LENGTH = 16


class SystemStatusResponse(BaseModel):
    """Runtime deployment mode, persistence indicator, and infrastructure topology."""

    model_config = ConfigDict(extra="forbid")

    deployment_mode: str
    persistent_volume: bool
    data_mount_point: str | None = None
    data_mount_fstype: str | None = None
    tier_b_sandbox_available: bool
    air_gap_mode: bool
    local_llm_endpoint_host: str | None = None
    is_server_admin: bool
    allow_unlimited_mcp_keys: bool = True


class StandaloneBackupRequest(BaseModel):
    """Request payload for triggering an encrypted database backup."""

    model_config = ConfigDict(extra="forbid")

    passphrase: str | None = Field(default=None, max_length=256)
    use_master_kek: bool = False


class ComposeExportResponse(BaseModel):
    """Production Docker Compose specification, environment template, and promotion guide."""

    model_config = ConfigDict(extra="forbid")

    filename: str
    compose_yaml: str
    env_template: str
    migration_steps_markdown: str


async def require_server_admin(
    caller: Annotated[PrincipalContext, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> PrincipalContext:
    """Verify caller possesses SERVER_ADMIN role.

    Raises 403 INSUFFICIENT_CAPABILITY if caller is not a server administrator.
    """
    stmt = text("SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])")
    is_server_admin = bool((await session.execute(stmt)).scalar_one())
    if not is_server_admin:
        raise ProblemException(
            code="INSUFFICIENT_CAPABILITY",
            status=403,
            title="Insufficient Capability",
            detail="Operation requires SERVER_ADMIN role.",
            type_uri="urn:kanban:problem:insufficient-capability",
        )
    return caller


system_router = APIRouter(prefix="/system", tags=["system"])
admin_standalone_router = APIRouter(
    prefix="/admin/standalone",
    tags=["admin-standalone"],
    dependencies=[Depends(require_admin_aal2)],
)


@system_router.get(
    "/status",
    response_model=SystemStatusResponse,
    summary="Get system deployment and persistence status",
)
async def get_system_status_endpoint(
    caller: Annotated[PrincipalContext, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
    request: Request,
) -> SystemStatusResponse:
    """Retrieve system status with anti-enumeration redaction for non-administrators."""
    del caller  # Context verified
    stmt = text("SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])")
    is_server_admin = bool((await session.execute(stmt)).scalar_one())

    settings = getattr(request.app.state, "settings", None)
    status_data = get_standalone_status(settings=settings)

    mount_point = status_data["data_mount_point"] if is_server_admin else None
    mount_fstype = status_data["data_mount_fstype"] if is_server_admin else None
    local_llm_host = status_data["local_llm_endpoint_host"] if is_server_admin else None
    disable_unlimited = (
        bool(getattr(settings, "disable_unlimited_mcp_keys", False)) if settings else False
    )

    return SystemStatusResponse(
        deployment_mode=status_data["deployment_mode"],
        persistent_volume=status_data["persistent_volume"],
        data_mount_point=mount_point,
        data_mount_fstype=mount_fstype,
        tier_b_sandbox_available=status_data["tier_b_sandbox_available"],
        air_gap_mode=status_data["air_gap_mode"],
        local_llm_endpoint_host=local_llm_host,
        is_server_admin=is_server_admin,
        allow_unlimited_mcp_keys=not disable_unlimited,
    )


@admin_standalone_router.get(
    "/status",
    response_model=SystemStatusResponse,
    summary="Get standalone deployment and persistence status for administrators",
)
async def get_admin_standalone_status_endpoint(
    caller: Annotated[PrincipalContext, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
    request: Request,
) -> SystemStatusResponse:
    """Retrieve standalone deployment status for administrators with full topology."""
    del caller
    stmt = text("SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])")
    is_server_admin = bool((await session.execute(stmt)).scalar_one())

    settings = getattr(request.app.state, "settings", None)
    status_data = get_standalone_status(settings=settings)

    mount_point = status_data["data_mount_point"] if is_server_admin else None
    mount_fstype = status_data["data_mount_fstype"] if is_server_admin else None
    local_llm_host = status_data["local_llm_endpoint_host"] if is_server_admin else None
    disable_unlimited = (
        bool(getattr(settings, "disable_unlimited_mcp_keys", False)) if settings else False
    )

    return SystemStatusResponse(
        deployment_mode=status_data["deployment_mode"],
        persistent_volume=status_data["persistent_volume"],
        data_mount_point=mount_point,
        data_mount_fstype=mount_fstype,
        tier_b_sandbox_available=status_data["tier_b_sandbox_available"],
        air_gap_mode=status_data["air_gap_mode"],
        local_llm_endpoint_host=local_llm_host,
        is_server_admin=is_server_admin,
        allow_unlimited_mcp_keys=not disable_unlimited,
    )


@admin_standalone_router.post(
    "/backup",
    summary="Generate and download encrypted database backup",
    dependencies=[Depends(require_server_admin)],
    responses={
        200: {"content": {"application/octet-stream": {}}},
        403: {"description": "AAL2 or SERVER_ADMIN required"},
        409: {"description": "Not in standalone deployment mode"},
        422: {"description": "Invalid passphrase (< 16 characters)"},
    },
)
async def create_standalone_backup(
    body: StandaloneBackupRequest,
    caller: Annotated[PrincipalContext, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
    request: Request,
) -> Response:
    """Execute pg_dump, encrypt with AES-256-GCM, record audit event, and stream .kbkp file."""
    settings = getattr(request.app.state, "settings", None)
    status_data = get_standalone_status(settings=settings)
    if status_data["deployment_mode"] != "standalone_embedded_pg":
        raise ProblemException(
            code="NOT_STANDALONE_MODE",
            status=409,
            title="Not Standalone Mode",
            detail=(
                "Encrypted database backup is only available in standalone "
                "single-container deployment mode."
            ),
            type_uri="urn:kanban:problem:not-standalone-mode",
        )

    if body.use_master_kek:
        key_material = getattr(request.app.state, "key_material", None)
        master_kek = getattr(key_material, "master_kek", None) if key_material else None
        if not master_kek:
            raise ProblemException(
                code="MASTER_KEK_UNAVAILABLE",
                status=500,
                title="Key Material Unavailable",
                detail="Server MASTER_KEK is not configured for backup encryption.",
            )
        raw_passphrase = None
    else:
        if not body.passphrase or len(body.passphrase) < MIN_PASSPHRASE_LENGTH:
            raise ProblemException(
                code="INVALID_BACKUP_PASSPHRASE",
                status=422,
                title="Invalid Backup Passphrase",
                detail="Passphrase must be at least 16 characters in length.",
                type_uri="urn:kanban:problem:invalid-backup-passphrase",
            )
        raw_passphrase = body.passphrase
        master_kek = None

    try:
        dump_bytes = await run_pg_dump(settings=settings)
    except Exception as exc:
        logger.exception("Database backup dump failed")
        raise ProblemException(
            code="BACKUP_DUMP_FAILED",
            status=500,
            title="Backup Dump Failed",
            detail=f"Database dump execution failed: {exc}",
        ) from exc

    encrypted_data = encrypt_backup(
        dump_bytes,
        passphrase=raw_passphrase,
        master_kek=master_kek,
    )

    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.STANDALONE_BACKUP_EXPORTED,
        payload={
            "kdf_mode": "master_kek" if body.use_master_kek else "passphrase",
            "size_bytes": len(encrypted_data),
        },
    )

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    filename = f"kanban-backup-{timestamp}.kbkp"

    return Response(
        content=encrypted_data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "X-Content-Type-Options": "nosniff",
        },
    )


@admin_standalone_router.get(
    "/compose-export",
    response_model=ComposeExportResponse,
    summary="Export production Docker Compose and migration runbook",
)
async def get_compose_export_endpoint() -> ComposeExportResponse:
    """Generate secret-free production docker-compose.yml and promotion checklist."""
    payload = generate_compose_export()
    return ComposeExportResponse(
        filename=payload.filename,
        compose_yaml=payload.compose_yaml,
        env_template=payload.env_template,
        migration_steps_markdown=payload.migration_steps_markdown,
    )
