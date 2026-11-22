# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Wrapped encryption key model for activity records (KB-SEC-SHRED-01)."""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    LargeBinary,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base


class ActivityRecordKey(Base):
    """Wrapped encryption keys for activity records supporting GDPR/HIPAA crypto-shredding."""

    __tablename__ = "activity_record_keys"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    activity_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    object_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    wrapped_dek: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    dek_nonce: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    dek_kid: Mapped[str] = mapped_column(String, nullable=False)
    shredded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    shredded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("principals.id", ondelete="SET NULL"), nullable=True
    )
    shred_reason: Mapped[str | None] = mapped_column(String, nullable=True)
