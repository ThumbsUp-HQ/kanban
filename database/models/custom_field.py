# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""SQLAlchemy 2.0 ORM models for custom field definitions and computed values (KB-P5-11)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base


class CustomFieldDefinition(Base):
    """Admin-defined custom field specification and execution parameters."""

    __tablename__ = "custom_field_definitions"
    __table_args__ = (
        UniqueConstraint("project_id", "slug", name="custom_field_definitions_project_id_slug_key"),
        CheckConstraint(
            "slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'", name="custom_field_definitions_slug_check"
        ),
        CheckConstraint(
            "char_length(btrim(name)) BETWEEN 1 AND 80", name="custom_field_definitions_name_check"
        ),
        CheckConstraint("tier IN ('wasm', 'nsjail')", name="custom_field_definitions_tier_check"),
        CheckConstraint(
            "output_format IN ("
            "'text', 'number', 'badge', 'markdown_snippet', 'url', 'json_table', 'severity_pill'"
            ")",
            name="custom_field_definitions_output_format_check",
        ),
        CheckConstraint(
            "jsonb_typeof(output_format_metadata) = 'object' "
            "AND octet_length(output_format_metadata::text) <= 16384",
            name="custom_field_definitions_output_format_metadata_check",
        ),
        CheckConstraint(
            "octet_length(script_source) BETWEEN 1 AND 131072",
            name="custom_field_definitions_script_source_check",
        ),
        CheckConstraint(
            "wasm_module_sha256 IS NULL OR octet_length(wasm_module_sha256) = 32",
            name="custom_field_definitions_wasm_module_sha256_check",
        ),
        CheckConstraint(
            "script_version >= 1", name="custom_field_definitions_script_version_check"
        ),
        CheckConstraint(
            "target_scope IN ('PROJECT', 'WORKSPACE', 'SERVER')",
            name="custom_field_definitions_target_scope_check",
        ),
        CheckConstraint(
            "credential_mode IN ('INVOKING_USER', 'PROJECT_ADMIN_SP', 'SERVER_ADMIN_SP')",
            name="custom_field_definitions_credential_mode_check",
        ),
        CheckConstraint(
            "cardinality(egress_allowlist) <= 16",
            name="custom_field_definitions_egress_allowlist_check",
        ),
        CheckConstraint(
            "octet_length(manifest_sha256) = 32",
            name="custom_field_definitions_manifest_sha256_check",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    slug: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    tier: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'wasm'"))
    output_format: Mapped[str] = mapped_column(String, nullable=False)
    output_format_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    script_source: Mapped[str] = mapped_column(String, nullable=False)
    wasm_module_sha256: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    script_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    target_scope: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'PROJECT'")
    )
    credential_mode: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'INVOKING_USER'")
    )
    egress_allowlist: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default=text("'{}'::text[]")
    )
    manifest_sha256: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("principals.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class CustomFieldValue(Base):
    """Cached computed custom field output partitioned by caller access hash."""

    __tablename__ = "custom_field_values"
    __table_args__ = (
        UniqueConstraint(
            "issue_id",
            "field_id",
            "script_version",
            "user_access_hash",
            name="custom_field_values_unique_key",
        ),
        CheckConstraint(
            "octet_length(user_access_hash) IN (0, 32)",
            name="custom_field_values_user_access_hash_check",
        ),
        CheckConstraint(
            "octet_length(value_json::text) <= 65536",
            name="custom_field_values_value_json_check",
        ),
        CheckConstraint("last_latency_ms >= 0", name="custom_field_values_last_latency_ms_check"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    issue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("issues.id", ondelete="CASCADE"), nullable=False
    )
    field_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("custom_field_definitions.id", ondelete="CASCADE"), nullable=False
    )
    script_version: Mapped[int] = mapped_column(Integer, nullable=False)
    user_access_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    value_json: Mapped[Any] = mapped_column(JSONB, nullable=False)
    last_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
