"""SQLAlchemy 2.0 ORM model for agent_definitions (KB-P5-16, S14.2)."""

import uuid
from typing import Any

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base


class AgentDefinition(Base):
    """Unified registry for agent execution definitions across all 3 harnesses."""

    __tablename__ = "agent_definitions"
    __table_args__ = (
        UniqueConstraint("workspace_id", "slug", name="agent_definitions_workspace_id_slug_key"),
        CheckConstraint(
            "timeout_ms BETWEEN 1000 AND 600000",
            name="chk_agent_definitions_timeout_ms",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    principal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("principals.id", ondelete="RESTRICT"), nullable=False
    )
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    harness_kind: Mapped[str] = mapped_column(Text, nullable=False)
    provider_kind: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    cli_binary_allowlist_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    cli_args_json: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    remote_runner_pool_slug: Mapped[str | None] = mapped_column(Text, nullable=True)
    repo_access_mode: Mapped[str] = mapped_column(
        Text, nullable=False, default="none", server_default=text("'none'")
    )
    mcp_allowed_tools: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        default=lambda: ["search_tickets", "read_ticket", "search_knowledge", "read_doc"],
        server_default=text(
            "ARRAY['search_tickets','read_ticket','search_knowledge','read_doc']::text[]"
        ),
    )
    system_instructions_md: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=text("''")
    )
    timeout_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60000, server_default=text("60000")
    )
