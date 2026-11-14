# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""SQLAlchemy 2.0 ORM models for ai_provider_configs and ai_token_ledgers (KB-P5-05a)."""

from __future__ import annotations

import uuid  # noqa: TC003
from datetime import date, datetime  # noqa: TC003
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base


class AIProviderConfig(Base):
    """Configuration row for an LLM provider with envelope-encrypted API keys."""

    __tablename__ = "ai_provider_configs"
    __table_args__ = (
        CheckConstraint(
            "provider_kind IN ('openai','ollama','gemini','fixture')",
            name="ck_ai_provider_configs_provider_kind",
        ),
        CheckConstraint(
            "char_length(display_name) BETWEEN 1 AND 80",
            name="ck_ai_provider_configs_display_name_len",
        ),
        CheckConstraint(
            "cardinality(model_allowlist) BETWEEN 1 AND 32",
            name="ck_ai_provider_configs_model_allowlist_card",
        ),
        CheckConstraint(
            "residency_tier ~ '^[a-z0-9:._-]{1,64}$'",
            name="ck_ai_provider_configs_residency_tier",
        ),
        CheckConstraint(
            "(wrapped_api_key IS NULL) = (wrapped_dek IS NULL)",
            name="ck_ai_provider_configs_key_envelope",
        ),
        Index("idx_ai_provider_configs_ws_proj", "workspace_id", "project_id"),
        Index("idx_ai_provider_configs_ws_prio", "workspace_id", "priority"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    provider_kind: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_allowlist: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    residency_tier: Mapped[str] = mapped_column(String(64), nullable=False)
    priority: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("100"), default=100
    )
    settings_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    wrapped_api_key: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, deferred=True)
    api_key_nonce: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, deferred=True)
    wrapped_dek: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, deferred=True)
    dek_kid: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"), default=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class AITokenLedger(Base):
    """Daily or monthly token consumption and reservation ledger for an AI provider."""

    __tablename__ = "ai_token_ledgers"
    __table_args__ = (
        CheckConstraint(
            "period_kind IN ('daily','monthly')",
            name="ck_ai_token_ledgers_period_kind",
        ),
        CheckConstraint("token_cap >= 0", name="ck_ai_token_ledgers_token_cap_positive"),
        CheckConstraint(
            "tokens_reserved >= 0", name="ck_ai_token_ledgers_tokens_reserved_positive"
        ),
        CheckConstraint("tokens_used >= 0", name="ck_ai_token_ledgers_tokens_used_positive"),
        CheckConstraint(
            "tokens_used + tokens_reserved <= token_cap",
            name="ck_ai_token_ledgers_cap_bound",
        ),
        UniqueConstraint(
            "workspace_id",
            "project_id",
            "provider_config_id",
            "period_kind",
            "period_start",
            name="uq_ai_token_ledgers_period",
            postgresql_nulls_not_distinct=True,
        ),
        Index(
            "idx_ai_token_ledgers_lookup",
            "workspace_id",
            "provider_config_id",
            "period_kind",
            "period_start",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    provider_config_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_provider_configs.id", ondelete="CASCADE"), nullable=False
    )
    period_kind: Mapped[str] = mapped_column(Text, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    token_cap: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tokens_reserved: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0"), default=0
    )
    tokens_used: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0"), default=0
    )
