"""Activity ledger models: activity_chain_heads, activity_records."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    LargeBinary,
    SmallInteger,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base, ObjectKind, object_kind_pg_enum


class ActivityChainHead(Base):
    """Cryptographic hash chain tip tracking last sequence and hash per workspace."""

    __tablename__ = "activity_chain_heads"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), primary_key=True
    )
    last_seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class ActivityRecord(Base):
    """Immutable, append-only partitioned activity audit record."""

    __tablename__ = "activity_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    chain_seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    object_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    object_type: Mapped[ObjectKind | None] = mapped_column(object_kind_pg_enum, nullable=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("principals.id", ondelete="RESTRICT"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'")
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, server_default=text("clock_timestamp()")
    )
    prev_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    row_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encryption_ver: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0")
    )
    payload_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    payload_nonce: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    payload_aad_sha256: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
