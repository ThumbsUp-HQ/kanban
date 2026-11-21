# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Async AI/CLI agent transition gate state machine and coordinator (KB-P5-18, S14.1-14.3)."""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
import uuid
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import select, text

from database.models.agent_definition import AgentDefinition
from database.models.issues import Issue, IssueComment, IssueLabel
from database.models.principals import Principal
from database.models.projects import Project, ProjectLabel, WorkflowState
from database.models.spine import ObjectLink
from database.models.workflow import (
    WorkflowHookInvocation,
    WorkflowTransitionExecution,
    WorkflowTransitionHook,
)
from database.outbox.broker import enqueue_outbox_event
from kanban.api.problems import ProblemException, not_found
from kanban.content.normalize import normalize_to_markdown
from kanban.security.permissions import Capability, evaluate_capabilities
from kanban.security.scrubber import scrub_text
from kanban.services.activity import ActivityEventType, record_activity
from kanban.workflows.engine import TransitionOutcome
from kanban.workflows.gate_types import GateDecision, GateEventType, LinkSpec
from kanban.workflows.mutations import apply_field_updates, validate_field_updates

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext

logger = logging.getLogger(__name__)

MAX_VETO_COMMENT_BYTES: Final[int] = 16384
MAX_APPROVE_COMMENT_BYTES: Final[int] = 65536
MAX_REASON_PREVIEW_CHARS: Final[int] = 280


def compute_harness_label(agent_def: AgentDefinition | None) -> str:
    """Compute human-facing harness label for display and event payloads."""
    if agent_def is None:
        return "in_app_sdk"
    if agent_def.harness_kind == "cli_pipe":
        bin_id = agent_def.cli_binary_allowlist_id or "cli"
        if bin_id in ("agy", "codex"):
            return f"cli: {bin_id} -p"
        return f"cli: {bin_id}"
    if agent_def.harness_kind == "in_app_sdk":
        return agent_def.provider_kind or "sdk"
    if agent_def.harness_kind == "remote_runner":
        return f"remote: {agent_def.remote_runner_pool_slug or 'runner'}"
    return agent_def.harness_kind


def format_reason_preview(reason_markdown: str) -> str:
    """Format scrubbed 2-line <= 280-char reason preview for outbox events."""
    scrubbed = scrub_text(reason_markdown)
    lines = [line.strip() for line in scrubbed.splitlines() if line.strip()]
    first_two = " ".join(lines[:2])
    return first_two[:MAX_REASON_PREVIEW_CHARS]


def format_veto_comment(
    hook_name: str,
    harness_label: str,
    from_state_name: str,
    to_state_name: str,
    reason_markdown: str,
) -> str:
    """Format normalized, scrubbed veto comment capped at 16,384 bytes."""
    header = (
        f"🛑🤖 Gate `{hook_name}` ({harness_label}) vetoed {from_state_name} -> {to_state_name}"
    )
    normalized = normalize_to_markdown(reason_markdown)
    scrubbed = scrub_text(normalized)
    capped = scrubbed[:MAX_VETO_COMMENT_BYTES]
    return f"{header}\n\n{capped}"


def format_approve_comment(
    hook_name: str,
    harness_label: str,
    from_state_name: str,
    to_state_name: str,
    reason_markdown: str,
) -> str:
    """Format normalized, scrubbed approve comment capped at 65,536 bytes."""
    header = (
        f"## ✅🤖 Workflow Transition Gate Approved\n\n"
        f"- **Hook:** `{hook_name}`\n"
        f"- **Harness:** `{harness_label}`\n"
        f"- **Transition:** `{from_state_name}` -> `{to_state_name}`\n\n"
        f"### Reality Check / Gate Rationale"
    )
    normalized = normalize_to_markdown(reason_markdown)
    scrubbed = scrub_text(normalized)
    capped = scrubbed[:MAX_APPROVE_COMMENT_BYTES]
    return f"{header}\n\n{capped}"


class AgentGateDispatcher:
    """Dispatches asynchronous AI/CLI agent transition helpers (KB-P5-18)."""

    async def dispatch(
        self,
        session: AsyncSession,
        execution: WorkflowTransitionExecution,
        hooks: Sequence[WorkflowTransitionHook],
        caller: PrincipalContext,
    ) -> TransitionOutcome:
        """Dispatch async agent gate hold, returning HTTP 202 TransitionOutcome."""
        del caller
        now = dt.datetime.now(dt.UTC)

        # 1. Put execution in pending_async status
        execution.status = "pending_async"

        # 2. Lock and set hold on issue
        issue = await session.get(Issue, execution.issue_id, with_for_update=True)
        if issue is None:  # pragma: no cover
            not_found()
        issue.pending_transition_exec_id = execution.id

        # 3. Order agent hooks by sort_rank COLLATE "C", id
        agent_hooks = sorted(
            [h for h in hooks if h.hook_kind == "agent_interceptor"],
            key=lambda h: (h.sort_rank, str(h.id)),
        )
        if not agent_hooks:  # pragma: no cover
            msg = "No agent_interceptor hooks provided to AgentGateDispatcher"
            raise ValueError(msg)

        first_hook = agent_hooks[0]

        # 4. Resolve agent definition & compute deadline
        agent_def = (
            await session.get(AgentDefinition, first_hook.agent_definition_id)
            if first_hook.agent_definition_id
            else None
        )
        timeout_ms = agent_def.timeout_ms if agent_def else 60000
        deadline_at = now + dt.timedelta(milliseconds=timeout_ms)

        # 5. Insert workflow_hook_invocations row status='running' for FIRST hook only
        inv = WorkflowHookInvocation(
            id=uuid.uuid7() if hasattr(uuid, "uuid7") else uuid.uuid4(),
            workspace_id=execution.workspace_id,
            execution_id=execution.id,
            hook_id=first_hook.id,
            hook_kind="agent_interceptor",
            status="running",
            started_at=now,
        )
        session.add(inv)
        await session.flush()

        # 6. Resolve states, project, and issue key for event payloads
        from_state = await session.get(WorkflowState, execution.from_state_id)
        to_state = await session.get(WorkflowState, execution.to_state_id)
        project = await session.get(Project, execution.project_id)
        issue_key = f"{project.identifier}-{issue.sequence_id}" if project else str(issue.id)

        agent_slug = agent_def.slug if agent_def else "agent"
        harness_kind = agent_def.harness_kind if agent_def else "in_app_sdk"
        harness_label = compute_harness_label(agent_def)

        # 7. Insert outbox events: workflow.gate.dispatch and workflow.gate.pending
        await enqueue_outbox_event(
            session=session,
            workspace_id=execution.workspace_id,
            project_id=execution.project_id,
            object_id=issue.id,
            topic=GateEventType.DISPATCH,
            payload={
                "execution_id": str(execution.id),
                "hook_id": str(first_hook.id),
                "agent_definition_id": str(first_hook.agent_definition_id),
                "deadline_at": deadline_at.isoformat(),
            },
        )

        await enqueue_outbox_event(
            session=session,
            workspace_id=execution.workspace_id,
            project_id=execution.project_id,
            object_id=issue.id,
            topic=GateEventType.PENDING,
            payload={
                "issue_id": str(issue.id),
                "issue_key": issue_key,
                "execution_id": str(execution.id),
                "hook_name": first_hook.name,
                "agent_slug": agent_slug,
                "harness_kind": harness_kind,
                "harness_label": harness_label,
                "from_state": from_state.name if from_state else "",
                "to_state": to_state.name if to_state else "",
                "started_at": now.isoformat(),
            },
        )

        # 8. Record GATE_PENDING activity
        await record_activity(
            session=session,
            workspace_id=execution.workspace_id,
            object_id=issue.id,
            actor_principal_id=execution.invoking_principal_id,
            event_type=ActivityEventType.GATE_PENDING,
            payload={
                "hook_name": first_hook.name,
                "harness_label": harness_label,
                "agent_slug": agent_slug,
            },
        )

        return TransitionOutcome(
            status_code=202,
            execution_id=execution.id,
            status="pending_agent_gate",
            state=from_state.name if from_state else "In Progress",
            from_state_id=execution.from_state_id,
            to_state_id=execution.to_state_id,
            hook_name=first_hook.name,
            field_updates={
                "active_agent": agent_slug,
                "hook_name": first_hook.name,
                "harness_kind": harness_kind,
                "harness_label": harness_label,
                "deadline_at": deadline_at.isoformat(),
            },
        )


class GateCoordinator:
    """Coordinates verdicts, timeouts, failures, and cancellations for async agent gates."""

    def __init__(self, session: AsyncSession | None = None) -> None:
        """Initialize coordinator optionally bound to an active database session."""
        self.session = session
        if session is not None:
            self.record_failure = self._record_failure_instance  # type: ignore[assignment]

    async def _record_failure_instance(  # noqa: PLR0913
        self,
        execution_id: uuid.UUID | str | None = None,
        hook_id: uuid.UUID | str | None = None,
        code: str = "GATE_TIMEOUT",
        *,
        invocation_id: uuid.UUID | str | None = None,
        error_code: str | None = None,
        detail: str | None = None,
    ) -> WorkflowTransitionExecution:
        if self.session is None:
            msg = "session is required on GateCoordinator instance"
            raise ValueError(msg)
        return await GateCoordinator.record_failure(
            self.session,
            execution_id=execution_id,
            hook_id=hook_id,
            code=code,
            invocation_id=invocation_id,
            error_code=error_code,
            detail=detail,
        )

    @classmethod
    async def record_decision(  # noqa: C901, PLR0911, PLR0912, PLR0915
        cls,
        session: AsyncSession,
        execution_id: uuid.UUID | str,
        hook_id: uuid.UUID | str,
        decision: GateDecision,
    ) -> WorkflowTransitionExecution:
        """Record an agent gate decision within an atomic transaction."""
        exec_uuid = uuid.UUID(str(execution_id))
        hook_uuid = uuid.UUID(str(hook_id))
        now = dt.datetime.now(dt.UTC)

        # 1. Lock execution and running invocation
        exec_stmt = (
            select(WorkflowTransitionExecution)
            .where(WorkflowTransitionExecution.id == exec_uuid)
            .with_for_update()
        )
        execution = (await session.execute(exec_stmt)).scalar_one_or_none()
        if execution is None:
            raise ProblemException(
                code="EXECUTION_NOT_FOUND",
                status=404,
                title="Execution Not Found",
                detail="Workflow transition execution not found",
            )

        inv_stmt = (
            select(WorkflowHookInvocation)
            .where(
                WorkflowHookInvocation.execution_id == exec_uuid,
                WorkflowHookInvocation.hook_id == hook_uuid,
            )
            .with_for_update()
        )
        invocation = (await session.execute(inv_stmt)).scalar_one_or_none()

        verdict_hex = decision.verdict_sha256.hex() if decision.verdict_sha256 else ""

        # Check for out-of-order or duplicate identical decision
        if (
            execution.status != "pending_async"
            or invocation is None
            or invocation.status != "running"
        ):
            if (
                invocation is not None
                and invocation.output_json
                and invocation.output_json.get("verdict_sha256") == verdict_hex
            ):
                return execution
            if (
                execution.verdict_json
                and execution.verdict_json.get("verdict_sha256") == verdict_hex
            ):
                return execution
            raise ProblemException(
                code="GATE_DECISION_OUT_OF_ORDER",
                status=409,
                title="Gate Decision Out Of Order",
                detail="Invocation is not currently running or execution is not pending_async",
            )

        # 2. Lock issue and resolve metadata
        issue_stmt = select(Issue).where(Issue.id == execution.issue_id).with_for_update()
        issue = (await session.execute(issue_stmt)).scalar_one_or_none()
        if issue is None:  # pragma: no cover
            not_found()

        hook = await session.get(WorkflowTransitionHook, hook_uuid)
        if hook is None:  # pragma: no cover
            not_found()

        agent_def = (
            await session.get(AgentDefinition, hook.agent_definition_id)
            if hook.agent_definition_id
            else None
        )
        from_state = await session.get(WorkflowState, execution.from_state_id)
        to_state = await session.get(WorkflowState, execution.to_state_id)
        project = await session.get(Project, execution.project_id)

        issue_key = f"{project.identifier}-{issue.sequence_id}" if project else str(issue.id)
        from_name = from_state.name if from_state else "Unknown"
        to_name = to_state.name if to_state else "Unknown"
        agent_slug = agent_def.slug if agent_def else "agent"
        harness_kind = agent_def.harness_kind if agent_def else "in_app_sdk"
        harness_label = compute_harness_label(agent_def)

        # 3. Validate decision.field_updates against hook.allowed_mutable_fields
        if decision.field_updates:
            try:
                validate_field_updates(hook.allowed_mutable_fields, dict(decision.field_updates))
            except ProblemException:
                if hook.failure_policy == "fail_open_warn":
                    inv_actor = (
                        agent_def.principal_id if agent_def else execution.invoking_principal_id
                    )
                    await record_activity(
                        session=session,
                        workspace_id=execution.workspace_id,
                        object_id=issue.id,
                        actor_principal_id=inv_actor,
                        event_type=ActivityEventType.HOOK_FAIL_OPEN_WARN,
                        payload={"hook_name": hook.name, "error": "HOOK_MUTATION_NOT_ALLOWED"},
                    )
                    decision = GateDecision(
                        decision=decision.decision,
                        reason_markdown=decision.reason_markdown,
                        field_updates={},
                        add_labels=decision.add_labels,
                        add_links=decision.add_links,
                        verdict_sha256=decision.verdict_sha256,
                        latency_ms=decision.latency_ms,
                    )
                else:
                    return await cls.record_failure(
                        session, execution.id, hook.id, "HOOK_MUTATION_NOT_ALLOWED"
                    )

        # 4. Handle REJECT verdict
        if decision.decision == "reject":
            duration_us = int(decision.latency_ms * 1000)
            reason_preview = format_reason_preview(decision.reason_markdown)

            invocation.status = "rejected"
            invocation.duration_us = duration_us
            invocation.completed_at = now
            invocation.output_json = {
                "decision": "reject",
                "reason": decision.reason_markdown,
                "verdict_sha256": verdict_hex,
                "cited_files": list(decision.cited_files),
            }

            execution.status = "rejected"
            execution.verdict_json = {
                "decision": "reject",
                "hook_name": hook.name,
                "reason": decision.reason_markdown,
                "verdict_sha256": verdict_hex,
                "latency_ms": decision.latency_ms,
                "cited_files": list(decision.cited_files),
            }
            execution.completed_at = now

            # Clear hold
            issue.pending_transition_exec_id = None

            # Post veto comment authored by agent principal
            if agent_def is not None:
                veto_body = format_veto_comment(
                    hook.name, harness_label, from_name, to_name, decision.reason_markdown
                )
                comment = IssueComment(
                    id=uuid.uuid7() if hasattr(uuid, "uuid7") else uuid.uuid4(),
                    workspace_id=issue.workspace_id,
                    issue_id=issue.id,
                    author_id=agent_def.principal_id,
                    body_markdown=veto_body,
                )
                session.add(comment)

            # Record GATE_REJECTED activity
            await record_activity(
                session=session,
                workspace_id=execution.workspace_id,
                object_id=issue.id,
                actor_principal_id=(
                    agent_def.principal_id if agent_def else execution.invoking_principal_id
                ),
                event_type=ActivityEventType.GATE_REJECTED,
                payload={
                    "hook_name": hook.name,
                    "harness_label": harness_label,
                    "verdict_sha256": verdict_hex,
                    "latency_ms": decision.latency_ms,
                    "reason_preview": reason_preview,
                },
            )

            # Emit workflow.gate.rejected outbox event
            await enqueue_outbox_event(
                session=session,
                workspace_id=execution.workspace_id,
                project_id=execution.project_id,
                object_id=issue.id,
                topic=GateEventType.REJECTED,
                payload={
                    "issue_id": str(issue.id),
                    "issue_key": issue_key,
                    "execution_id": str(execution.id),
                    "hook_name": hook.name,
                    "agent_slug": agent_slug,
                    "harness_kind": harness_kind,
                    "harness_label": harness_label,
                    "from_state": from_name,
                    "to_state": to_name,
                    "started_at": execution.created_at.isoformat(),
                    "completed_at": now.isoformat(),
                    "latency_ms": decision.latency_ms,
                    "verdict_sha256": verdict_hex,
                    "reason_preview": reason_preview,
                },
            )

            await session.flush()
            return execution

        # 5. Handle APPROVE verdict
        # Check if more agent hooks exist sequentially
        remaining_stmt = (
            select(WorkflowTransitionHook)
            .where(
                WorkflowTransitionHook.project_id == execution.project_id,
                WorkflowTransitionHook.to_state_id == execution.to_state_id,
                WorkflowTransitionHook.is_enabled.is_(True),
                WorkflowTransitionHook.hook_kind == "agent_interceptor",
            )
            .order_by(WorkflowTransitionHook.sort_rank.collate("C"), WorkflowTransitionHook.id)
        )
        all_agent_hooks = list((await session.execute(remaining_stmt)).scalars().all())
        current_rank = hook.sort_rank
        current_id_str = str(hook.id)

        next_hooks = [
            h for h in all_agent_hooks if (h.sort_rank, str(h.id)) > (current_rank, current_id_str)
        ]

        if next_hooks:
            # More agent hooks remain: mark current allowed and open next invocation
            duration_us = int(decision.latency_ms * 1000)
            invocation.status = "allowed"
            invocation.duration_us = duration_us
            invocation.completed_at = now
            invocation.output_json = {
                "decision": "approve",
                "field_updates": dict(decision.field_updates),
                "verdict_sha256": verdict_hex,
            }

            next_hook = next_hooks[0]
            next_agent_def = (
                await session.get(AgentDefinition, next_hook.agent_definition_id)
                if next_hook.agent_definition_id
                else None
            )
            next_timeout = next_agent_def.timeout_ms if next_agent_def else 60000
            next_deadline = now + dt.timedelta(milliseconds=next_timeout)

            next_inv = WorkflowHookInvocation(
                id=uuid.uuid7() if hasattr(uuid, "uuid7") else uuid.uuid4(),
                workspace_id=execution.workspace_id,
                execution_id=execution.id,
                hook_id=next_hook.id,
                hook_kind="agent_interceptor",
                status="running",
                started_at=now,
            )
            session.add(next_inv)
            await session.flush()

            await enqueue_outbox_event(
                session=session,
                workspace_id=execution.workspace_id,
                project_id=execution.project_id,
                object_id=issue.id,
                topic=GateEventType.DISPATCH,
                payload={
                    "execution_id": str(execution.id),
                    "hook_id": str(next_hook.id),
                    "agent_definition_id": str(next_hook.agent_definition_id),
                    "deadline_at": next_deadline.isoformat(),
                },
            )
            return execution

        # 6. Last agent hook approved: check TOCTOU invariants
        current_desc_bytes = (issue.description_markdown or "").encode("utf-8")
        current_desc_sha256 = (
            issue.description_sha256 or hashlib.sha256(current_desc_bytes).digest()
        )

        if (
            current_desc_sha256 != execution.issue_body_sha256_snapshot
            or issue.state_id != execution.from_state_id
        ):
            # TOCTOU MISMATCH: STALE SNAPSHOT!
            duration_us = int(decision.latency_ms * 1000)
            invocation.status = "error"
            invocation.error_code = "STALE_SNAPSHOT"
            invocation.duration_us = duration_us
            invocation.completed_at = now

            execution.status = "cancelled"
            execution.verdict_json = {
                "decision": "cancelled",
                "reason": "Issue modified concurrently (stale snapshot)",
                "verdict_sha256": verdict_hex,
            }
            execution.completed_at = now

            # Clear hold
            issue.pending_transition_exec_id = None

            # Record GATE_ABORTED_STALE activity
            await record_activity(
                session=session,
                workspace_id=execution.workspace_id,
                object_id=issue.id,
                actor_principal_id=execution.invoking_principal_id,
                event_type=ActivityEventType.GATE_ABORTED_STALE,
                payload={"hook_name": hook.name, "reason": "STALE_SNAPSHOT"},
            )

            # Emit workflow.gate.cancelled outbox event
            await enqueue_outbox_event(
                session=session,
                workspace_id=execution.workspace_id,
                project_id=execution.project_id,
                object_id=issue.id,
                topic=GateEventType.CANCELLED,
                payload={
                    "issue_id": str(issue.id),
                    "issue_key": issue_key,
                    "execution_id": str(execution.id),
                    "hook_name": hook.name,
                    "agent_slug": agent_slug,
                    "harness_kind": harness_kind,
                    "harness_label": harness_label,
                    "from_state": from_name,
                    "to_state": to_name,
                    "started_at": execution.created_at.isoformat(),
                    "completed_at": now.isoformat(),
                    "reason_preview": "STALE_SNAPSHOT: Issue modified concurrently",
                },
            )

            await session.flush()
            return execution

        # 7. TOCTOU verified: COMMIT TRANSITION!
        duration_us = int(decision.latency_ms * 1000)
        bounded_reason = (decision.reason_markdown or "")[:16384]
        reason_preview = format_reason_preview(decision.reason_markdown or "")
        invocation.status = "allowed"
        invocation.duration_us = duration_us
        invocation.completed_at = now
        invocation.output_json = {
            "decision": "approve",
            "field_updates": dict(decision.field_updates),
            "verdict_sha256": verdict_hex,
            "reason": bounded_reason,
            "reason_preview": reason_preview,
        }

        # Apply accumulated field updates across all hook invocations
        inv_list_stmt = (
            select(WorkflowHookInvocation)
            .where(WorkflowHookInvocation.execution_id == execution.id)
            .order_by(WorkflowHookInvocation.started_at)
        )
        inv_rows = (await session.execute(inv_list_stmt)).scalars().all()
        accumulated_updates: dict[str, Any] = {}
        for r in inv_rows:
            if r.output_json and isinstance(r.output_json.get("field_updates"), dict):
                accumulated_updates.update(r.output_json["field_updates"])
        if decision.field_updates:
            accumulated_updates.update(decision.field_updates)

        invoking_principal = await session.get(Principal, execution.invoking_principal_id)
        if accumulated_updates and invoking_principal:
            from kanban.api.deps import PrincipalContext  # noqa: PLC0415

            fake_caller = PrincipalContext(
                principal_id=execution.invoking_principal_id,
                workspace_id=execution.workspace_id,
            )
            await apply_field_updates(session, issue, accumulated_updates, fake_caller)

        # Apply add_labels
        if decision.add_labels:
            await cls._apply_labels(session, issue, decision.add_labels)

        # Apply add_links
        if decision.add_links:
            await cls._apply_links(
                session, issue, decision.add_links, execution.invoking_principal_id
            )

        # Set transaction-local execution ID for DB guard trigger and update state
        await session.execute(
            text("SELECT set_config('app.transition_exec_id', :val, true)"),
            {"val": str(execution.id)},
        )

        issue.state_id = execution.to_state_id
        issue.pending_transition_exec_id = None

        execution.status = "approved"
        execution.verdict_json = {
            "decision": "approve",
            "hook_name": hook.name,
            "verdict_sha256": verdict_hex,
            "latency_ms": decision.latency_ms,
            "cited_files": list(decision.cited_files),
            "reason": bounded_reason,
            "reason_preview": reason_preview,
        }
        execution.completed_at = now

        # Format and persist approval comment authored by agent principal
        approve_author_id = (
            agent_def.principal_id
            if agent_def and agent_def.principal_id is not None
            else execution.invoking_principal_id
        )
        approve_comment_body = format_approve_comment(
            hook.name,
            harness_label,
            from_name,
            to_name,
            decision.reason_markdown or "",
        )
        comment = IssueComment(
            id=uuid.uuid7() if hasattr(uuid, "uuid7") else uuid.uuid4(),
            workspace_id=issue.workspace_id,
            issue_id=issue.id,
            author_id=approve_author_id,
            body_markdown=approve_comment_body,
        )
        session.add(comment)
        await record_activity(
            session=session,
            workspace_id=execution.workspace_id,
            object_id=issue.id,
            actor_principal_id=approve_author_id,
            event_type=ActivityEventType.COMMENT_CREATED,
            payload={"comment_id": str(comment.id)},
        )

        # Record GATE_APPROVED and ISSUE_STATE_CHANGED activities
        await record_activity(
            session=session,
            workspace_id=execution.workspace_id,
            object_id=issue.id,
            actor_principal_id=(
                agent_def.principal_id if agent_def else execution.invoking_principal_id
            ),
            event_type=ActivityEventType.GATE_APPROVED,
            payload={
                "hook_name": hook.name,
                "harness_label": harness_label,
                "verdict_sha256": verdict_hex,
                "latency_ms": decision.latency_ms,
            },
        )

        await record_activity(
            session=session,
            workspace_id=execution.workspace_id,
            object_id=issue.id,
            actor_principal_id=execution.invoking_principal_id,
            event_type=ActivityEventType.ISSUE_STATE_CHANGED,
            payload={
                "from_state_id": str(execution.from_state_id),
                "to_state_id": str(execution.to_state_id),
                "from_state": from_name,
                "to_state": to_name,
                "transition_execution_id": str(execution.id),
            },
        )

        # Emit workflow.gate.approved outbox event
        await enqueue_outbox_event(
            session=session,
            workspace_id=execution.workspace_id,
            project_id=execution.project_id,
            object_id=issue.id,
            topic=GateEventType.APPROVED,
            payload={
                "issue_id": str(issue.id),
                "issue_key": issue_key,
                "execution_id": str(execution.id),
                "hook_name": hook.name,
                "agent_slug": agent_slug,
                "harness_kind": harness_kind,
                "harness_label": harness_label,
                "from_state": from_name,
                "to_state": to_name,
                "started_at": execution.created_at.isoformat(),
                "completed_at": now.isoformat(),
                "latency_ms": decision.latency_ms,
                "verdict_sha256": verdict_hex,
            },
        )

        await session.flush()
        return execution

    @classmethod
    async def record_failure(  # noqa: C901, PLR0912, PLR0913, PLR0915
        cls,
        session: AsyncSession | None = None,
        execution_id: uuid.UUID | str | None = None,
        hook_id: uuid.UUID | str | None = None,
        code: str = "GATE_TIMEOUT",
        *,
        invocation_id: uuid.UUID | str | None = None,
        error_code: str | None = None,
        detail: str | None = None,
    ) -> WorkflowTransitionExecution:
        """Record a gate timeout or error execution failure."""
        if session is None:
            msg = "session must be provided to record_failure"
            raise ValueError(msg)
        if invocation_id is not None and (execution_id is None or hook_id is None):
            inv_lookup = await session.get(WorkflowHookInvocation, uuid.UUID(str(invocation_id)))
            if inv_lookup is None:
                raise ProblemException(
                    code="INVOCATION_NOT_FOUND",
                    status=404,
                    title="Invocation Not Found",
                    detail="Hook invocation not found",
                )
            execution_id = inv_lookup.execution_id
            hook_id = inv_lookup.hook_id

        if execution_id is None or hook_id is None:
            msg = "execution_id and hook_id, or invocation_id must be provided"
            raise ValueError(msg)

        effective_code = error_code or code
        exec_uuid = uuid.UUID(str(execution_id))
        hook_uuid = uuid.UUID(str(hook_id))
        now = dt.datetime.now(dt.UTC)

        exec_stmt = (
            select(WorkflowTransitionExecution)
            .where(WorkflowTransitionExecution.id == exec_uuid)
            .with_for_update()
        )
        execution = (await session.execute(exec_stmt)).scalar_one_or_none()
        if execution is None:
            raise ProblemException(
                code="EXECUTION_NOT_FOUND",
                status=404,
                title="Execution Not Found",
                detail="Workflow transition execution not found",
            )

        inv_stmt = (
            select(WorkflowHookInvocation)
            .where(
                WorkflowHookInvocation.execution_id == exec_uuid,
                WorkflowHookInvocation.hook_id == hook_uuid,
            )
            .with_for_update()
        )
        invocation = (await session.execute(inv_stmt)).scalar_one_or_none()
        if invocation is None:
            raise ProblemException(
                code="INVOCATION_NOT_FOUND",
                status=404,
                title="Invocation Not Found",
                detail="Hook invocation not found",
            )

        issue_stmt = select(Issue).where(Issue.id == execution.issue_id).with_for_update()
        issue = (await session.execute(issue_stmt)).scalar_one_or_none()
        if issue is None:  # pragma: no cover
            not_found()

        hook = await session.get(WorkflowTransitionHook, hook_uuid)
        if hook is None:  # pragma: no cover
            not_found()

        agent_def = (
            await session.get(AgentDefinition, hook.agent_definition_id)
            if hook.agent_definition_id
            else None
        )
        from_state = await session.get(WorkflowState, execution.from_state_id)
        to_state = await session.get(WorkflowState, execution.to_state_id)
        project = await session.get(Project, execution.project_id)

        issue_key = f"{project.identifier}-{issue.sequence_id}" if project else str(issue.id)
        from_name = from_state.name if from_state else "Unknown"
        to_name = to_state.name if to_state else "Unknown"
        agent_slug = agent_def.slug if agent_def else "agent"
        harness_kind = agent_def.harness_kind if agent_def else "in_app_sdk"
        harness_label = compute_harness_label(agent_def)

        is_timeout = effective_code in {"TIMED_OUT", "GATE_TIMEOUT"}

        # Check failure_policy: fail_open_warn vs fail_closed (completed state MUST fail closed)
        is_completed_target = to_state is not None and to_state.state_group == "completed"
        if hook.failure_policy == "fail_open_warn" and not is_completed_target:
            inv_status = "timed_out" if is_timeout else "error"
            invocation.status = inv_status
            invocation.error_code = effective_code
            invocation.completed_at = now

            await record_activity(
                session=session,
                workspace_id=execution.workspace_id,
                object_id=issue.id,
                actor_principal_id=(
                    agent_def.principal_id if agent_def else execution.invoking_principal_id
                ),
                event_type=ActivityEventType.GATE_FAIL_OPEN_WARN,
                payload={"hook_name": hook.name, "error": effective_code},
            )

            # Check if more agent hooks exist sequentially
            remaining_stmt = (
                select(WorkflowTransitionHook)
                .where(
                    WorkflowTransitionHook.project_id == execution.project_id,
                    WorkflowTransitionHook.to_state_id == execution.to_state_id,
                    WorkflowTransitionHook.is_enabled.is_(True),
                    WorkflowTransitionHook.hook_kind == "agent_interceptor",
                )
                .order_by(WorkflowTransitionHook.sort_rank.collate("C"), WorkflowTransitionHook.id)
            )
            all_agent_hooks = list((await session.execute(remaining_stmt)).scalars().all())
            current_rank = hook.sort_rank
            current_id_str = str(hook.id)
            next_hooks = [
                h
                for h in all_agent_hooks
                if (h.sort_rank, str(h.id)) > (current_rank, current_id_str)
            ]

            if next_hooks:
                next_hook = next_hooks[0]
                next_agent_def = (
                    await session.get(AgentDefinition, next_hook.agent_definition_id)
                    if next_hook.agent_definition_id
                    else None
                )
                next_timeout = next_agent_def.timeout_ms if next_agent_def else 60000
                next_deadline = now + dt.timedelta(milliseconds=next_timeout)

                next_inv = WorkflowHookInvocation(
                    id=uuid.uuid7() if hasattr(uuid, "uuid7") else uuid.uuid4(),
                    workspace_id=execution.workspace_id,
                    execution_id=execution.id,
                    hook_id=next_hook.id,
                    hook_kind="agent_interceptor",
                    status="running",
                    started_at=now,
                )
                session.add(next_inv)
                await session.flush()

                await enqueue_outbox_event(
                    session=session,
                    workspace_id=execution.workspace_id,
                    project_id=execution.project_id,
                    object_id=issue.id,
                    topic=GateEventType.DISPATCH,
                    payload={
                        "execution_id": str(execution.id),
                        "hook_id": str(next_hook.id),
                        "agent_definition_id": str(next_hook.agent_definition_id),
                        "deadline_at": next_deadline.isoformat(),
                    },
                )
                return execution

            # Last hook with fail_open_warn -> check TOCTOU and commit
            current_desc_bytes = (issue.description_markdown or "").encode("utf-8")
            current_desc_sha256 = (
                issue.description_sha256 or hashlib.sha256(current_desc_bytes).digest()
            )

            if (
                current_desc_sha256 != execution.issue_body_sha256_snapshot
                or issue.state_id != execution.from_state_id
            ):
                execution.status = "cancelled"
                execution.completed_at = now
                issue.pending_transition_exec_id = None
                return execution

            await session.execute(
                text("SELECT set_config('app.transition_exec_id', :val, true)"),
                {"val": str(execution.id)},
            )
            issue.state_id = execution.to_state_id
            issue.pending_transition_exec_id = None
            execution.status = "approved"
            execution.verdict_json = {"decision": "approve", "fail_open_warn": effective_code}
            execution.completed_at = now
            await session.flush()
            return execution

        # Fail closed: reject/time out
        final_status = "timed_out" if is_timeout else "rejected"
        timeout_ms = agent_def.timeout_ms if agent_def else 60000
        if is_timeout:
            reason_text = detail or f"Gate timed out after {timeout_ms} ms"
        else:
            reason_text = detail or f"Gate failed: {effective_code}"

        invocation.status = final_status
        invocation.error_code = effective_code
        invocation.completed_at = now

        execution.status = final_status
        execution.verdict_json = {
            "decision": final_status,
            "hook_name": hook.name,
            "reason": reason_text,
            "code": effective_code,
        }
        execution.completed_at = now

        # Clear hold
        issue.pending_transition_exec_id = None
        if hasattr(issue, "pending_gate_invocation_id"):
            issue.pending_gate_invocation_id = None

        # Post veto comment authored by agent principal
        if agent_def is not None:
            header = f"🛑🤖 Gate `{hook.name}` ({harness_label}) vetoed {from_name} -> {to_name}"
            veto_comment_body = f"{header}\n\n{reason_text}"
            comment = IssueComment(
                id=uuid.uuid7() if hasattr(uuid, "uuid7") else uuid.uuid4(),
                workspace_id=issue.workspace_id,
                issue_id=issue.id,
                author_id=agent_def.principal_id,
                body_markdown=veto_comment_body,
            )
            session.add(comment)

        act_type = (
            ActivityEventType.GATE_TIMED_OUT if is_timeout else ActivityEventType.GATE_REJECTED
        )
        await record_activity(
            session=session,
            workspace_id=execution.workspace_id,
            object_id=issue.id,
            actor_principal_id=(
                agent_def.principal_id if agent_def else execution.invoking_principal_id
            ),
            event_type=act_type,
            payload={
                "hook_name": hook.name,
                "harness_label": harness_label,
                "error": effective_code,
            },
        )

        outbox_topic = GateEventType.TIMED_OUT if is_timeout else GateEventType.REJECTED
        await enqueue_outbox_event(
            session=session,
            workspace_id=execution.workspace_id,
            project_id=execution.project_id,
            object_id=issue.id,
            topic=outbox_topic,
            payload={
                "issue_id": str(issue.id),
                "issue_key": issue_key,
                "execution_id": str(execution.id),
                "hook_name": hook.name,
                "agent_slug": agent_slug,
                "harness_kind": harness_kind,
                "harness_label": harness_label,
                "from_state": from_name,
                "to_state": to_name,
                "started_at": execution.created_at.isoformat(),
                "completed_at": now.isoformat(),
                "reason_preview": reason_text[:MAX_REASON_PREVIEW_CHARS],
            },
        )

        await session.flush()
        return execution

    @classmethod
    async def cancel(
        cls,
        session: AsyncSession,
        execution_id: uuid.UUID | str,
        actor: PrincipalContext,
    ) -> WorkflowTransitionExecution:
        """Cancel a pending async transition execution (invoking user or project admin)."""
        exec_uuid = uuid.UUID(str(execution_id))
        now = dt.datetime.now(dt.UTC)

        exec_stmt = (
            select(WorkflowTransitionExecution)
            .where(WorkflowTransitionExecution.id == exec_uuid)
            .with_for_update()
        )
        execution = (await session.execute(exec_stmt)).scalar_one_or_none()
        if execution is None or execution.status != "pending_async":
            not_found()

        # Authorization: caller is invoking principal OR has PROJECT_ADMIN
        is_invoker = actor.principal_id == execution.invoking_principal_id
        if not is_invoker:
            caps = await evaluate_capabilities(session, actor, execution.project_id)
            if Capability.ADMIN not in caps:
                not_found()

        issue_stmt = select(Issue).where(Issue.id == execution.issue_id).with_for_update()
        issue = (await session.execute(issue_stmt)).scalar_one_or_none()
        if issue is None:  # pragma: no cover
            not_found()

        from_state = await session.get(WorkflowState, execution.from_state_id)
        to_state = await session.get(WorkflowState, execution.to_state_id)
        project = await session.get(Project, execution.project_id)
        issue_key = f"{project.identifier}-{issue.sequence_id}" if project else str(issue.id)

        # Cancel running invocation if present
        inv_stmt = (
            select(WorkflowHookInvocation)
            .where(
                WorkflowHookInvocation.execution_id == execution.id,
                WorkflowHookInvocation.status == "running",
            )
            .with_for_update()
        )
        inv = (await session.execute(inv_stmt)).scalar_one_or_none()
        if inv:
            inv.status = "error"
            inv.error_code = "CANCELLED"
            inv.completed_at = now

        execution.status = "cancelled"
        execution.verdict_json = {"decision": "cancelled", "actor": str(actor.principal_id)}
        execution.completed_at = now

        if issue.pending_transition_exec_id == execution.id:
            issue.pending_transition_exec_id = None

        await record_activity(
            session=session,
            workspace_id=execution.workspace_id,
            object_id=issue.id,
            actor_principal_id=actor.principal_id,
            event_type=ActivityEventType.GATE_CANCELLED,
            payload={"transition_execution_id": str(execution.id)},
        )

        await enqueue_outbox_event(
            session=session,
            workspace_id=execution.workspace_id,
            project_id=execution.project_id,
            object_id=issue.id,
            topic=GateEventType.CANCELLED,
            payload={
                "issue_id": str(issue.id),
                "issue_key": issue_key,
                "execution_id": str(execution.id),
                "hook_name": inv.hook_kind if inv else "agent_gate",
                "from_state": from_state.name if from_state else "",
                "to_state": to_state.name if to_state else "",
                "started_at": execution.created_at.isoformat(),
                "completed_at": now.isoformat(),
                "reason_preview": "Cancelled by operator",
            },
        )

        await session.flush()
        return execution

    @classmethod
    async def _apply_labels(
        cls, session: AsyncSession, issue: Issue, labels: Sequence[str]
    ) -> None:
        """Apply labels proposed by gate decision."""
        if not labels:
            return
        lbl_stmt = select(ProjectLabel).where(
            ProjectLabel.project_id == issue.project_id,
            ProjectLabel.name.in_(labels),
        )
        matching = list((await session.execute(lbl_stmt)).scalars().all())
        for lbl in matching:
            existing = (
                await session.execute(
                    select(IssueLabel).where(
                        IssueLabel.issue_id == issue.id,
                        IssueLabel.label_id == lbl.id,
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    IssueLabel(
                        workspace_id=issue.workspace_id,
                        issue_id=issue.id,
                        label_id=lbl.id,
                    )
                )

    @classmethod
    async def _apply_links(
        cls,
        session: AsyncSession,
        issue: Issue,
        links: Sequence[LinkSpec],
        creator_id: uuid.UUID,
    ) -> None:
        """Apply object links proposed by gate decision."""
        for lspec in links:
            target_key = lspec.target.strip()
            if "-" not in target_key:
                continue
            parts = target_key.rsplit("-", 1)
            proj_ident = parts[0]
            try:
                seq_num = int(parts[1])
            except ValueError:
                continue
            target_issue_stmt = (
                select(Issue)
                .join(Project, Project.id == Issue.project_id)
                .where(
                    Project.workspace_id == issue.workspace_id,
                    Project.identifier == proj_ident,
                    Issue.sequence_id == seq_num,
                )
            )
            target_issue = (await session.execute(target_issue_stmt)).scalar_one_or_none()
            if target_issue is None or target_issue.id == issue.id:
                continue

            link_kind = lspec.link_type.upper()
            # Check if active link already exists
            link_exists = (
                await session.execute(
                    select(ObjectLink).where(
                        ObjectLink.workspace_id == issue.workspace_id,
                        ObjectLink.source_id == issue.id,
                        ObjectLink.target_id == target_issue.id,
                        ObjectLink.link_type == link_kind,
                        ObjectLink.link_state == "ACTIVE",
                    )
                )
            ).scalar_one_or_none()

            if link_exists is None:
                new_link = ObjectLink(
                    id=uuid.uuid7() if hasattr(uuid, "uuid7") else uuid.uuid4(),
                    workspace_id=issue.workspace_id,
                    source_id=issue.id,
                    source_type="issue",
                    target_id=target_issue.id,
                    target_type="issue",
                    link_type=link_kind,
                    link_state="ACTIVE",
                    created_by_id=creator_id,
                )
                session.add(new_link)
