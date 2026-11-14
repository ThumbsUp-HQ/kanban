# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Workflow transition service and gate hook abstractions for issues (KB-P4-06)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Protocol, runtime_checkable

from pydantic import ValidationError
from sqlalchemy import select, text

from database.models.issues import Issue, IssueAssignee, IssueComment
from database.models.projects import Cycle, Project, WorkflowState
from kanban.api.problems import ProblemException
from kanban.content import normalize_to_markdown
from kanban.issues.proof import VerificationProof, validate_proof_ticket_key
from kanban.security.permissions import Capability, evaluate_capabilities, require_capability
from kanban.services.activity import ActivityEventType, record_activity
from kanban.services.issue_keys import resolve_issue_ref

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext

__all__ = [
    "DefaultWorkflowGateHook",
    "GateHoldResult",
    "WorkflowGateHook",
    "begin_work",
    "complete_work",
    "get_workflow_gate_hook",
    "render_proof_table",
    "set_workflow_gate_hook",
    "transition_ticket",
]

MAX_BODY_BYTES: Final[int] = 65536


@dataclass(frozen=True, slots=True)
class GateHoldResult:
    """Provisional transition hold details emitted when a gate interceptor activates."""

    execution_id: uuid.UUID
    active_agent: str
    from_state: str
    to_state: str


@runtime_checkable
class WorkflowGateHook(Protocol):
    """Protocol for pluggable workflow transition interceptors and gates."""

    async def evaluate_transition(  # noqa: PLR0913, PLR0917
        self,
        session: AsyncSession,
        caller: PrincipalContext,
        issue: Issue,
        from_state: WorkflowState,
        to_state: WorkflowState,
        verification_proof: dict[str, Any] | None = None,
    ) -> GateHoldResult | None:
        """Evaluate whether transition can proceed immediately or must be held."""
        ...


class DefaultWorkflowGateHook:
    """Default pass-through gate hook that introduces zero holds."""

    async def evaluate_transition(  # noqa: PLR0913, PLR0917
        self,
        session: AsyncSession,
        caller: PrincipalContext,
        issue: Issue,
        from_state: WorkflowState,
        to_state: WorkflowState,
        verification_proof: dict[str, Any] | None = None,
    ) -> GateHoldResult | None:
        """Allow all transitions without provisional hold."""
        del session, caller, issue, from_state, to_state, verification_proof
        return None


_ACTIVE_GATE_HOOK: WorkflowGateHook = DefaultWorkflowGateHook()


def get_workflow_gate_hook() -> WorkflowGateHook:
    """Retrieve active WorkflowGateHook."""
    return _ACTIVE_GATE_HOOK


def set_workflow_gate_hook(hook: WorkflowGateHook | None) -> None:
    """Configure active WorkflowGateHook."""
    global _ACTIVE_GATE_HOOK  # noqa: PLW0603
    _ACTIVE_GATE_HOOK = hook if hook is not None else DefaultWorkflowGateHook()


def render_proof_table(summary_markdown: str, proof: dict[str, Any]) -> str:
    """Render markdown summary coupled with structured verification proof table."""
    qa_dir = str(proof.get("qa_dir", ""))
    rc = proof.get("reality_checker", {})
    verdict = str(rc.get("verdict", ""))
    grade = str(rc.get("grade", ""))
    report_path = str(rc.get("report_path", ""))
    ci_run_url = str(proof.get("ci_run_url", ""))
    artifacts = proof.get("artifacts", [])
    count = len(artifacts) if isinstance(artifacts, list) else 0

    return (
        f"{summary_markdown.strip()}\n\n"
        "### Verification Proof\n"
        "| Metric | Value |\n"
        "| :--- | :--- |\n"
        f"| **QA Directory** | `{qa_dir}` |\n"
        f"| **Verdict** | `{verdict}` |\n"
        f"| **Grade** | `{grade}` |\n"
        f"| **Report** | `{report_path}` |\n"
        f"| **CI Run** | [{ci_run_url}]({ci_run_url}) |\n"
        f"| **Artifacts** | {count} files |"
    )


async def _check_if_match_etag(issue: Issue, if_match: str | None) -> None:
    """Validate optional If-Match ETag against issue description SHA-256."""
    if not if_match:
        return
    current_etag = issue.description_sha256.hex() if issue.description_sha256 else ""
    clean_match = if_match.strip().strip('"')
    if clean_match != current_etag:
        raise ProblemException(
            code="CONFLICT_ETAG",
            status=412,
            title="Precondition Failed",
            detail="If-Match ETag does not match current issue description ETag",
        )


async def _resolve_state_by_ref(
    session: AsyncSession,
    project_id: uuid.UUID,
    state_ref: str,
) -> WorkflowState:
    """Resolve workflow state in project by UUID string or exact/case-insensitive name."""
    clean_ref = state_ref.strip()
    try:
        state_uuid = uuid.UUID(clean_ref)
        res = await session.execute(
            select(WorkflowState).where(
                WorkflowState.project_id == project_id,
                WorkflowState.id == state_uuid,
            )
        )
        found = res.scalars().first()
        if found:
            return found
    except ValueError:
        pass

    res_name = await session.execute(
        select(WorkflowState).where(
            WorkflowState.project_id == project_id,
            WorkflowState.name.ilike(clean_ref),
        )
    )
    found_by_name = res_name.scalars().first()
    if found_by_name:
        return found_by_name

    raise ProblemException(
        code="INVALID_TRANSITION",
        status=422,
        title="Invalid Transition",
        detail=f"Target state '{state_ref}' not found in project",
    )


async def begin_work(
    session: AsyncSession,
    caller: PrincipalContext,
    issue_ref: str,
    plan_markdown: str,
    if_match: str | None = None,
) -> tuple[Issue, WorkflowState, WorkflowState, str, GateHoldResult | None]:
    """Execute atomic begin_work operation on an issue in a single transaction."""
    issue = await resolve_issue_ref(session, caller, issue_ref)
    await require_capability(
        session,
        caller,
        issue.id,
        Capability.EDIT | Capability.TRANSITION,
    )

    await _check_if_match_etag(issue, if_match)

    if issue.pending_transition_exec_id is not None:
        raise ProblemException(
            code="TRANSITION_HELD",
            status=409,
            title="Transition Held",
            detail="Issue transition is currently held by an active gate hook",
        )

    # Validate plan markdown byte length
    encoded_plan = plan_markdown.encode("utf-8")
    if len(encoded_plan) < 1 or len(encoded_plan) > MAX_BODY_BYTES:
        raise ProblemException(
            code="VALIDATION_FAILED",
            status=422,
            title="Validation Failed",
            detail="plan_markdown length must be between 1 and 65536 bytes",
        )

    normalized_plan = normalize_to_markdown(plan_markdown)

    # 1. Assign caller principal if not already assigned
    assigned_row = (
        await session.execute(
            select(IssueAssignee.id).where(
                IssueAssignee.issue_id == issue.id,
                IssueAssignee.principal_id == caller.principal_id,
            )
        )
    ).scalar_one_or_none()

    if assigned_row is None:
        await session.execute(
            text(
                "INSERT INTO issue_assignees (workspace_id, issue_id, principal_id) "
                "VALUES (:ws, :iss, :p)"
            ),
            {"ws": caller.workspace_id, "iss": issue.id, "p": caller.principal_id},
        )
        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=issue.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.ASSIGNEE_ADDED,
            payload={"kind": "principal", "principal_id": str(caller.principal_id)},
        )

    # 2. Attach project's single active cycle if issue currently has none
    if issue.cycle_id is None:
        active_cycle = (
            (
                await session.execute(
                    select(Cycle).where(
                        Cycle.project_id == issue.project_id,
                        Cycle.status == "active",
                    )
                )
            )
            .scalars()
            .first()
        )
        if active_cycle is not None:
            issue.cycle_id = active_cycle.id
            await record_activity(
                session,
                workspace_id=caller.workspace_id,
                object_id=issue.id,
                actor_principal_id=caller.principal_id,
                event_type=ActivityEventType.ISSUE_CYCLE_CHANGED,
                payload={"cycle_id": str(active_cycle.id)},
            )

    # 3. Locate lowest sort_order state with group = 'started'
    stmt_state = (
        select(WorkflowState)
        .where(
            WorkflowState.project_id == issue.project_id,
            WorkflowState.state_group == "started",
        )
        .order_by(WorkflowState.sort_order.asc(), WorkflowState.id.asc())
    )
    started_state = (await session.execute(stmt_state)).scalars().first()
    if started_state is None:
        raise ProblemException(
            code="NO_STARTED_STATE",
            status=409,
            title="No Started State",
            detail="Project has no workflow state configured in the 'started' group",
        )

    from_state = await session.get(WorkflowState, issue.state_id)
    if from_state is None:
        raise ProblemException(
            code="INVALID_TRANSITION",
            status=422,
            title="Invalid Transition",
            detail="Current issue state could not be resolved",
        )

    # Evaluate gate hook
    hook = get_workflow_gate_hook()
    gate_hold = await hook.evaluate_transition(session, caller, issue, from_state, started_state)

    if gate_hold is not None:
        issue.pending_transition_exec_id = gate_hold.execution_id
    elif issue.state_id != started_state.id:
        old_id = issue.state_id
        issue.state_id = started_state.id
        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=issue.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.ISSUE_STATE_CHANGED,
            payload={
                "from_state_id": str(old_id),
                "to_state_id": str(started_state.id),
                "from_state": from_state.name,
                "to_state": started_state.name,
            },
        )

    # 4. Post plan_markdown as an issue comment
    comment = IssueComment(
        workspace_id=caller.workspace_id,
        issue_id=issue.id,
        author_id=caller.principal_id,
        body_markdown=normalized_plan,
    )
    session.add(comment)
    await session.flush()
    await session.refresh(comment)

    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=issue.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.COMMENT_CREATED,
        payload={
            "comment_id": str(comment.id),
            "body_sha256": comment.body_sha256.hex() if comment.body_sha256 else "",
        },
    )

    # Generate permalink
    proj = await session.get(Project, issue.project_id)
    p_ident = proj.identifier if proj else "ISSUE"
    comment_ref = f"{p_ident}-{issue.sequence_id}#c-{str(comment.id)[:8]}"

    await session.flush()
    await session.refresh(issue)
    return issue, from_state, started_state, comment_ref, gate_hold


async def transition_ticket(  # noqa: PLR0913, PLR0917
    session: AsyncSession,
    caller: PrincipalContext,
    issue_ref: str,
    to_state_ref: str,
    comment_markdown: str | None = None,
    verification_proof: dict[str, Any] | None = None,
    if_match: str | None = None,
) -> tuple[Issue, WorkflowState, WorkflowState, GateHoldResult | None]:
    """Execute intermediate state transition on an issue."""
    issue = await resolve_issue_ref(session, caller, issue_ref)
    await require_capability(session, caller, issue.id, Capability.TRANSITION)

    await _check_if_match_etag(issue, if_match)

    if issue.pending_transition_exec_id is not None:
        raise ProblemException(
            code="TRANSITION_HELD",
            status=409,
            title="Transition Held",
            detail="Issue transition is currently held by an active gate hook",
        )

    target_state = await _resolve_state_by_ref(session, issue.project_id, to_state_ref)

    if target_state.state_group == "completed":
        raise ProblemException(
            code="USE_COMPLETE_WORK",
            status=422,
            title="Use Complete Work",
            detail=(
                f"Cannot transition to terminal state '{target_state.name}' using "
                "transition_ticket. Use complete_work with verification proof."
            ),
        )

    from_state = await session.get(WorkflowState, issue.state_id)
    if from_state is None:
        raise ProblemException(
            code="INVALID_TRANSITION",
            status=422,
            title="Invalid Transition",
            detail="Current issue state could not be resolved",
        )

    hook = get_workflow_gate_hook()
    gate_hold = await hook.evaluate_transition(
        session,
        caller,
        issue,
        from_state,
        target_state,
        verification_proof=verification_proof,
    )

    if gate_hold is not None:
        issue.pending_transition_exec_id = gate_hold.execution_id
    elif issue.state_id != target_state.id:
        old_id = issue.state_id
        issue.state_id = target_state.id
        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=issue.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.ISSUE_STATE_CHANGED,
            payload={
                "from_state_id": str(old_id),
                "to_state_id": str(target_state.id),
                "from_state": from_state.name,
                "to_state": target_state.name,
            },
        )

    if comment_markdown:
        encoded = comment_markdown.encode("utf-8")
        if len(encoded) > MAX_BODY_BYTES:
            raise ProblemException(
                code="VALIDATION_FAILED",
                status=422,
                title="Validation Failed",
                detail="comment_markdown length must be <= 65536 bytes",
            )
        normalized_comment = normalize_to_markdown(comment_markdown)
        c = IssueComment(
            workspace_id=caller.workspace_id,
            issue_id=issue.id,
            author_id=caller.principal_id,
            body_markdown=normalized_comment,
        )
        session.add(c)
        await session.flush()
        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=issue.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.COMMENT_CREATED,
            payload={
                "comment_id": str(c.id),
                "body_sha256": c.body_sha256.hex() if c.body_sha256 else "",
            },
        )

    await session.flush()
    await session.refresh(issue)
    return issue, from_state, target_state, gate_hold


async def _collect_open_blockers(
    session: AsyncSession,
    caller: PrincipalContext,
    issue: Issue,
) -> list[str]:
    """Inspect recursive child issues and incoming BLOCKS links for uncompleted work."""
    visible_keys: list[str] = []
    redacted_count = 0
    seen_ids: set[uuid.UUID] = set()

    # 1. Recursive child issues
    stmt_children = text(
        "WITH RECURSIVE descendants AS ("
        "    SELECT id, project_id, state_id, sequence_id FROM issues WHERE parent_issue_id = :iid "
        "    UNION ALL "
        "    SELECT i.id, i.project_id, i.state_id, i.sequence_id FROM issues i "
        "    JOIN descendants d ON i.parent_issue_id = d.id "
        ") "
        "SELECT d.id, d.project_id, d.sequence_id, p.identifier "
        "FROM descendants d "
        "JOIN projects p ON p.id = d.project_id "
        "JOIN workflow_states ws ON ws.id = d.state_id "
        "WHERE ws.state_group NOT IN ('completed', 'cancelled')"
    )
    child_rows = (await session.execute(stmt_children, {"iid": issue.id})).all()
    for row in child_rows:
        b_id, _, b_seq, b_pident = row[0], row[1], row[2], row[3]
        if b_id in seen_ids:
            continue
        seen_ids.add(b_id)
        caps = await evaluate_capabilities(session, caller, b_id)
        if Capability.VIEW in caps:
            visible_keys.append(f"{b_pident}-{b_seq}")
        else:
            redacted_count += 1

    # 2. Inbound BLOCKS links from object_links
    stmt_blocks = text(
        "SELECT ol.source_id, ol.source_key_snapshot "
        "FROM object_links ol "
        "WHERE ol.target_id = :iid "
        "  AND ol.link_type = 'BLOCKS' "
        "  AND ol.link_state = 'ACTIVE'"
    )
    block_links = (await session.execute(stmt_blocks, {"iid": issue.id})).all()
    for row in block_links:
        src_id = row[0]
        if src_id in seen_ids:
            continue
        seen_ids.add(src_id)

        caps = await evaluate_capabilities(session, caller, src_id)
        if Capability.VIEW not in caps:
            redacted_count += 1
            continue

        # For readable source, check whether its state is non-terminal
        src_state_stmt = text(
            "SELECT p.identifier, src.sequence_id, ws.state_group "
            "FROM issues src "
            "JOIN projects p ON p.id = src.project_id "
            "JOIN workflow_states ws ON ws.id = src.state_id "
            "WHERE src.id = :sid"
        )
        src_state_row = (await session.execute(src_state_stmt, {"sid": src_id})).first()
        if src_state_row is not None:
            p_ident, seq, state_grp = src_state_row[0], src_state_row[1], src_state_row[2]
            if state_grp not in ("completed", "cancelled"):
                visible_keys.append(f"{p_ident}-{seq}")

    result_keys = visible_keys[:20]
    if redacted_count > 0:
        plural = "blocker" if redacted_count == 1 else "blockers"
        result_keys.append(f"redacted: {redacted_count} hidden {plural}")

    return result_keys


async def complete_work(  # noqa: C901, PLR0913, PLR0915, PLR0917
    session: AsyncSession,
    caller: PrincipalContext,
    issue_ref: str,
    summary_markdown: str,
    verification_proof: dict[str, Any],
    to_state_ref: str | None = None,
    if_match: str | None = None,
) -> tuple[Issue, WorkflowState, WorkflowState, dict[str, Any], str, GateHoldResult | None]:
    """Execute complete_work workflow: blocker audit, QA gate verification, and transition."""
    issue = await resolve_issue_ref(session, caller, issue_ref)
    await require_capability(session, caller, issue.id, Capability.TRANSITION)

    await _check_if_match_etag(issue, if_match)

    if issue.pending_transition_exec_id is not None:
        raise ProblemException(
            code="TRANSITION_HELD",
            status=409,
            title="Transition Held",
            detail="Issue transition is currently held by an active gate hook",
        )

    # 1. Check open child blockers and inbound BLOCKS links
    blockers = await _collect_open_blockers(session, caller, issue)
    if blockers:
        raise ProblemException(
            code="OPEN_CHILD_BLOCKERS",
            status=409,
            title="Open Child Blockers",
            detail=f"Issue has open blockers: {', '.join(blockers)}",
            extra={"blockers": blockers},
        )

    # 2. Validate structured verification_proof schema and ticket key invariants
    proj = await session.get(Project, issue.project_id)
    issue_key = f"{proj.identifier}-{issue.sequence_id}" if proj else str(issue.id)

    try:
        parsed_proof = VerificationProof.model_validate(verification_proof)
        validate_proof_ticket_key(parsed_proof, issue_key)
    except (ValueError, ValidationError) as exc:
        raise ProblemException(
            code="VALIDATION_FAILED",
            status=422,
            title="Validation Failed",
            detail=str(exc),
        ) from exc

    if parsed_proof.reality_checker.verdict != "READY" or parsed_proof.reality_checker.grade != "A":
        raise ProblemException(
            code="QA_VERDICT_NOT_READY",
            status=422,
            title="QA Verdict Not Ready",
            detail=(
                "Reality-Checker verdict must be READY with grade A "
                f"(got {parsed_proof.reality_checker.verdict} / "
                f"{parsed_proof.reality_checker.grade})"
            ),
        )

    # Validate summary markdown length
    encoded_summary = summary_markdown.encode("utf-8")
    if len(encoded_summary) < 1 or len(encoded_summary) > MAX_BODY_BYTES:
        raise ProblemException(
            code="VALIDATION_FAILED",
            status=422,
            title="Validation Failed",
            detail="summary_markdown length must be between 1 and 65536 bytes",
        )

    # Resolve target completed state
    if to_state_ref:
        target_state = await _resolve_state_by_ref(session, issue.project_id, to_state_ref)
        if target_state.state_group != "completed":
            raise ProblemException(
                code="INVALID_TRANSITION",
                status=422,
                title="Invalid Transition",
                detail=f"Target state '{target_state.name}' is not in the 'completed' group",
            )
    else:
        stmt_comp = (
            select(WorkflowState)
            .where(
                WorkflowState.project_id == issue.project_id,
                WorkflowState.state_group == "completed",
            )
            .order_by(WorkflowState.sort_order.asc(), WorkflowState.id.asc())
        )
        comp_state = (await session.execute(stmt_comp)).scalars().first()
        if comp_state is None:
            raise ProblemException(
                code="INVALID_TRANSITION",
                status=422,
                title="Invalid Transition",
                detail="Project has no workflow state configured in the 'completed' group",
            )
        target_state = comp_state

    from_state = await session.get(WorkflowState, issue.state_id)
    if from_state is None:
        raise ProblemException(
            code="INVALID_TRANSITION",
            status=422,
            title="Invalid Transition",
            detail="Current issue state could not be resolved",
        )

    # 3. Evaluate gate hook
    hook = get_workflow_gate_hook()
    gate_hold = await hook.evaluate_transition(
        session,
        caller,
        issue,
        from_state,
        target_state,
        verification_proof=verification_proof,
    )

    if gate_hold is not None:
        issue.pending_transition_exec_id = gate_hold.execution_id
    elif issue.state_id != target_state.id:
        old_id = issue.state_id
        issue.state_id = target_state.id
        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=issue.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.ISSUE_STATE_CHANGED,
            payload={
                "from_state_id": str(old_id),
                "to_state_id": str(target_state.id),
                "from_state": from_state.name,
                "to_state": target_state.name,
            },
        )

    # 4. Post summary comment with rendered proof table
    comment_content = render_proof_table(summary_markdown, verification_proof)
    normalized_content = normalize_to_markdown(comment_content)
    comment = IssueComment(
        workspace_id=caller.workspace_id,
        issue_id=issue.id,
        author_id=caller.principal_id,
        body_markdown=normalized_content,
    )
    session.add(comment)
    await session.flush()
    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=issue.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.COMMENT_CREATED,
        payload={
            "comment_id": str(comment.id),
            "body_sha256": comment.body_sha256.hex() if comment.body_sha256 else "",
        },
    )

    # 5. Record WORK_COMPLETED activity
    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=issue.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.WORK_COMPLETED,
        payload=verification_proof,
    )

    proj = await session.get(Project, issue.project_id)
    p_ident = proj.identifier if proj else "ISSUE"
    comment_ref = f"{p_ident}-{issue.sequence_id}#c-{str(comment.id)[:8]}"

    await session.flush()
    await session.refresh(issue)
    return issue, from_state, target_state, verification_proof, comment_ref, gate_hold
