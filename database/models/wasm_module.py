# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""SQLAlchemy 2.0 ORM model for approved_wasm_modules (KB-P5-13)."""

from __future__ import annotations

import uuid  # noqa: TC003
from datetime import datetime  # noqa: TC003

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base


class ApprovedWasmModule(Base):
    """Approved WebAssembly module artifact for sandboxed custom fields and sync hooks."""

    __tablename__ = "approved_wasm_modules"
    __table_args__ = (
        CheckConstraint(
            "octet_length(sha256) = 32",
            name="ck_approved_wasm_modules_sha256_len",
        ),
        CheckConstraint(
            "char_length(btrim(name)) BETWEEN 1 AND 120",
            name="ck_approved_wasm_modules_name_len",
        ),
        CheckConstraint(
            "octet_length(wasm_bytes) BETWEEN 8 AND 1048576",
            name="ck_approved_wasm_modules_bytes_len",
        ),
        UniqueConstraint("workspace_id", "sha256", name="uq_approved_wasm_modules_ws_sha256"),
        Index("idx_approved_wasm_modules_lookup", "workspace_id", "sha256"),
        Index("idx_approved_wasm_modules_project", "project_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    sha256: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    wasm_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    approved_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("principals.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )
