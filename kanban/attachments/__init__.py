"""Attachment storage, media sniffing, metadata stripping, and signed URL service (S5.4)."""

from kanban.attachments.raster import (
    MAX_ANIMATED_FRAMES,
    MAX_ANIMATED_TOTAL_PIXELS,
    MAX_DIMENSION,
    MAX_IMAGE_PIXELS,
    ProcessedAttachment,
    sanitize_and_reencode_avatar,
    sanitize_and_reencode_avatar_sync,
    sanitize_and_reencode_raster,
    sanitize_and_reencode_raster_sync,
)
from kanban.attachments.service import AttachmentService
from kanban.attachments.signing import (
    DEFAULT_SIGNED_URL_TTL_SECONDS,
    sign_attachment_url,
    verify_attachment_url,
)
from kanban.attachments.sniff import (
    ALLOWED_MEDIA_TYPES,
    MAX_ATTACHMENT_BYTES,
    sanitize_content_disposition_filename,
    sanitize_original_filename,
    sniff_media_type,
)
from kanban.attachments.storage import (
    BlobStorageError,
    LocalFilesystemBlobStore,
)

__all__ = [
    "ALLOWED_MEDIA_TYPES",
    "DEFAULT_SIGNED_URL_TTL_SECONDS",
    "MAX_ANIMATED_FRAMES",
    "MAX_ANIMATED_TOTAL_PIXELS",
    "MAX_ATTACHMENT_BYTES",
    "MAX_DIMENSION",
    "MAX_IMAGE_PIXELS",
    "AttachmentService",
    "BlobStorageError",
    "LocalFilesystemBlobStore",
    "ProcessedAttachment",
    "sanitize_and_reencode_avatar",
    "sanitize_and_reencode_avatar_sync",
    "sanitize_and_reencode_raster",
    "sanitize_and_reencode_raster_sync",
    "sanitize_content_disposition_filename",
    "sanitize_original_filename",
    "sign_attachment_url",
    "sniff_media_type",
    "verify_attachment_url",
]
