"""Attachment domain service orchestrating validation, storage, and activity recording."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from database.models import Attachment
from kanban.api.problems import not_found
from kanban.attachments.pdf import sanitize_and_validate_pdf
from kanban.attachments.raster import sanitize_and_reencode_raster
from kanban.attachments.signing import sign_attachment_url
from kanban.attachments.sniff import (
    sanitize_original_filename,
    sniff_media_type,
)
from kanban.services.activity import ActivityEventType, record_activity

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext
    from kanban.attachments.storage import LocalFilesystemBlobStore


class AttachmentService:
    """Service orchestrating attachment upload, RLS verification, and signed URL generation."""

    def __init__(
        self,
        blob_store: LocalFilesystemBlobStore,
        session_hmac_key: bytes,
    ) -> None:
        """Initialize attachment service with storage backend and HMAC key."""
        self.blob_store = blob_store
        self.session_hmac_key = session_hmac_key

    async def upload_attachment(  # noqa: PLR0913, PLR0917
        self,
        session: AsyncSession,
        caller: PrincipalContext,
        project_id: uuid.UUID,
        workspace_id: uuid.UUID,
        issue_id: uuid.UUID | None,
        raw_filename: str,
        raw_bytes: bytes,
        declared_content_type: str | None,
    ) -> dict[str, Any]:
        """Validate, sanitize, persist, and record an attachment upload."""
        # 1. Magic-byte verification and content-type negotiation
        detected_type = sniff_media_type(
            raw_bytes[:4096],
            declared_content_type,
            raw_filename,
        )

        # 2. Decompression-bomb inspection and content-specific validation/re-encoding
        page_count: int | None = None
        if detected_type == "application/pdf":
            pdf_result = await sanitize_and_validate_pdf(raw_bytes)
            clean_bytes = pdf_result.clean_bytes
            blob_sha256 = pdf_result.blob_sha256
            byte_size = pdf_result.byte_size
            pixel_width = None
            pixel_height = None
            page_count = pdf_result.page_count
        else:
            processed = await sanitize_and_reencode_raster(raw_bytes, detected_type)
            clean_bytes = processed.clean_bytes
            blob_sha256 = processed.blob_sha256
            byte_size = processed.byte_size
            pixel_width = processed.pixel_width
            pixel_height = processed.pixel_height

        # 3. Content-addressed atomic filesystem storage
        storage_key, _ = self.blob_store.store(clean_bytes)

        # 4. Safe filename handling for metadata row
        safe_db_filename = sanitize_original_filename(raw_filename)

        # 5. Database metadata persistence under RLS
        attachment = Attachment(
            workspace_id=workspace_id,
            project_id=project_id,
            issue_id=issue_id,
            uploaded_by_id=caller.principal_id,
            original_filename=safe_db_filename,
            content_type=detected_type,
            byte_size=byte_size,
            pixel_width=pixel_width,
            pixel_height=pixel_height,
            page_count=page_count,
            blob_sha256=blob_sha256,
            storage_key=storage_key,
        )
        session.add(attachment)
        await session.flush()

        # 6. Immutable Activity Ledger recording
        target_object_id = issue_id if issue_id is not None else project_id
        await record_activity(
            session,
            workspace_id=workspace_id,
            object_id=target_object_id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.ATTACHMENT_UPLOADED,
            payload={
                "attachment_id": str(attachment.id),
                "original_filename": attachment.original_filename,
                "content_type": attachment.content_type,
                "byte_size": attachment.byte_size,
                "storage_key": attachment.storage_key,
            },
        )

        # 7. Mint initial 300s signed URL
        signed_url = sign_attachment_url(
            attachment.id,
            caller.principal_id,
            self.session_hmac_key,
            ttl_seconds=300,
        )

        return {
            "id": attachment.id,
            "markdown_uri": f"attachment://att_{attachment.id}",
            "content_type": attachment.content_type,
            "byte_size": attachment.byte_size,
            "pixel_width": attachment.pixel_width,
            "pixel_height": attachment.pixel_height,
            "page_count": attachment.page_count,
            "signed_url": signed_url,
            "expires_in": 300,
        }

    async def get_attachment_or_404(
        self,
        session: AsyncSession,
        attachment_id: uuid.UUID,
    ) -> Attachment:
        """Fetch attachment row by ID or raise canonical 404."""
        stmt = select(Attachment).where(Attachment.id == attachment_id)
        attachment = (await session.execute(stmt)).scalar_one_or_none()
        if attachment is None:
            not_found()
        return attachment

    def mint_signed_url(
        self,
        attachment_id: uuid.UUID,
        principal_id: uuid.UUID,
    ) -> str:
        """Mint a 300s signed URL for an attachment and principal."""
        return sign_attachment_url(
            attachment_id,
            principal_id,
            self.session_hmac_key,
            ttl_seconds=300,
        )
