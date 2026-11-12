"""Attachment schema models for upload and signed-url responses (S5.4, S5.2)."""

from __future__ import annotations

import uuid  # noqa: TC003  # Required at runtime for Pydantic schema validation
from typing import Annotated

from pydantic import BaseModel, Field


class AttachmentResponse(BaseModel):
    """Response returned upon successful attachment upload."""

    id: uuid.UUID
    markdown_uri: Annotated[
        str,
        Field(
            description="Canonical attachment URI for markdown embedding (attachment://att_<id>)"
        ),
    ]
    content_type: Annotated[str, Field(description="MIME media type")]
    byte_size: Annotated[int, Field(ge=1, le=26_214_400, description="Payload byte size")]
    pixel_width: Annotated[int | None, Field(default=None, description="Raster width in pixels")]
    pixel_height: Annotated[int | None, Field(default=None, description="Raster height in pixels")]
    signed_url: Annotated[str, Field(description="HMAC-SHA256 signed content retrieval URL")]
    expires_in: Annotated[int, Field(default=300, description="TTL in seconds for signed URL")]


class SignedUrlResponse(BaseModel):
    """Response returned when minting a signed URL for an existing attachment."""

    signed_url: Annotated[str, Field(description="HMAC-SHA256 signed content retrieval URL")]
    expires_in: Annotated[int, Field(default=300, description="TTL in seconds for signed URL")]
