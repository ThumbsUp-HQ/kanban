# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""User personal settings studio API endpoints (KB-USER-SETTINGS / KANBA-187)."""

from __future__ import annotations

import email
import email.message
import logging
import os
import uuid
import zoneinfo
from typing import TYPE_CHECKING, Annotated, Final, Literal, cast

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from starlette.requests import Request  # noqa: TC002  # Required at runtime by FastAPI
from starlette.responses import JSONResponse

from database.session import RLSContext
from kanban.api.deps import PrincipalContext, get_principal
from kanban.api.problems import ProblemException
from kanban.attachments.raster import sanitize_and_reencode_raster
from kanban.attachments.sniff import sniff_media_type
from kanban.attachments.storage import LocalFilesystemBlobStore
from kanban.auth.local.hashing import get_auth_pepper, hash_password, verify_password
from kanban.services.activity import ActivityEventType, record_activity

if TYPE_CHECKING:
    from database.session import RLSSessionFactory

logger = logging.getLogger(__name__)

router = APIRouter(tags=["user-settings"])

MAX_AVATAR_BYTES: Final[int] = 2 * 1024 * 1024  # 2 MiB exact
MAX_DISPLAY_NAME_LENGTH: Final[int] = 120
AAL2_REQUIRED_LEVEL: Final[int] = 2
ADMIN_MIN_PASSWORD_LENGTH: Final[int] = 14
USER_MIN_PASSWORD_LENGTH: Final[int] = 12
ALLOWED_AVATAR_TYPES: Final[frozenset[str]] = frozenset({"image/png", "image/jpeg", "image/webp"})


class UpdateProfileRequest(BaseModel):
    """Payload for updating personal profile display name and timezone."""

    display_name: str = Field(
        min_length=1, max_length=120, description="Display name (1..120 characters)"
    )
    timezone: str = Field(default="UTC", description="Valid IANA timezone identifier")


class ChangePasswordRequest(BaseModel):
    """Payload for updating personal local login password."""

    current_password: str | None = Field(
        default=None, description="Current local password (if one exists)"
    )
    new_password: str = Field(
        min_length=1, description="New local password (>=14 for admins, >=12 for standard)"
    )


def _get_blob_store(request: Request) -> LocalFilesystemBlobStore:
    """Resolve or construct LocalFilesystemBlobStore from application state."""
    blob_store: LocalFilesystemBlobStore | None = getattr(
        request.app.state, "attachment_blob_store", None
    )
    if blob_store is None:
        root_dir = os.environ.get("KANBAN_ATTACHMENT_DIR", "/tmp/kanban-attachments")  # noqa: S108
        blob_store = LocalFilesystemBlobStore(root_dir)
        request.app.state.attachment_blob_store = blob_store
    return blob_store


def _resolve_auth_pepper(request: Request) -> bytes:
    """Resolve auth pepper from app key material or runtime environment."""
    km = getattr(request.app.state, "key_material", None)
    if km is not None and getattr(km, "auth_pepper", None):
        auth_pepper: bytes = km.auth_pepper
        return auth_pepper
    return get_auth_pepper()


@router.patch("/auth/me")
async def update_profile(
    body: UpdateProfileRequest,
    request: Request,
    principal: Annotated[PrincipalContext, Depends(get_principal)],
) -> JSONResponse:
    """Update own profile display name and timezone."""
    cleaned_name = body.display_name.strip()
    if not (1 <= len(cleaned_name) <= MAX_DISPLAY_NAME_LENGTH):
        raise ProblemException(
            code="INVALID_DISPLAY_NAME",
            status=422,
            title="Invalid Display Name",
            detail=f"Display name must be between 1 and {MAX_DISPLAY_NAME_LENGTH} characters.",
        )

    cleaned_tz = body.timezone.strip()
    if cleaned_tz not in zoneinfo.available_timezones():
        raise ProblemException(
            code="INVALID_TIMEZONE",
            status=422,
            title="Invalid Timezone",
            detail=f"Timezone '{cleaned_tz}' is not a valid IANA timezone identifier.",
        )

    session_factory: RLSSessionFactory | None = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        msg = "Session factory is not configured on app.state.session_factory"
        raise RuntimeError(msg)

    rls_ctx = RLSContext(
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        token_scopes=principal.token_scopes,
        aal_level=cast("Literal[1, 2]", principal.aal_level),
    )

    async with session_factory.session(rls_ctx) as session:
        await session.execute(
            text("SELECT kb_auth.user_update_own_profile(:p_id, :name, :tz)"),
            {
                "p_id": principal.principal_id,
                "name": cleaned_name,
                "tz": cleaned_tz,
            },
        )

    return JSONResponse(
        content={
            "id": str(principal.principal_id),
            "display_name": cleaned_name,
            "timezone": cleaned_tz,
        }
    )


def _parse_avatar_upload(request: Request, body_bytes: bytes) -> tuple[str, str | None, bytes]:
    """Parse multipart form-data or raw binary payload."""
    content_type_header = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type_header.lower():
        msg_bytes = (
            b"Content-Type: " + content_type_header.encode("latin-1") + b"\r\n\r\n" + body_bytes
        )
        parsed_msg = email.message_from_bytes(msg_bytes)
        if parsed_msg.is_multipart():
            parts = parsed_msg.get_payload()
            if isinstance(parts, list):
                for part in parts:
                    if not isinstance(part, email.message.Message):
                        continue
                    payload_raw = part.get_payload(decode=True)
                    if isinstance(payload_raw, bytes):
                        part_fn = part.get_filename() or "avatar.png"
                        part_ct = part.get_content_type()
                        return part_fn, part_ct, payload_raw

    fn = request.headers.get("x-filename") or "avatar.png"
    ct: str | None = content_type_header.split(";")[0].strip() or None
    return fn, ct, body_bytes


@router.put("/auth/me/avatar")
async def upload_avatar(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(get_principal)],
) -> JSONResponse:
    """Upload, sanitize, re-encode and set a personal avatar."""
    chunks: list[bytes] = []
    total_bytes = 0
    async for chunk in request.stream():
        total_bytes += len(chunk)
        if total_bytes > MAX_AVATAR_BYTES + 65536:
            raise ProblemException(
                code="PAYLOAD_TOO_LARGE",
                status=413,
                title="Payload Too Large",
                detail="Avatar image exceeds maximum 2 MiB limit.",
            )
        chunks.append(chunk)

    body_bytes = b"".join(chunks)
    if not body_bytes:
        raise ProblemException(
            code="EMPTY_PAYLOAD",
            status=400,
            title="Empty Payload",
            detail="Uploaded avatar image file is empty.",
        )

    filename, declared_ct, raw_bytes = _parse_avatar_upload(request, body_bytes)
    return await _process_and_store_avatar(
        request=request,
        principal=principal,
        filename=filename,
        declared_ct=declared_ct,
        raw_bytes=raw_bytes,
    )


async def _process_and_store_avatar(
    request: Request,
    principal: PrincipalContext,
    filename: str,
    declared_ct: str | None,
    raw_bytes: bytes,
) -> JSONResponse:
    if len(raw_bytes) > MAX_AVATAR_BYTES:
        raise ProblemException(
            code="PAYLOAD_TOO_LARGE",
            status=413,
            title="Payload Too Large",
            detail="Avatar image exceeds maximum 2 MiB limit.",
        )
    if not raw_bytes:
        raise ProblemException(
            code="EMPTY_PAYLOAD",
            status=400,
            title="Empty Payload",
            detail="Uploaded avatar image file is empty.",
        )

    try:
        detected = sniff_media_type(raw_bytes[:1024], declared_ct, filename)
    except ProblemException:
        raise
    except Exception as exc:
        raise ProblemException(
            code="UNSUPPORTED_MEDIA_TYPE",
            status=415,
            title="Unsupported Media Type",
            detail=f"Failed to identify image format: {exc}",
        ) from exc

    if detected == "image/svg+xml":
        raise ProblemException(
            code="UNSUPPORTED_MEDIA_TYPE",
            status=415,
            title="Unsupported Media Type",
            detail="SVG avatars are not allowed. Please upload PNG, JPEG, or WebP.",
        )

    if detected not in ALLOWED_AVATAR_TYPES:
        raise ProblemException(
            code="UNSUPPORTED_MEDIA_TYPE",
            status=415,
            title="Unsupported Media Type",
            detail="Only PNG, JPEG, and WebP raster avatars are supported.",
        )

    processed = await sanitize_and_reencode_raster(raw_bytes, detected)
    blob_store = _get_blob_store(request)
    storage_key, raw_sha = blob_store.store(processed.clean_bytes)

    session_factory: RLSSessionFactory | None = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        msg = "Session factory is not configured on app.state.session_factory"
        raise RuntimeError(msg)

    rls_ctx = RLSContext(
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        token_scopes=principal.token_scopes,
        aal_level=cast("Literal[1, 2]", principal.aal_level),
    )

    async with session_factory.session(rls_ctx) as session:
        await session.execute(
            text(
                "INSERT INTO public.user_preferences "
                "(principal_id, workspace_id, avatar_storage_key, avatar_content_type, "
                "avatar_sha256, updated_at) "
                "VALUES (:p_id, :w_id, :s_key, :c_type, :sha, clock_timestamp()) "
                "ON CONFLICT (principal_id) DO UPDATE "
                "SET avatar_storage_key = EXCLUDED.avatar_storage_key, "
                "    avatar_content_type = EXCLUDED.avatar_content_type, "
                "    avatar_sha256 = EXCLUDED.avatar_sha256, "
                "    updated_at = clock_timestamp()"
            ),
            {
                "p_id": principal.principal_id,
                "w_id": principal.workspace_id,
                "s_key": storage_key,
                "c_type": processed.content_type,
                "sha": raw_sha,
            },
        )

    return JSONResponse(
        content={
            "avatar_url": f"/api/v1/users/{principal.principal_id}/avatar",
        }
    )


@router.delete("/auth/me/avatar")
async def delete_avatar(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(get_principal)],
) -> JSONResponse:
    """Remove personal avatar."""
    session_factory: RLSSessionFactory | None = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        msg = "Session factory is not configured on app.state.session_factory"
        raise RuntimeError(msg)

    rls_ctx = RLSContext(
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        token_scopes=principal.token_scopes,
        aal_level=cast("Literal[1, 2]", principal.aal_level),
    )

    async with session_factory.session(rls_ctx) as session:
        await session.execute(
            text(
                "UPDATE public.user_preferences "
                "SET avatar_storage_key = NULL, avatar_content_type = NULL, "
                "    avatar_sha256 = NULL, updated_at = clock_timestamp() "
                "WHERE principal_id = :p_id"
            ),
            {"p_id": principal.principal_id},
        )

    return JSONResponse(content={"avatar_url": None})


@router.get("/users/{principal_id}/avatar")
async def get_user_avatar(
    principal_id: uuid.UUID,
    request: Request,
) -> Response:
    """Retrieve and serve user avatar image bytes."""
    session_factory: RLSSessionFactory | None = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        msg = "Session factory is not configured on app.state.session_factory"
        raise RuntimeError(msg)

    anon_ctx = RLSContext(
        principal_id=uuid.UUID(int=0),
        workspace_id=uuid.UUID(int=0),
        token_scopes=("session",),
        aal_level=1,
    )

    storage_key: str | None = None
    content_type: str = "image/png"

    async with session_factory.session(anon_ctx) as session:
        res = await session.execute(
            text("SELECT * FROM kb_auth.user_get_avatar(:p_id)"),
            {"p_id": principal_id},
        )
        row = res.mappings().first()
        if row and row["avatar_storage_key"]:
            storage_key = row["avatar_storage_key"]
            if row["avatar_content_type"]:
                content_type = row["avatar_content_type"]

    if not storage_key:
        raise ProblemException(
            code="AVATAR_NOT_FOUND",
            status=404,
            title="Avatar Not Found",
            detail="User does not have an avatar set.",
        )

    blob_store = _get_blob_store(request)
    try:
        data = blob_store.read(storage_key)
    except Exception as exc:
        raise ProblemException(
            code="AVATAR_NOT_FOUND",
            status=404,
            title="Avatar Not Found",
            detail="Avatar storage file could not be read.",
        ) from exc

    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=3600",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
        },
    )


@router.post("/auth/me/password")
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    principal: Annotated[PrincipalContext, Depends(get_principal)],
) -> JSONResponse:
    """Change own local password with length validation, AAL2 check, and session revocation."""
    session_factory: RLSSessionFactory | None = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        msg = "Session factory is not configured on app.state.session_factory"
        raise RuntimeError(msg)

    rls_ctx = RLSContext(
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        token_scopes=principal.token_scopes,
        aal_level=cast("Literal[1, 2]", principal.aal_level),
    )

    async with session_factory.session(rls_ctx) as session:
        admin_res = await session.execute(
            text("SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])")
        )
        is_server_admin = bool(admin_res.scalar_one())

        proj_admin_res = await session.execute(
            text(
                "SELECT 1 FROM role_bindings "
                "WHERE principal_id = :p_id "
                "  AND role IN ('SERVER_ADMIN', 'PROJECT_ADMIN')"
            ),
            {"p_id": principal.principal_id},
        )
        is_admin = is_server_admin or (proj_admin_res.scalar_one_or_none() is not None)

        min_len = ADMIN_MIN_PASSWORD_LENGTH if is_admin else USER_MIN_PASSWORD_LENGTH
        if len(body.new_password) < min_len:
            raise ProblemException(
                code="PASSWORD_TOO_SHORT",
                status=422,
                title="Password Too Short",
                detail=f"Password must be at least {min_len} characters.",
            )

        if body.current_password is not None and body.new_password == body.current_password:
            raise ProblemException(
                code="PASSWORD_UNCHANGED",
                status=422,
                title="Password Unchanged",
                detail="New password cannot be identical to current password.",
            )

        cred_res = await session.execute(
            text("SELECT * FROM kb_auth.local_get_credential_by_principal(:p_id)"),
            {"p_id": principal.principal_id},
        )
        cred = cred_res.mappings().first()

        pepper = _resolve_auth_pepper(request)

        if cred is not None and cred["password_hash"]:
            if not body.current_password:
                raise ProblemException(
                    code="CURRENT_PASSWORD_REQUIRED",
                    status=422,
                    title="Current Password Required",
                    detail="Current password is required to change password.",
                )
            is_valid = await verify_password(
                cred["password_hash"], body.current_password, pepper=pepper
            )
            if not is_valid:
                raise ProblemException(
                    code="INVALID_CREDENTIALS",
                    status=401,
                    title="Invalid Current Password",
                    detail="Current password is incorrect.",
                )

        status_res = await session.execute(
            text("SELECT * FROM kb_auth.mfa_status(:p_id)"),
            {"p_id": principal.principal_id},
        )
        mfa_row = status_res.mappings().first()
        has_active_totp = bool(mfa_row and mfa_row["has_active_totp"])
        webauthn_count = int(mfa_row["webauthn_credential_count"]) if mfa_row else 0
        has_mfa = has_active_totp or (webauthn_count > 0)

        if (is_admin or has_mfa) and principal.aal_level < AAL2_REQUIRED_LEVEL:
            raise ProblemException(
                code="AAL2_REQUIRED",
                status=403,
                title="AAL2 Authentication Required",
                detail="Second-factor authentication is required to change password.",
            )

        new_hash = await hash_password(body.new_password, pepper=pepper)

        if cred is not None:
            await session.execute(
                text("SELECT kb_auth.local_set_password_hash(:p_id, :hash)"),
                {"p_id": principal.principal_id, "hash": new_hash},
            )
        else:
            p_res = await session.execute(
                text("SELECT display_name FROM principals WHERE id = :p_id"),
                {"p_id": principal.principal_id},
            )
            dname = p_res.scalar_one_or_none() or f"user-{principal.principal_id.hex[:8]}"
            await session.execute(
                text("SELECT kb_auth.local_admin_create(:p_id, :username, :hash)"),
                {
                    "p_id": principal.principal_id,
                    "username": dname,
                    "hash": new_hash,
                },
            )

        await session.execute(
            text("SELECT kb_auth.session_revoke_all_except(:p_id, :s_id)"),
            {
                "p_id": principal.principal_id,
                "s_id": principal.session_id,
            },
        )

        try:
            await record_activity(
                session,
                workspace_id=principal.workspace_id,
                actor_principal_id=principal.principal_id,
                event_type=ActivityEventType.USER_PASSWORD_CHANGED,
                payload={"principal_id": str(principal.principal_id)},
            )
        except Exception:
            logger.debug("Failed to record USER_PASSWORD_CHANGED activity", exc_info=True)

    return JSONResponse(
        content={
            "success": True,
            "message": "Password changed successfully.",
        }
    )
