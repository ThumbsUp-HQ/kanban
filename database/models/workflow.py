# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""SQLAlchemy 2.0 ORM models for workflow transition hooks, executions, and invocations.

KB-P5-17a, S14.1, S14.2.
"""

from __future__ import annotations

import uuid  # noqa: TC003
from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base


class WorkflowTransitionHook(Base):
    """Workflow transition hook definition (sync validator/mutator or async agent gate)."""

    __tablename__ = "workflow_transition_hooks"
    __table_args__ = (
        CheckConstraint(
            "(hook_kind IN ('sync_validator', 'sync_mutator') "
            "AND wasm_module_sha256 IS NOT NULL AND agent_definition_id IS NULL) "
            "OR (hook_kind = 'agent_interceptor' "
            "AND agent_definition_id IS NOT NULL AND wasm_module_sha256 IS NULL)",
            name="ck_workflow_transition_hooks_kind",
        ),
        CheckConstraint(
            "octet_length(manifest_sha256) = 32",
            name="ck_workflow_transition_hooks_manifest_sha256",
        ),
        CheckConstraint(
            "wasm_module_sha256 IS NULL OR octet_length(wasm_module_sha256) = 32",
            name="ck_workflow_transition_hooks_wasm_sha256",
        ),
        CheckConstraint(
            "max_rework_attempts BETWEEN 1 AND 20",
            name="ck_workflow_transition_hooks_max_rework",
        ),
        Index(
            "wth_lookup",
            "project_id",
            "to_state_id",
            "sort_rank",
            postgresql_where=text("is_enabled"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    from_state_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workflow_states.id", ondelete="CASCADE"), nullable=True
    )
    to_state_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_states.id", ondelete="CASCADE"), nullable=False
    )
    hook_kind: Mapped[str] = mapped_column(Text, nullable=False)
    sort_rank: Mapped[str] = mapped_column(Text, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("TRUE")
    )
    wasm_module_sha256: Mapped[bytes | None] = mapped_column(LargeBinary(32), nullable=True)
    agent_definition_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_definitions.id", ondelete="RESTRICT"), nullable=True
    )
    allowed_mutable_fields: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'")
    )
    failure_policy: Mapped[str] = mapped_column(
        Text, nullable=False, default="fail_closed", server_default=text("'fail_closed'")
    )
    manifest_sha256: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    max_rework_attempts: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=3, server_default=text("3")
    )


class WorkflowTransitionExecution(Base):
    """Workflow transition execution record tracking synchronous and asynchronous gates."""

    __tablename__ = "workflow_transition_executions"
    __table_args__ = (
        CheckConstraint(
            "status IN ("
            "'running_sync','pending_async','approved','rejected','cancelled','timed_out'"
            ")",
            name="ck_workflow_transition_executions_status",
        ),
        CheckConstraint("hop_depth <= 3", name="ck_workflow_transition_executions_hop_depth"),
        CheckConstraint(
            "octet_length(issue_body_sha256_snapshot) = 32",
            name="ck_workflow_transition_executions_snapshot",
        ),
        Index(
            "wte_one_pending",
            "issue_id",
            unique=True,
            postgresql_where=text("status IN ('running_sync','pending_async')"),
        ),
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
    invoking_principal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("principals.id"), nullable=False
    )
    from_state_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_states.id"), nullable=False
    )
    to_state_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_states.id"), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    hop_depth: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default=text("0")
    )
    issue_body_sha256_snapshot: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    verdict_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WorkflowHookInvocation(Base):
    """Invocation telemetry and outcome of a hook within an execution."""

    __tablename__ = "workflow_hook_invocations"
    __table_args__ = (
        CheckConstraint(
            "hook_kind IN ('sync_validator','sync_mutator','agent_interceptor')",
            name="ck_workflow_hook_invocations_kind",
        ),
        CheckConstraint(
            "status IN ('running','allowed','rejected','mutated','error','timed_out','skipped')",
            name="ck_workflow_hook_invocations_status",
        ),
        CheckConstraint("duration_us >= 0", name="ck_workflow_hook_invocations_duration"),
        CheckConstraint(
            "output_json IS NULL OR octet_length(output_json::text) <= 65536",
            name="ck_workflow_hook_invocations_output_json",
        ),
        UniqueConstraint("execution_id", "hook_id", name="uq_workflow_hook_invocations_exec_hook"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_transition_executions.id", ondelete="CASCADE"), nullable=False
    )
    hook_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_transition_hooks.id", ondelete="RESTRICT"), nullable=False
    )
    hook_kind: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    duration_us: Mapped[int | None] = mapped_column(Integer, nullable=True)
    claimed_by_worker: Mapped[str | None] = mapped_column(Text, nullable=True)
    claim_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def deadline_at(self) -> datetime | None:
        """Computed or stored deadline timestamp."""
        if hasattr(self, "_deadline_at") and self._deadline_at is not None:
            return self._deadline_at
        if self.output_json and "deadline_at" in self.output_json:
            val = self.output_json["deadline_at"]
            if isinstance(val, str):
                return datetime.fromisoformat(val)
            if isinstance(val, datetime):
                return val
        return None

    @deadline_at.setter
    def deadline_at(self, value: datetime | None) -> None:
        self._deadline_at = value
