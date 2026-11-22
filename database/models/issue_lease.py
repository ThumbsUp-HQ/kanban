# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""SQLAlchemy 2.0 ORM model for issue claim leases (KB-CONCURRENCY-01, KAN-69)."""

from __future__ import annotations

import uuid  # noqa: TC003
from datetime import datetime  # noqa: TC003

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base


class IssueLease(Base):
    """Exclusive, heartbeated claim lease on an issue held by a worker or principal."""

    __tablename__ = "issue_leases"
    __table_args__ = (UniqueConstraint("issue_id", name="uq_issue_leases_issue_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    issue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("issues.id", ondelete="CASCADE"), nullable=False
    )
    principal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("principals.id", ondelete="CASCADE"), nullable=False
    )
    fencing_token: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
