# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""SQLAlchemy 2.0 ORM model for custom field escalation approvals (KB-P5-12)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    LargeBinary,
    SmallInteger,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base


class CustomFieldApproval(Base):
    """Cryptographic manifest escalation approval and dual-control audit record."""

    __tablename__ = "custom_field_approvals"
    __table_args__ = (
        CheckConstraint(
            "octet_length(manifest_sha256) = 32",
            name="custom_field_approvals_manifest_sha256_check",
        ),
        CheckConstraint(
            "target_scope IN ('PROJECT', 'WORKSPACE', 'SERVER')",
            name="custom_field_approvals_target_scope_check",
        ),
        CheckConstraint(
            "credential_mode IN ('INVOKING_USER', 'PROJECT_ADMIN_SP', 'SERVER_ADMIN_SP')",
            name="custom_field_approvals_credential_mode_check",
        ),
        CheckConstraint(
            "required_tier IN ('PROJECT_ADMIN', 'WORKSPACE_ADMIN', 'SERVER_ADMIN_DUAL')",
            name="custom_field_approvals_required_tier_check",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'PENDING_SECOND_APPROVER', 'APPROVED', 'REVOKED')",
            name="custom_field_approvals_status_check",
        ),
        CheckConstraint(
            "char_length(btrim(justification)) BETWEEN 10 AND 2000",
            name="custom_field_approvals_justification_check",
        ),
        CheckConstraint(
            "primary_approver_aal IS NULL OR primary_approver_aal >= 2",
            name="custom_field_approvals_primary_approver_aal_check",
        ),
        CheckConstraint(
            "secondary_approver_aal IS NULL OR secondary_approver_aal >= 2",
            name="custom_field_approvals_secondary_approver_aal_check",
        ),
        CheckConstraint(
            "approval_signature_hmac IS NULL OR octet_length(approval_signature_hmac) = 32",
            name="custom_field_approvals_approval_signature_hmac_check",
        ),
        CheckConstraint(
            "secondary_approver_id IS NULL OR secondary_approver_id <> primary_approver_id",
            name="custom_field_approvals_dual_approver_distinct_check",
        ),
        CheckConstraint(
            "(target_scope = 'PROJECT' AND credential_mode "
            "IN ('INVOKING_USER', 'PROJECT_ADMIN_SP')) OR "
            "(target_scope = 'WORKSPACE' AND credential_mode "
            "IN ('INVOKING_USER', 'PROJECT_ADMIN_SP')) OR "
            "(target_scope = 'SERVER' AND credential_mode "
            "IN ('INVOKING_USER', 'SERVER_ADMIN_SP'))",
            name="custom_field_approvals_scope_principal_combo_check",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=text("uuidv7()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    field_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("custom_field_definitions.id", ondelete="CASCADE"), nullable=False
    )
    manifest_sha256: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    target_scope: Mapped[str] = mapped_column(String, nullable=False)
    credential_mode: Mapped[str] = mapped_column(String, nullable=False)
    required_tier: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="PENDING")
    requested_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("principals.id"), nullable=False)
    justification: Mapped[str] = mapped_column(String, nullable=False)
    primary_approver_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("principals.id"), nullable=True
    )
    primary_approver_aal: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    primary_approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    secondary_approver_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("principals.id"), nullable=True
    )
    secondary_approver_aal: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    secondary_approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sp_warning_acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approval_signature_hmac: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
