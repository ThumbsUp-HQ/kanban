"""Attachment REST endpoints: upload, signed-url minting, and content serving (S5.4)."""

from __future__ import annotations

import contextlib
import email
import os
import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Issue
from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.problems import ProblemException, not_found
from kanban.api.timing import timing_floor
from kanban.api.v1.schemas.attachments import (
    AttachmentMetaResponse,
    AttachmentResponse,
    SignedUrlResponse,
)
from kanban.attachments.service import AttachmentService
from kanban.attachments.signing import verify_attachment_url
from kanban.attachments.sniff import (
    MAX_ATTACHMENT_BYTES,
    sanitize_content_disposition_filename,
)
from kanban.attachments.storage import LocalFilesystemBlobStore
from kanban.security.granular_permissions import GranularPermission, require_permissions
from kanban.security.permissions import Capability, evaluate_capabilities, require_capability
from kanban.security.ratelimit import ATTACHMENT_UPLOAD_PRINCIPAL
from kanban.security.ratelimit.decorator import rate_limited
from kanban.services.projects import get_project_or_404

router = APIRouter(tags=["attachments"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


async def _principal_rate_key(request: Request) -> list[str]:
    """Extract authenticated principal ID for upload rate limiting."""
    caller = await get_principal(request)
    return [str(caller.principal_id)]


def get_attachment_service(request: Request) -> AttachmentService:
    """Resolve or construct AttachmentService from application state."""
    service: AttachmentService | None = getattr(request.app.state, "attachment_service", None)
    if service is not None:
        return service

    blob_store: LocalFilesystemBlobStore | None = getattr(
        request.app.state, "attachment_blob_store", None
    )
    if blob_store is None:
        root_dir = os.environ.get("KANBAN_ATTACHMENT_DIR", "/tmp/kanban-attachments")  # noqa: S108
        blob_store = LocalFilesystemBlobStore(root_dir)
        request.app.state.attachment_blob_store = blob_store

    km = getattr(request.app.state, "key_material", None)
    if km is None:
        try:
            from kanban.security.keys import load_key_material  # noqa: PLC0415

            km = load_key_material()
        except Exception:  # noqa: BLE001
            km = None
    session_hmac_key = km.session_hmac_key if km is not None else b"\x00" * 32

    service = AttachmentService(blob_store, session_hmac_key)
    request.app.state.attachment_service = service
    return service


def _parse_multipart_body(
    content_type_header: str,
    body_bytes: bytes,
) -> tuple[str, str | None, uuid.UUID | None, bytes]:
    """Parse multipart form-data payload using standard MIME parser."""
    raw_filename = "attachment"
    declared_content_type: str | None = None
    target_issue_id: uuid.UUID | None = None
    raw_file_bytes = body_bytes

    msg_bytes = b"Content-Type: " + content_type_header.encode("latin-1") + b"\r\n\r\n" + body_bytes
    parsed_msg = email.message_from_bytes(msg_bytes)
    if parsed_msg.is_multipart():
        parts = parsed_msg.get_payload()
        if isinstance(parts, list):
            for part in parts:
                if not isinstance(part, email.message.Message):
                    continue
                name = part.get_param("name", header="content-disposition")
                payload_raw = part.get_payload(decode=True)
                if not isinstance(payload_raw, bytes):
                    continue
                if name == "issue_id":
                    issue_val = payload_raw.decode("utf-8", errors="replace").strip()
                    if issue_val:
                        with contextlib.suppress(ValueError):
                            target_issue_id = uuid.UUID(issue_val)
                elif name in ("file", "attachment") or part.get_filename():
                    raw_filename = part.get_filename() or raw_filename
                    declared_content_type = part.get_content_type()
                    raw_file_bytes = payload_raw

    return raw_filename, declared_content_type, target_issue_id, raw_file_bytes


def _parse_raw_upload_request(
    request: Request,
    body_bytes: bytes,
) -> tuple[str, str | None, uuid.UUID | None, bytes]:
    """Parse raw binary upload stream extracting headers and query params."""
    content_type_header = request.headers.get("content-type", "")
    declared_content_type = content_type_header.split(";")[0].strip() or None
    raw_filename = "attachment"
    target_issue_id: uuid.UUID | None = None

    if "x-filename" in request.headers:
        raw_filename = request.headers["x-filename"]
    elif "content-disposition" in request.headers:
        cd = request.headers["content-disposition"]
        match = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', cd, re.IGNORECASE)
        if match:
            raw_filename = match.group(1)
    elif "filename" in request.query_params:
        raw_filename = request.query_params["filename"]

    if "issue_id" in request.query_params:
        with contextlib.suppress(ValueError):
            target_issue_id = uuid.UUID(request.query_params["issue_id"])

    return raw_filename, declared_content_type, target_issue_id, body_bytes


def _parse_upload_body(
    request: Request,
    body_bytes: bytes,
) -> tuple[str, str | None, uuid.UUID | None, bytes]:
    """Dispatch payload parsing based on content-type header."""
    content_type_header = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type_header.lower():
        raw_fn, decl_ct, target_id, raw_bytes = _parse_multipart_body(
            content_type_header, body_bytes
        )
    else:
        raw_fn, decl_ct, target_id, raw_bytes = _parse_raw_upload_request(request, body_bytes)

    if len(raw_bytes) > MAX_ATTACHMENT_BYTES:
        raise ProblemException(
            code="PAYLOAD_TOO_LARGE",
            status=413,
            title="Payload Too Large",
            detail=f"Attachment payload exceeds {MAX_ATTACHMENT_BYTES} bytes",
        )
    return raw_fn, decl_ct, target_id, raw_bytes


async def _read_stream_payload(request: Request) -> bytes:
    """Stream request body enforcing MAX_ATTACHMENT_BYTES limit."""
    chunks: list[bytes] = []
    total_bytes = 0
    async for chunk in request.stream():
        total_bytes += len(chunk)
        if total_bytes > MAX_ATTACHMENT_BYTES:
            raise ProblemException(
                code="PAYLOAD_TOO_LARGE",
                status=413,
                title="Payload Too Large",
                detail=f"Attachment exceeds maximum allowed size of {MAX_ATTACHMENT_BYTES} bytes",
            )
        chunks.append(chunk)

    body_bytes = b"".join(chunks)
    if not body_bytes:
        raise ProblemException(
            code="MIME_MISMATCH_OR_UNSUPPORTED",
            status=415,
            title="Unsupported Media Type",
            detail="Attachment payload is empty",
        )
    return body_bytes


async def _verify_upload_permissions(
    session: AsyncSession,
    caller: PrincipalContext,
    project_id: uuid.UUID,
    target_issue_id: uuid.UUID | None,
) -> None:
    """Enforce upload permissions on project and optional issue."""
    caps = await evaluate_capabilities(session, caller, project_id)
    if not (caps & (Capability.COMMENT | Capability.EDIT)):
        raise ProblemException(
            code="INSUFFICIENT_CAPABILITY",
            status=403,
            title="Insufficient Capability",
            detail="Uploading attachments requires COMMENT or EDIT capability on target project",
        )
    await require_permissions(
        session,
        caller,
        caller.workspace_id,
        {GranularPermission.FIELD_ATTACH_FILES.value},
        project_id=project_id,
        object_readable=True,
        object_id=target_issue_id,
    )

    if target_issue_id is not None:
        issue_stmt = select(Issue).where(
            Issue.id == target_issue_id,
            Issue.project_id == project_id,
            Issue.workspace_id == caller.workspace_id,
        )
        issue = (await session.execute(issue_stmt)).scalar_one_or_none()
        if issue is None:
            not_found()
        issue_caps = await evaluate_capabilities(session, caller, target_issue_id)
        if Capability.VIEW not in issue_caps:
            not_found()
        if not (issue_caps & (Capability.COMMENT | Capability.EDIT)):
            raise ProblemException(
                code="INSUFFICIENT_CAPABILITY",
                status=403,
                title="Insufficient Capability",
                detail="Uploading attachments requires COMMENT or EDIT capability on target issue",
            )


@router.post(
    "/projects/{project_ref}/attachments",
    status_code=201,
    response_model=AttachmentResponse,
    summary="Upload media attachment",
    dependencies=[Depends(rate_limited(ATTACHMENT_UPLOAD_PRINCIPAL, key_func=_principal_rate_key))],
)
async def upload_attachment(
    project_ref: str,
    request: Request,
    caller: Caller,
    session: Session,
) -> AttachmentResponse:
    """Stream and validate attachment upload with decompression-bomb guards and metadata strip."""
    project = await get_project_or_404(session, caller, project_ref)
    body_bytes = await _read_stream_payload(request)
    raw_fn, decl_ct, target_issue_id, raw_bytes = _parse_upload_body(request, body_bytes)
    await _verify_upload_permissions(session, caller, project.id, target_issue_id)

    service = get_attachment_service(request)
    result = await service.upload_attachment(
        session=session,
        caller=caller,
        project_id=project.id,
        workspace_id=caller.workspace_id,
        issue_id=target_issue_id,
        raw_filename=raw_fn,
        raw_bytes=raw_bytes,
        declared_content_type=decl_ct,
    )

    return AttachmentResponse(**result)


@router.post(
    "/attachments/{attachment_id}/signed-url",
    response_model=SignedUrlResponse,
    summary="Mint signed URL for attachment",
)
async def create_signed_url(
    attachment_id: uuid.UUID,
    caller: Caller,
    session: Session,
    request: Request,
) -> SignedUrlResponse:
    """Verify Capability.VIEW on owning resource and mint 300s signed URL."""
    async with timing_floor(floor_ms=25.0):
        service = get_attachment_service(request)
        attachment = await service.get_attachment_or_404(session, attachment_id)
        target_resource = (
            attachment.issue_id if attachment.issue_id is not None else attachment.project_id
        )
        await require_capability(session, caller, target_resource, Capability.VIEW)
        url = service.mint_signed_url(attachment.id, caller.principal_id)
        return SignedUrlResponse(signed_url=url, expires_in=300)


@router.get(
    "/attachments/{attachment_id}/meta",
    response_model=AttachmentMetaResponse,
    summary="Retrieve attachment metadata",
)
async def get_attachment_meta(
    attachment_id: uuid.UUID,
    request: Request,
    caller: Caller,
    session: Session,
) -> AttachmentMetaResponse:
    """Retrieve attachment metadata enforcing caller VIEW capability."""
    async with timing_floor(floor_ms=25.0):
        service = get_attachment_service(request)
        attachment = await service.get_attachment_or_404(session, attachment_id)
        target_resource = (
            attachment.issue_id if attachment.issue_id is not None else attachment.project_id
        )
        await require_capability(session, caller, target_resource, Capability.VIEW)
        sha_hex = attachment.blob_sha256.hex() if attachment.blob_sha256 else ""
        return AttachmentMetaResponse(
            id=attachment.id,
            original_filename=attachment.original_filename,
            content_type=attachment.content_type,
            byte_size=attachment.byte_size,
            page_count=attachment.page_count,
            blob_sha256=sha_hex,
        )


@router.get(
    "/attachments/{attachment_id}",
    summary="Retrieve attachment blob directly for authenticated caller",
)
async def get_attachment_direct(
    attachment_id: uuid.UUID,
    request: Request,
    caller: Caller,
    session: Session,
) -> Response:
    """Retrieve attachment content blob enforcing caller capability and .svg sandbox shield."""
    async with timing_floor(floor_ms=25.0):
        service = get_attachment_service(request)
        attachment = await service.get_attachment_or_404(session, attachment_id)
        target_resource = (
            attachment.issue_id if attachment.issue_id is not None else attachment.project_id
        )
        await require_capability(session, caller, target_resource, Capability.VIEW)
        blob_bytes = service.blob_store.read(attachment.storage_key)

    headers: dict[str, str] = {
        "X-Content-Type-Options": "nosniff",
        "Cross-Origin-Resource-Policy": "same-origin",
        "Cache-Control": "private, max-age=300",
    }

    safe_filename = sanitize_content_disposition_filename(
        attachment.original_filename,
        attachment.content_type,
    )

    is_download_requested = request.query_params.get("download") == "1"

    if attachment.content_type == "image/svg+xml":
        headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
        sec_dest = (request.headers.get("sec-fetch-dest") or "").strip().lower()
        if sec_dest == "image" and not is_download_requested:
            headers["Content-Disposition"] = f'inline; filename="{safe_filename}"'
        else:
            headers["Content-Disposition"] = f'attachment; filename="{safe_filename}"'
    elif attachment.content_type == "application/pdf":
        headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
        headers["Content-Disposition"] = f'attachment; filename="{safe_filename}"'
    elif is_download_requested:
        headers["Content-Disposition"] = f'attachment; filename="{safe_filename}"'
    else:
        headers["Content-Disposition"] = f'inline; filename="{safe_filename}"'

    return Response(
        content=blob_bytes,
        media_type=attachment.content_type,
        headers=headers,
    )


@router.get(
    "/attachments/{attachment_id}/content",
    summary="Retrieve attachment blob content",
)
async def get_attachment_content(  # noqa: PLR0913, PLR0917
    attachment_id: uuid.UUID,
    exp: Annotated[int, Query(description="Signature expiration timestamp")],
    p: Annotated[str, Query(description="Authorized principal ID")],
    sig: Annotated[str, Query(description="HMAC-SHA256 signature")],
    request: Request,
    caller: Caller,
    session: Session,
) -> Response:
    """Retrieve attachment content blob enforcing signature, live RLS, and .svg sandbox shield."""
    # 1. Reject expired or invalid signature BEFORE any DB or disk access
    service = get_attachment_service(request)
    if not verify_attachment_url(
        attachment_id=attachment_id,
        principal_id=p,
        exp=exp,
        sig=sig,
        session_hmac_key=service.session_hmac_key,
    ):
        raise ProblemException(
            code="INVALID_SIGNED_URL",
            status=403,
            title="Invalid Signed URL",
            detail="Signed URL has expired or has an invalid signature",
        )

    # 2. Verify active authenticated principal matches p
    if str(caller.principal_id) != str(p):
        raise ProblemException(
            code="INVALID_SIGNED_URL",
            status=403,
            title="Forbidden",
            detail="Signed URL principal does not match authenticated caller",
        )

    # 3. Live RLS re-verification inside timing floor
    async with timing_floor(floor_ms=25.0):
        attachment = await service.get_attachment_or_404(session, attachment_id)
        target_resource = (
            attachment.issue_id if attachment.issue_id is not None else attachment.project_id
        )
        await require_capability(session, caller, target_resource, Capability.VIEW)
        blob_bytes = service.blob_store.read(attachment.storage_key)

    # 4. Mandatory HTTP response headers
    headers: dict[str, str] = {
        "X-Content-Type-Options": "nosniff",
        "Cross-Origin-Resource-Policy": "same-origin",
        "Cache-Control": "private, max-age=300",
    }

    safe_filename = sanitize_content_disposition_filename(
        attachment.original_filename,
        attachment.content_type,
    )

    # 5. .svg Direct-URL Navigation Shield
    is_download_requested = request.query_params.get("download") == "1"

    if attachment.content_type == "image/svg+xml":
        headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
        sec_dest = (request.headers.get("sec-fetch-dest") or "").strip().lower()
        if sec_dest == "image" and not is_download_requested:
            headers["Content-Disposition"] = f'inline; filename="{safe_filename}"'
        else:
            headers["Content-Disposition"] = f'attachment; filename="{safe_filename}"'
    elif attachment.content_type == "application/pdf":
        headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
        headers["Content-Disposition"] = f'attachment; filename="{safe_filename}"'
    elif is_download_requested:
        headers["Content-Disposition"] = f'attachment; filename="{safe_filename}"'
    else:
        headers["Content-Disposition"] = f'inline; filename="{safe_filename}"'

    return Response(
        content=blob_bytes,
        media_type=attachment.content_type,
        headers=headers,
    )
