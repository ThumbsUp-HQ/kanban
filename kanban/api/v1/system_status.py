# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""System status, standalone encrypted backup, and Docker Compose export endpoints (KB-P3-52)."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002  # Runtime dependency for FastAPI

from database.models.workspace_settings import WorkspaceSettings
from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.problems import ProblemException
from kanban.auth.mfa.policy import require_admin_aal2
from kanban.jobs.scheduled_backup import (
    get_backup_schedule,
    list_backups,
    resolve_backup_dir,
    run_scheduled_backup_pass,
    update_backup_schedule,
)
from kanban.ops.backup_crypto import KeySource, PassphraseKeySource, RawKeySource
from kanban.ops.backup_service import restore_backup, verify_backup
from kanban.ops.build_info import get_build_info
from kanban.services.activity import ActivityEventType, record_activity
from kanban.standalone.export_service import (
    decrypt_backup,
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
    supported_custom_field_tiers: list[str] = Field(
        default_factory=lambda: ["scalar", "formula", "wasm", "nsjail"]
    )
    sandbox_unavailable_reason: str | None = None
    git_commit: str | None = None
    build_timestamp: str | None = None
    openapi_version: str | None = "2.0.0"
    openapi_bundle_hash: str | None = None
    frontend_bundle_hash: str | None = None


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
    single_container_compose_yaml: str | None = None


class BackupScheduleResponse(BaseModel):
    """Automated backup schedule and snapshot retention settings."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    interval_hours: int
    retention_count: int
    last_run_at: str | None = None
    next_run_at: str | None = None


class BackupScheduleUpdateRequest(BaseModel):
    """Update payload for automated backup schedule."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    interval_hours: int = Field(default=24, ge=1)
    retention_count: int = Field(default=7, ge=1)


class BackupFileItem(BaseModel):
    """Descriptor of an existing backup snapshot file."""

    model_config = ConfigDict(extra="forbid")

    filename: str
    size_bytes: int
    created_at: str


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


async def _assemble_system_status_response(
    caller: PrincipalContext,
    session: AsyncSession,
    request: Request,
) -> SystemStatusResponse:
    """Build standardized SystemStatusResponse with topological metadata and build info."""
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

    ws_air_gap = False
    if caller.workspace_id != uuid.UUID(int=0):
        try:
            ws_stmt = select(WorkspaceSettings.air_gap_mode).where(
                WorkspaceSettings.workspace_id == caller.workspace_id
            )
            ws_res = (await session.execute(ws_stmt)).scalar_one_or_none()
            ws_air_gap = bool(ws_res)
        except (SQLAlchemyError, ValueError, KeyError):
            ws_air_gap = False
    effective_air_gap = ws_air_gap or bool(status_data["air_gap_mode"])

    tier_b_avail = bool(status_data["tier_b_sandbox_available"])
    supported_tiers = (
        ["scalar", "formula", "wasm", "nsjail"] if tier_b_avail else ["scalar", "formula", "wasm"]
    )
    sandbox_reason = (
        None
        if tier_b_avail
        else (
            "Isolated nsjail sandbox execution is unavailable in standalone mode. "
            "Multi-container compose deployment is required."
        )
    )

    openapi_doc = None
    if hasattr(request, "app") and hasattr(request.app, "openapi"):
        openapi_doc = request.app.openapi()
    b_info = get_build_info(openapi_doc)

    return SystemStatusResponse(
        deployment_mode=status_data["deployment_mode"],
        persistent_volume=status_data["persistent_volume"],
        data_mount_point=mount_point,
        data_mount_fstype=mount_fstype,
        tier_b_sandbox_available=tier_b_avail,
        air_gap_mode=effective_air_gap,
        local_llm_endpoint_host=local_llm_host,
        is_server_admin=is_server_admin,
        allow_unlimited_mcp_keys=not disable_unlimited,
        supported_custom_field_tiers=supported_tiers,
        sandbox_unavailable_reason=sandbox_reason,
        git_commit=b_info.git_commit,
        build_timestamp=b_info.build_timestamp,
        openapi_version=b_info.openapi_version,
        openapi_bundle_hash=b_info.openapi_bundle_hash,
        frontend_bundle_hash=b_info.frontend_bundle_hash,
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
    return await _assemble_system_status_response(caller, session, request)


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
    return await _assemble_system_status_response(caller, session, request)


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
        single_container_compose_yaml=payload.single_container_compose_yaml,
    )


@admin_standalone_router.get(
    "/backup-schedule",
    response_model=BackupScheduleResponse,
    summary="Get automated backup schedule configuration",
    dependencies=[Depends(require_server_admin)],
)
async def get_backup_schedule_endpoint() -> BackupScheduleResponse:
    """Retrieve automated backup schedule and snapshot retention settings."""
    data = get_backup_schedule()
    return BackupScheduleResponse(**data)


@admin_standalone_router.put(
    "/backup-schedule",
    response_model=BackupScheduleResponse,
    summary="Update automated backup schedule configuration",
    dependencies=[Depends(require_server_admin)],
)
async def update_backup_schedule_endpoint(
    body: BackupScheduleUpdateRequest,
) -> BackupScheduleResponse:
    """Update automated backup interval and snapshot retention limit."""
    try:
        data = update_backup_schedule(
            enabled=body.enabled,
            interval_hours=body.interval_hours,
            retention_count=body.retention_count,
        )
    except ValueError as exc:
        raise ProblemException(
            code="INVALID_BACKUP_SCHEDULE",
            status=422,
            title="Invalid Backup Schedule",
            detail=str(exc),
        ) from exc
    except OSError as exc:
        logger.exception("Failed to write backup schedule configuration")
        raise ProblemException(
            code="BACKUP_SCHEDULE_SAVE_FAILED",
            status=500,
            title="Backup Schedule Save Failed",
            detail=f"Failed to persist backup schedule to disk: {exc}",
        ) from exc
    return BackupScheduleResponse(**data)


@admin_standalone_router.get(
    "/backups",
    response_model=list[BackupFileItem],
    summary="List existing backup snapshot files",
    dependencies=[Depends(require_server_admin)],
)
async def list_backups_endpoint() -> list[BackupFileItem]:
    """Enumerate backup snapshots on disk sorted by creation time descending."""
    return [BackupFileItem(**item) for item in list_backups()]


@admin_standalone_router.post(
    "/backups/run-now",
    summary="Trigger immediate backup snapshot",
    dependencies=[Depends(require_server_admin)],
)
async def run_backup_now_endpoint(
    request: Request,
) -> dict[str, Any]:
    """Execute an automated backup pass immediately on demand."""
    settings = getattr(request.app.state, "settings", None)
    db_url = settings.database_url if settings else None
    try:
        summary = run_scheduled_backup_pass(db_url=db_url)
    except Exception as exc:
        logger.exception("Immediate backup snapshot execution failed")
        raise ProblemException(
            code="BACKUP_RUN_FAILED",
            status=500,
            title="Backup Run Failed",
            detail=f"Failed to execute immediate backup snapshot: {exc}",
        ) from exc

    if summary is None:
        raise ProblemException(
            code="BACKUP_RUN_FAILED",
            status=500,
            title="Backup Run Failed",
            detail="Failed to execute immediate backup snapshot.",
        )
    return {
        "status": "success",
        "filename": summary.archive_path.name,
        "size_bytes": summary.size_bytes,
        "manifest": summary.manifest.to_dict(),
        "duration_seconds": summary.duration_seconds,
    }


@admin_standalone_router.get(
    "/backups/{filename}",
    summary="Download backup snapshot file",
    dependencies=[Depends(require_server_admin)],
)
async def download_backup_file_endpoint(
    filename: str,
) -> Response:
    """Safely stream requested backup file with traversal protections."""
    if not re.match(r"^[a-zA-Z0-9._-]+$", filename) or ".." in filename:
        raise ProblemException(
            code="INVALID_FILENAME",
            status=400,
            title="Invalid Filename",
            detail="Filename contains forbidden characters.",
        )
    backup_dir = resolve_backup_dir()
    target_file = backup_dir / filename
    if not target_file.is_file():
        raise ProblemException(
            code="BACKUP_NOT_FOUND",
            status=404,
            title="Backup Not Found",
            detail=f"Backup file '{filename}' was not found.",
        )
    return Response(
        content=target_file.read_bytes(),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "X-Content-Type-Options": "nosniff",
        },
    )


@admin_standalone_router.post(
    "/backup/verify",
    summary="Verify an encrypted backup archive",
    dependencies=[Depends(require_server_admin)],
)
async def verify_backup_endpoint(  # noqa: C901, PLR0912, PLR0915
    request: Request,
) -> dict[str, Any]:
    """Verify cryptographic integrity and manifest of a backup archive."""
    content_type = request.headers.get("content-type", "")
    passphrase: str | None = None
    use_master_kek = False
    file_bytes: bytes | None = None
    filename: str | None = None

    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        uploaded_file = form.get("file")
        if uploaded_file and hasattr(uploaded_file, "read"):
            file_bytes = await uploaded_file.read()
            filename = getattr(uploaded_file, "filename", "uploaded_backup.kbbak")
        passphrase_val = form.get("passphrase")
        if isinstance(passphrase_val, str) and passphrase_val:
            passphrase = passphrase_val
        use_kek_val = form.get("use_master_kek")
        if isinstance(use_kek_val, str) and use_kek_val.lower() in ("true", "1"):
            use_master_kek = True
    else:
        body = await request.json()
        filename = body.get("filename")
        passphrase = body.get("passphrase")
        use_master_kek = bool(body.get("use_master_kek", False))

    if not file_bytes and filename:
        if not re.match(r"^[a-zA-Z0-9._-]+$", filename) or ".." in filename:
            raise ProblemException(
                code="INVALID_FILENAME",
                status=400,
                title="Invalid Filename",
                detail="Filename contains forbidden characters.",
            )
        backup_dir = resolve_backup_dir()
        target = backup_dir / filename
        if not target.is_file():
            raise ProblemException(
                code="BACKUP_NOT_FOUND",
                status=404,
                title="Backup Not Found",
                detail=f"Backup file '{filename}' was not found.",
            )
        file_bytes = target.read_bytes()

    if not file_bytes:
        raise ProblemException(
            code="MISSING_BACKUP_PAYLOAD",
            status=422,
            title="Missing Backup Payload",
            detail="Either an uploaded backup file or a valid server filename is required.",
        )

    # Determine key source
    key_source: KeySource | None = None
    if use_master_kek:
        key_material = getattr(request.app.state, "key_material", None)
        master_kek = getattr(key_material, "master_kek", None) if key_material else None
        if master_kek:
            key_source = RawKeySource(master_kek)
    elif passphrase:
        key_source = PassphraseKeySource(passphrase)

    if key_source is None:
        key_material = getattr(request.app.state, "key_material", None)
        master_kek = getattr(key_material, "master_kek", None) if key_material else None
        key_source = RawKeySource(master_kek) if master_kek else RawKeySource(b"\x00" * 32)

    with tempfile.NamedTemporaryFile(prefix="kb_verify_target_", delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = Path(tmp.name)

    try:
        if file_bytes.startswith(b"KBKP"):
            kek_bytes = (
                getattr(key_source, "master_kek", None)
                if hasattr(key_source, "master_kek")
                else None
            )
            decrypted = decrypt_backup(file_bytes, passphrase=passphrase, master_kek=kek_bytes)
            return {
                "valid": True,
                "format": "kbkp",
                "size_bytes": len(file_bytes),
                "plain_bytes": len(decrypted),
            }

        manifest = verify_backup(tmp_path, key_source)
        return {
            "valid": True,
            "format": "kbbak",
            "manifest": manifest.to_dict(),
            "size_bytes": len(file_bytes),
        }
    except Exception as exc:
        logger.warning("Backup verification failed: %s", exc)
        raise ProblemException(
            code="BACKUP_VERIFICATION_FAILED",
            status=422,
            title="Backup Verification Failed",
            detail=f"Verification failed: {exc}",
        ) from exc
    finally:
        await asyncio.to_thread(tmp_path.unlink, missing_ok=True)


@admin_standalone_router.post(
    "/restore",
    summary="Restore database from an encrypted backup archive",
    dependencies=[Depends(require_server_admin)],
)
async def restore_backup_endpoint(  # noqa: C901, PLR0912, PLR0915
    request: Request,
    caller: Annotated[PrincipalContext, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> dict[str, Any]:
    """Restore database from a backup archive with mandatory 'RESTORE' confirmation."""
    del caller, session
    content_type = request.headers.get("content-type", "")
    passphrase: str | None = None
    use_master_kek = False
    confirm_overwrite: str | None = None
    file_bytes: bytes | None = None
    filename: str | None = None

    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        uploaded_file = form.get("file")
        if uploaded_file and hasattr(uploaded_file, "read"):
            file_bytes = await uploaded_file.read()
            filename = getattr(uploaded_file, "filename", "restore_backup.kbbak")
        passphrase_val = form.get("passphrase")
        if isinstance(passphrase_val, str) and passphrase_val:
            passphrase = passphrase_val
        use_kek_val = form.get("use_master_kek")
        if isinstance(use_kek_val, str) and use_kek_val.lower() in ("true", "1"):
            use_master_kek = True
        confirm_val = form.get("confirm_overwrite")
        if isinstance(confirm_val, str):
            confirm_overwrite = confirm_val
    else:
        body = await request.json()
        filename = body.get("filename")
        passphrase = body.get("passphrase")
        use_master_kek = bool(body.get("use_master_kek", False))
        confirm_overwrite = body.get("confirm_overwrite")

    if confirm_overwrite != "RESTORE":
        raise ProblemException(
            code="INVALID_CONFIRM_OVERWRITE",
            status=422,
            title="Confirmation Required",
            detail="Database restore requires confirm_overwrite='RESTORE'.",
            type_uri="urn:kanban:problem:invalid-confirm-overwrite",
        )

    if not file_bytes and filename:
        if not re.match(r"^[a-zA-Z0-9._-]+$", filename) or ".." in filename:
            raise ProblemException(
                code="INVALID_FILENAME",
                status=400,
                title="Invalid Filename",
                detail="Filename contains forbidden characters.",
            )
        backup_dir = resolve_backup_dir()
        target = backup_dir / filename
        if not target.is_file():
            raise ProblemException(
                code="BACKUP_NOT_FOUND",
                status=404,
                title="Backup Not Found",
                detail=f"Backup file '{filename}' was not found.",
            )
        file_bytes = target.read_bytes()

    if not file_bytes:
        raise ProblemException(
            code="MISSING_BACKUP_PAYLOAD",
            status=422,
            title="Missing Backup Payload",
            detail="Either an uploaded backup file or a valid server filename is required.",
        )

    settings = getattr(request.app.state, "settings", None)
    target_db_url = settings.database_url if settings else None
    if not target_db_url:
        target_db_url = os.environ.get("DATABASE_URL")

    if not target_db_url:
        raise ProblemException(
            code="DATABASE_UNAVAILABLE",
            status=500,
            title="Database Unavailable",
            detail="Target database connection URL is not configured.",
        )

    key_source: KeySource | None = None
    if use_master_kek:
        key_material = getattr(request.app.state, "key_material", None)
        master_kek = getattr(key_material, "master_kek", None) if key_material else None
        if master_kek:
            key_source = RawKeySource(master_kek)
    elif passphrase:
        key_source = PassphraseKeySource(passphrase)

    if key_source is None:
        key_material = getattr(request.app.state, "key_material", None)
        master_kek = getattr(key_material, "master_kek", None) if key_material else None
        key_source = RawKeySource(master_kek) if master_kek else RawKeySource(b"\x00" * 32)

    with tempfile.NamedTemporaryFile(prefix="kb_restore_target_", delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = Path(tmp.name)

    try:
        report = restore_backup(
            archive_path=tmp_path,
            target_db_url=target_db_url,
            key_source=key_source,
            confirm_overwrite=True,
        )
    except Exception as exc:
        logger.exception("Database restore execution failed")
        raise ProblemException(
            code="RESTORE_EXECUTION_FAILED",
            status=500,
            title="Restore Failed",
            detail=f"Database restore failed: {exc}",
        ) from exc
    else:
        return {
            "status": "success",
            "message": "Database restored successfully",
            "workspaces_verified": report.workspaces_verified,
            "links_audited": report.links_audited,
            "duration_seconds": report.duration_seconds,
        }
    finally:
        await asyncio.to_thread(tmp_path.unlink, missing_ok=True)
