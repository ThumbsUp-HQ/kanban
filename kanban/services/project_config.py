# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Project configuration business logic (KB-P3-01b).

Implements management of workflow states (with WIP limits), custom priorities,
and labels (with exclusive groups).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified

from database.models import (
    Issue,
    IssueLabel,
    ObjectRecord,
    ProjectPriority,
    WorkflowState,
    WorkflowTransitionExecution,
    WorkflowTransitionHook,
)
from database.models.projects import ProjectLabel, View
from kanban.api.problems import ProblemException, not_found
from kanban.api.v1.schemas.project_config import (
    LabelAuditImpactResponse,
    LabelCreate,
    LabelPatch,
    LabelResponse,
    PriorityCreate,
    PriorityPatch,
    PriorityResponse,
    SavedViewSummary,
    StateAuditImpactResponse,
    StateCreate,
    StatePatch,
    StateResponse,
    WorkflowHookSummary,
)
from kanban.security.permissions import Capability, require_capability
from kanban.services.activity import ActivityEventType, record_activity
from kanban.services.projects import get_project_or_404
from kanban.workflows.manifest import compute_hook_manifest_sha256

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext

MAX_MIGRATION_ISSUES: int = 500


def _migrate_id_in_list(
    raw_list: list[object],
    target_str: str,
    replacement_str: str | None,
) -> tuple[list[str], bool]:
    """Replace target_str with replacement_str (deduplicating), or remove if replacement is None."""
    new_items: list[str] = []
    seen: set[str] = set()
    modified = False
    for item in raw_list:
        item_str = str(item)
        if item_str == target_str:
            modified = True
            if replacement_str and replacement_str not in seen:
                seen.add(replacement_str)
                new_items.append(replacement_str)
        elif item_str not in seen:
            seen.add(item_str)
            new_items.append(item_str)
    return new_items, modified


def _migrate_id_in_dict(
    d: dict[str, Any],
    field: str,
    target_str: str,
    replacement_str: str | None,
) -> tuple[dict[str, Any], bool]:
    """Recursively replace or remove target_str in dict occurrences of field."""
    new_dict: dict[str, Any] = {}
    any_modified = False
    for k, v in d.items():
        if k == field and isinstance(v, list):
            new_list, mod = _migrate_id_in_list(v, target_str, replacement_str)
            new_dict[k] = new_list
            if mod:
                any_modified = True
        elif isinstance(v, dict):
            new_sub_dict, mod = _migrate_id_in_dict(v, field, target_str, replacement_str)
            new_dict[k] = new_sub_dict
            if mod:
                any_modified = True
        elif isinstance(v, list):
            new_sub_list, mod = _migrate_id_in_container_list(v, field, target_str, replacement_str)
            new_dict[k] = new_sub_list
            if mod:
                any_modified = True
        else:
            new_dict[k] = v
    return new_dict, any_modified


def _migrate_id_in_container_list(
    items: list[Any],
    field: str,
    target_str: str,
    replacement_str: str | None,
) -> tuple[list[Any], bool]:
    """Recursively replace or remove target_str inside nested list elements."""
    new_items: list[Any] = []
    any_modified = False
    for item in items:
        if isinstance(item, dict):
            new_d, mod = _migrate_id_in_dict(item, field, target_str, replacement_str)
            new_items.append(new_d)
            if mod:
                any_modified = True
        elif isinstance(item, list):
            new_l, mod = _migrate_id_in_container_list(item, field, target_str, replacement_str)
            new_items.append(new_l)
            if mod:
                any_modified = True
        else:
            new_items.append(item)
    return new_items, any_modified


def _nested_references_id(obj: object, field: str, target_str: str) -> bool:
    """Recursively check if field contains target_str in nested dicts/lists."""
    if isinstance(obj, dict):
        raw_val = obj.get(field)
        if isinstance(raw_val, list) and any(str(x) == target_str for x in raw_val):
            return True
        return any(_nested_references_id(v, field, target_str) for v in obj.values())
    if isinstance(obj, list):
        return any(_nested_references_id(item, field, target_str) for item in obj)
    return False


def _view_references_id(view: View, field: str, target_id: uuid.UUID) -> bool:
    """Check if view references target_id in filters_json or display_props_json."""
    target_str = str(target_id)
    return _nested_references_id(view.filters_json, field, target_str) or _nested_references_id(
        view.display_props_json, field, target_str
    )


def _update_views_for_deleted_id(
    views: Sequence[View],
    field: str,
    target_id: uuid.UUID,
    replacement_id: uuid.UUID | None,
) -> None:
    """Migrate references to target_id across filters_json and display_props_json in saved views."""
    target_str = str(target_id)
    repl_str = str(replacement_id) if replacement_id else None
    for v in views:
        if isinstance(v.filters_json, dict):
            new_filters, mod = _migrate_id_in_dict(v.filters_json, field, target_str, repl_str)
            if mod:
                v.filters_json = new_filters
                flag_modified(v, "filters_json")
        if isinstance(v.display_props_json, dict):
            new_display, mod = _migrate_id_in_dict(
                v.display_props_json, field, target_str, repl_str
            )
            if mod:
                v.display_props_json = new_display
                flag_modified(v, "display_props_json")


# ---------------------------------------------------------------------------
# Workflow States
# ---------------------------------------------------------------------------


async def list_states(
    session: AsyncSession,
    caller: PrincipalContext,
    project_ref: str,
) -> list[StateResponse]:
    """List workflow states for a project ordered by sort_order."""
    project = await get_project_or_404(session, caller, project_ref)
    await require_capability(session, caller, project.id, Capability.VIEW)

    # Aggregate non-archived, non-deleted issues per state
    counts_query = (
        select(Issue.state_id, func.count(Issue.id).label("cnt"))
        .join(ObjectRecord, ObjectRecord.id == Issue.id)
        .where(
            Issue.project_id == project.id,
            ObjectRecord.archived_at.is_(None),
            ObjectRecord.deleted_at.is_(None),
        )
        .group_by(Issue.state_id)
    )
    counts_res = await session.execute(counts_query)
    issue_counts: dict[uuid.UUID, int] = {row[0]: row[1] for row in counts_res.all()}

    states_query = (
        select(WorkflowState)
        .where(WorkflowState.project_id == project.id)
        .order_by(WorkflowState.sort_order, WorkflowState.name)
    )
    res = await session.execute(states_query)
    states = res.scalars().all()

    return [
        StateResponse(
            id=s.id,
            project_id=s.project_id,
            name=s.name,
            group=s.state_group,  # type: ignore[arg-type]
            color_hex=s.color_hex,
            sort_order=s.sort_order,
            is_default=s.is_default,
            wip_soft_limit=s.wip_soft_limit,
            wip_hard_limit=s.wip_hard_limit,
            issue_count=issue_counts.get(s.id, 0),
        )
        for s in states
    ]


def _is_unique_violation(exc: IntegrityError) -> bool:
    """Return True when the wrapped driver error carries SQLSTATE 23505."""
    orig = exc.orig
    candidates = (orig, getattr(orig, "__cause__", None))
    return (
        any(
            getattr(c, "sqlstate", None) == "23505" or getattr(c, "pgcode", None) == "23505"
            for c in candidates
        )
        or "23505" in str(exc)
        or "unique constraint" in str(exc).lower()
    )


async def create_state(
    session: AsyncSession,
    caller: PrincipalContext,
    project_ref: str,
    data: StateCreate,
) -> StateResponse:
    """Create a new workflow state for a project."""
    project = await get_project_or_404(session, caller, project_ref)
    await require_capability(session, caller, project.id, Capability.ADMIN)

    # Check case-insensitive name uniqueness within project
    existing = await session.execute(
        select(WorkflowState.id).where(
            WorkflowState.project_id == project.id,
            func.lower(WorkflowState.name) == data.name.lower(),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ProblemException(
            status=409,
            code="STATE_NAME_TAKEN",
            title="State Name Taken",
            detail=None,
        )

    # Single default invariant: setting is_default=true clears previous default
    if data.is_default:
        await session.execute(
            update(WorkflowState)
            .where(WorkflowState.project_id == project.id)
            .values(is_default=False)
        )

    new_state = WorkflowState(
        workspace_id=project.workspace_id,
        project_id=project.id,
        name=data.name,
        state_group=data.group,
        color_hex=data.color_hex,
        sort_order=data.sort_order,
        is_default=data.is_default,
        wip_soft_limit=data.wip_soft_limit,
        wip_hard_limit=data.wip_hard_limit,
    )
    session.add(new_state)
    try:
        await session.flush()
    except IntegrityError as exc:
        if _is_unique_violation(exc):
            raise ProblemException(
                status=409,
                code="STATE_NAME_TAKEN",
                title="State Name Taken",
                detail=None,
            ) from exc
        raise

    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=project.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.STATE_CREATED,
        payload={
            "state_id": str(new_state.id),
            "name": new_state.name,
            "group": new_state.state_group,
            "color_hex": new_state.color_hex,
            "sort_order": new_state.sort_order,
            "is_default": new_state.is_default,
        },
    )

    return StateResponse(
        id=new_state.id,
        project_id=new_state.project_id,
        name=new_state.name,
        group=new_state.state_group,  # type: ignore[arg-type]
        color_hex=new_state.color_hex,
        sort_order=new_state.sort_order,
        is_default=new_state.is_default,
        wip_soft_limit=new_state.wip_soft_limit,
        wip_hard_limit=new_state.wip_hard_limit,
        issue_count=0,
    )


async def update_state(  # noqa: C901, PLR0912, PLR0915
    session: AsyncSession,
    caller: PrincipalContext,
    project_ref: str,
    state_id: uuid.UUID,
    data: StatePatch,
) -> StateResponse:
    """Update mutable fields of a workflow state."""
    project = await get_project_or_404(session, caller, project_ref)
    await require_capability(session, caller, project.id, Capability.ADMIN)

    res = await session.execute(
        select(WorkflowState).where(
            WorkflowState.project_id == project.id,
            WorkflowState.id == state_id,
        )
    )
    state = res.scalar_one_or_none()
    if state is None:
        not_found()

    # Validate combined WIP limits if partial updates given
    effective_soft = (
        data.wip_soft_limit if data.wip_soft_limit is not None else state.wip_soft_limit
    )
    effective_hard = (
        data.wip_hard_limit if data.wip_hard_limit is not None else state.wip_hard_limit
    )
    if (
        effective_soft is not None
        and effective_hard is not None
        and effective_soft > effective_hard
    ):
        raise ProblemException(
            status=422,
            code="INVALID_WIP_LIMITS",
            title="Invalid WIP Limits",
            detail=None,
        )

    # Name uniqueness check
    if data.name is not None and data.name.lower() != state.name.lower():
        existing = await session.execute(
            select(WorkflowState.id).where(
                WorkflowState.project_id == project.id,
                WorkflowState.id != state_id,
                func.lower(WorkflowState.name) == data.name.lower(),
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ProblemException(
                status=409,
                code="STATE_NAME_TAKEN",
                title="State Name Taken",
                detail=None,
            )

    # Group check: cannot move the sole remaining state out of required lifecycle groups
    if (
        data.group is not None
        and data.group != state.state_group
        and state.state_group in ("completed", "cancelled", "backlog", "started")
    ):
        grp_count_res = await session.execute(
            select(func.count(WorkflowState.id)).where(
                WorkflowState.project_id == project.id,
                WorkflowState.state_group == state.state_group,
            )
        )
        if grp_count_res.scalar_one() <= 1:
            raise ProblemException(
                status=409,
                code="LAST_STATE_IN_GROUP",
                title="Cannot Move Last State Out Of Group",
                detail=None,
            )

    # Exactly one default invariant
    if data.is_default is False and state.is_default:
        raise ProblemException(
            status=409,
            code="DEFAULT_STATE_REQUIRED",
            title="Default State Required",
            detail=None,
        )
    if data.is_default is True:
        await session.execute(
            update(WorkflowState)
            .where(
                WorkflowState.project_id == project.id,
                WorkflowState.id != state_id,
            )
            .values(is_default=False)
        )

    changes: dict[str, dict[str, Any]] = {}

    if data.name is not None and data.name != state.name:
        changes["name"] = {"old": state.name, "new": data.name}
        state.name = data.name

    if data.group is not None and data.group != state.state_group:
        changes["group"] = {"old": state.state_group, "new": data.group}
        state.state_group = data.group

    if data.color_hex is not None and data.color_hex != state.color_hex:
        changes["color_hex"] = {"old": state.color_hex, "new": data.color_hex}
        state.color_hex = data.color_hex

    if data.sort_order is not None and data.sort_order != state.sort_order:
        changes["sort_order"] = {"old": state.sort_order, "new": data.sort_order}
        state.sort_order = data.sort_order

    if data.is_default is not None and data.is_default != state.is_default:
        changes["is_default"] = {"old": state.is_default, "new": data.is_default}
        state.is_default = data.is_default

    if (
        data.wip_soft_limit is not None or "wip_soft_limit" in data.model_fields_set
    ) and data.wip_soft_limit != state.wip_soft_limit:
        changes["wip_soft_limit"] = {"old": state.wip_soft_limit, "new": data.wip_soft_limit}
        state.wip_soft_limit = data.wip_soft_limit

    if (
        data.wip_hard_limit is not None or "wip_hard_limit" in data.model_fields_set
    ) and data.wip_hard_limit != state.wip_hard_limit:
        changes["wip_hard_limit"] = {"old": state.wip_hard_limit, "new": data.wip_hard_limit}
        state.wip_hard_limit = data.wip_hard_limit

    try:
        await session.flush()
    except IntegrityError as exc:
        if _is_unique_violation(exc):
            raise ProblemException(
                status=409,
                code="STATE_NAME_TAKEN",
                title="State Name Taken",
                detail=None,
            ) from exc
        raise

    if changes:
        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=project.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.STATE_UPDATED,
            payload={
                "state_id": str(state.id),
                "changes": changes,
            },
        )

    # Issue count for response
    cnt_res = await session.execute(
        select(func.count(Issue.id))
        .join(ObjectRecord, ObjectRecord.id == Issue.id)
        .where(
            Issue.project_id == project.id,
            Issue.state_id == state.id,
            ObjectRecord.archived_at.is_(None),
            ObjectRecord.deleted_at.is_(None),
        )
    )
    issue_count = cnt_res.scalar_one()

    return StateResponse(
        id=state.id,
        project_id=state.project_id,
        name=state.name,
        group=state.state_group,  # type: ignore[arg-type]
        color_hex=state.color_hex,
        sort_order=state.sort_order,
        is_default=state.is_default,
        wip_soft_limit=state.wip_soft_limit,
        wip_hard_limit=state.wip_hard_limit,
        issue_count=issue_count,
    )


async def get_state_audit_impact(
    session: AsyncSession,
    caller: PrincipalContext,
    project_ref: str,
    state_id: uuid.UUID,
) -> StateAuditImpactResponse:
    """Compute reverse-audit impact of deleting a workflow state."""
    project = await get_project_or_404(session, caller, project_ref)
    await require_capability(session, caller, project.id, Capability.ADMIN)

    res = await session.execute(
        select(WorkflowState).where(
            WorkflowState.project_id == project.id,
            WorkflowState.id == state_id,
        )
    )
    state = res.scalar_one_or_none()
    if state is None:
        not_found()

    # 1. Issues count and sample keys (including archived and soft-deleted issues for FK parity)
    issues_res = await session.execute(
        select(Issue.sequence_id)
        .where(
            Issue.project_id == project.id,
            Issue.state_id == state_id,
        )
        .order_by(Issue.sequence_id.desc())
    )
    issue_seqs = issues_res.scalars().all()
    issues_count = len(issue_seqs)
    sample_issue_keys = [f"{project.identifier}-{seq}" for seq in issue_seqs[:5]]

    # 2. Workflow automation hooks referencing this state
    hooks_res = await session.execute(
        select(WorkflowTransitionHook).where(
            WorkflowTransitionHook.project_id == project.id,
            (WorkflowTransitionHook.from_state_id == state_id)
            | (WorkflowTransitionHook.to_state_id == state_id),
        )
    )
    hooks = hooks_res.scalars().all()
    workflow_hooks = [
        WorkflowHookSummary(
            id=h.id,
            name=h.name,
            hook_kind=h.hook_kind,
            is_enabled=h.is_enabled,
            from_state_id=h.from_state_id,
            to_state_id=h.to_state_id,
        )
        for h in hooks
    ]

    # 3. In-flight and historical executions
    pending_cnt_res = await session.execute(
        select(func.count(WorkflowTransitionExecution.id)).where(
            WorkflowTransitionExecution.project_id == project.id,
            (WorkflowTransitionExecution.from_state_id == state_id)
            | (WorkflowTransitionExecution.to_state_id == state_id),
            WorkflowTransitionExecution.status.in_(["running_sync", "pending_async"]),
        )
    )
    pending_executions_count = pending_cnt_res.scalar_one()

    hist_cnt_res = await session.execute(
        select(func.count(WorkflowTransitionExecution.id)).where(
            WorkflowTransitionExecution.project_id == project.id,
            (WorkflowTransitionExecution.from_state_id == state_id)
            | (WorkflowTransitionExecution.to_state_id == state_id),
            WorkflowTransitionExecution.status.notin_(["running_sync", "pending_async"]),
        )
    )
    historical_executions_count = hist_cnt_res.scalar_one()

    # 4. Saved views referencing this state
    views_res = await session.execute(select(View).where(View.project_id == project.id))
    views = views_res.scalars().all()
    saved_views = [
        SavedViewSummary(id=v.id, name=v.name)
        for v in views
        if _view_references_id(v, "state_ids", state_id)
    ]

    # 5. Blocking reasons
    blocking_reasons: list[str] = []
    if state.is_default:
        blocking_reasons.append("Default State: Default workflow state cannot be deleted.")

    if state.state_group in ("completed", "cancelled", "backlog"):
        grp_cnt_res = await session.execute(
            select(func.count(WorkflowState.id)).where(
                WorkflowState.project_id == project.id,
                WorkflowState.state_group == state.state_group,
            )
        )
        if grp_cnt_res.scalar_one() <= 1:
            blocking_reasons.append("Last State in Group: Cannot delete the last state in group.")

    if pending_executions_count > 0:
        blocking_reasons.append(
            "In-Flight Gate: Transitions are currently in flight for this state."
        )

    # 6. Valid replacement states (all other states in same project)
    other_states = await list_states(session, caller, project_ref)
    valid_replacement_states = [s for s in other_states if s.id != state_id]

    return StateAuditImpactResponse(
        state_id=state.id,
        project_id=project.id,
        issues_count=issues_count,
        sample_issue_keys=sample_issue_keys,
        workflow_hooks=workflow_hooks,
        pending_executions_count=pending_executions_count,
        historical_executions_count=historical_executions_count,
        saved_views=saved_views,
        is_default=state.is_default,
        blocking_reasons=blocking_reasons,
        valid_replacement_states=valid_replacement_states,
    )


async def delete_state(  # noqa: C901, PLR0912, PLR0913, PLR0915, PLR0917
    session: AsyncSession,
    caller: PrincipalContext,
    project_ref: str,
    state_id: uuid.UUID,
    replacement_state_id: uuid.UUID | None = None,
    migrate_to: uuid.UUID | None = None,
    migrate_hooks: bool = True,  # noqa: FBT001, FBT002
) -> None:
    """Delete a workflow state with hardened reverse-audit and migration."""
    project = await get_project_or_404(session, caller, project_ref)
    await require_capability(session, caller, project.id, Capability.ADMIN)

    res = await session.execute(
        select(WorkflowState).where(
            WorkflowState.project_id == project.id,
            WorkflowState.id == state_id,
        )
    )
    state = res.scalar_one_or_none()
    if state is None:
        not_found()

    effective_replacement_id = replacement_state_id or migrate_to

    # Validate effective_replacement_id if provided
    if effective_replacement_id is not None:
        if effective_replacement_id == state_id:
            raise ProblemException(
                status=422,
                code="MIGRATE_TARGET_INVALID",
                title="Invalid Migration Target",
                detail=None,
            )
        target_res = await session.execute(
            select(WorkflowState).where(
                WorkflowState.project_id == project.id,
                WorkflowState.id == effective_replacement_id,
            )
        )
        if target_res.scalar_one_or_none() is None:
            raise ProblemException(
                status=422,
                code="MIGRATE_TARGET_INVALID",
                title="Invalid Migration Target",
                detail=None,
            )

    # Rule: cannot delete default state
    if state.is_default:
        raise ProblemException(
            status=409,
            code="DEFAULT_STATE",
            title="Default State Cannot Be Deleted",
            detail=None,
        )

    # Rule: cannot delete last state in completed, cancelled, backlog, or started
    if state.state_group in ("completed", "cancelled", "backlog", "started"):
        grp_count_res = await session.execute(
            select(func.count(WorkflowState.id)).where(
                WorkflowState.project_id == project.id,
                WorkflowState.state_group == state.state_group,
            )
        )
        if grp_count_res.scalar_one() <= 1:
            raise ProblemException(
                status=409,
                code="LAST_STATE_IN_GROUP",
                title="Cannot Delete Last State In Group",
                detail=None,
            )

    # Rule: Fail closed if in-flight transition executions exist
    pending_cnt_res = await session.execute(
        select(func.count(WorkflowTransitionExecution.id)).where(
            WorkflowTransitionExecution.project_id == project.id,
            (WorkflowTransitionExecution.from_state_id == state_id)
            | (WorkflowTransitionExecution.to_state_id == state_id),
            WorkflowTransitionExecution.status.in_(["running_sync", "pending_async"]),
        )
    )
    if pending_cnt_res.scalar_one() > 0:
        raise ProblemException(
            status=409,
            code="TRANSITION_IN_FLIGHT",
            title="Transition In Flight",
            detail="In-flight transition gate is active for this state.",
        )

    # Check workflow transition hooks
    hooks_res = await session.execute(
        select(WorkflowTransitionHook).where(
            WorkflowTransitionHook.project_id == project.id,
            (WorkflowTransitionHook.from_state_id == state_id)
            | (WorkflowTransitionHook.to_state_id == state_id),
        )
    )
    hooks = hooks_res.scalars().all()
    enabled_hooks = [h for h in hooks if h.is_enabled]
    disabled_hooks = [h for h in hooks if not h.is_enabled]

    if enabled_hooks and (effective_replacement_id is None or not migrate_hooks):
        raise ProblemException(
            status=409,
            code="ACTIVE_AUTOMATION_HOOK_REQUIRES_STATE",
            title="Active Automation Hook Requires State",
            detail="Active automation hooks reference this state.",
        )

    # Check self-loops if migrating hooks
    if effective_replacement_id is not None and migrate_hooks:
        for h in enabled_hooks:
            new_from = effective_replacement_id if h.from_state_id == state_id else h.from_state_id
            new_to = effective_replacement_id if h.to_state_id == state_id else h.to_state_id
            if new_from is not None and new_from == new_to:
                raise ProblemException(
                    status=409,
                    code="HOOK_MIGRATION_CREATES_SELF_LOOP",
                    title="Hook Migration Creates Self Loop",
                    detail="Migrating hook would create a self-loop transition.",
                )

    # Query issues currently using this state
    issues_res = await session.execute(
        select(Issue).where(
            Issue.project_id == project.id,
            Issue.state_id == state_id,
        )
    )
    issues = issues_res.scalars().all()

    if issues:
        if effective_replacement_id is None:
            raise ProblemException(
                status=409,
                code="STATE_IN_USE",
                title="State In Use",
                detail=None,
            )
        if len(issues) > MAX_MIGRATION_ISSUES:
            raise ProblemException(
                status=409,
                code="MIGRATION_TOO_LARGE",
                title="Migration Too Large",
                detail=None,
            )

    # Historical executions check if no replacement provided
    if effective_replacement_id is None:
        hist_exec_res = await session.execute(
            select(func.count(WorkflowTransitionExecution.id)).where(
                WorkflowTransitionExecution.project_id == project.id,
                (WorkflowTransitionExecution.from_state_id == state_id)
                | (WorkflowTransitionExecution.to_state_id == state_id),
            )
        )
        if hist_exec_res.scalar_one() > 0:
            raise ProblemException(
                status=409,
                code="HISTORICAL_EXECUTIONS_REQUIRE_STATE",
                title="Historical Executions Require State",
                detail=(
                    "Historical transition executions reference this state. "
                    "Provide a replacement state to preserve execution history."
                ),
            )

    # Perform atomic migrations BEFORE deleting state_id
    # 1. Migrate issues
    if issues and effective_replacement_id is not None:
        await session.execute(text("SELECT set_config('app.transition_exec_id', 'bypass', true)"))
        for issue in issues:
            issue.state_id = effective_replacement_id
            await record_activity(
                session,
                workspace_id=caller.workspace_id,
                object_id=issue.id,
                actor_principal_id=caller.principal_id,
                event_type=ActivityEventType.ISSUE_FIELD_CHANGED,
                payload={
                    "field": "state_id",
                    "old": str(state_id),
                    "new": str(effective_replacement_id),
                    "reason": "state_deleted",
                },
            )

    # 2. Migrate or safely clean hooks
    if effective_replacement_id is not None and migrate_hooks:
        for h in hooks:
            new_from = effective_replacement_id if h.from_state_id == state_id else h.from_state_id
            new_to = effective_replacement_id if h.to_state_id == state_id else h.to_state_id
            if new_from is not None and new_from == new_to:
                # Disabled self-loop hook removed safely
                await session.delete(h)
                continue
            h.from_state_id = new_from
            h.to_state_id = new_to
            h.manifest_sha256 = compute_hook_manifest_sha256(
                hook_kind=h.hook_kind,
                wasm_module_sha256=h.wasm_module_sha256,
                agent_definition_id=h.agent_definition_id,
                allowed_mutable_fields=h.allowed_mutable_fields,
                failure_policy=h.failure_policy,
                from_state_id=h.from_state_id,
                to_state_id=h.to_state_id,
            )
    else:
        # Clean disabled hooks safely
        for dh in disabled_hooks:
            await session.delete(dh)

    # 3. Migrate historical executions
    if effective_replacement_id is not None:
        await session.execute(
            update(WorkflowTransitionExecution)
            .where(
                WorkflowTransitionExecution.project_id == project.id,
                WorkflowTransitionExecution.from_state_id == state_id,
            )
            .values(from_state_id=effective_replacement_id)
        )
        await session.execute(
            update(WorkflowTransitionExecution)
            .where(
                WorkflowTransitionExecution.project_id == project.id,
                WorkflowTransitionExecution.to_state_id == state_id,
            )
            .values(to_state_id=effective_replacement_id)
        )

    # 4. Update saved views
    views_res = await session.execute(select(View).where(View.project_id == project.id))
    views = views_res.scalars().all()
    _update_views_for_deleted_id(views, "state_ids", state_id, effective_replacement_id)

    await session.delete(state)
    await session.flush()

    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=project.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.STATE_DELETED,
        payload={
            "state_id": str(state_id),
            "migrated_issue_count": len(issues),
            "migrate_to": str(effective_replacement_id) if effective_replacement_id else None,
        },
    )


# ---------------------------------------------------------------------------
# Project Priorities
# ---------------------------------------------------------------------------


async def list_priorities(
    session: AsyncSession,
    caller: PrincipalContext,
    project_ref: str,
) -> list[PriorityResponse]:
    """List priorities for a project ordered by sort_order."""
    project = await get_project_or_404(session, caller, project_ref)
    await require_capability(session, caller, project.id, Capability.VIEW)

    res = await session.execute(
        select(ProjectPriority)
        .where(ProjectPriority.project_id == project.id)
        .order_by(ProjectPriority.sort_order, ProjectPriority.label)
    )
    priorities = res.scalars().all()

    return [
        PriorityResponse(
            id=p.id,
            project_id=p.project_id,
            slug=p.slug,
            label=p.label,
            emoji=p.emoji,
            color_hex=p.color_hex,
            sort_order=p.sort_order,
            is_default=p.is_default,
        )
        for p in priorities
    ]


async def create_priority(
    session: AsyncSession,
    caller: PrincipalContext,
    project_ref: str,
    data: PriorityCreate,
) -> PriorityResponse:
    """Create a custom priority for a project."""
    project = await get_project_or_404(session, caller, project_ref)
    await require_capability(session, caller, project.id, Capability.ADMIN)

    existing = await session.execute(
        select(ProjectPriority.id).where(
            ProjectPriority.project_id == project.id,
            ProjectPriority.slug == data.slug,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ProblemException(
            status=409,
            code="PRIORITY_SLUG_TAKEN",
            title="Priority Slug Taken",
            detail=None,
        )

    # Setting default clears previous defaults
    if data.is_default:
        await session.execute(
            update(ProjectPriority)
            .where(ProjectPriority.project_id == project.id)
            .values(is_default=False)
        )

    new_prio = ProjectPriority(
        workspace_id=project.workspace_id,
        project_id=project.id,
        slug=data.slug,
        label=data.label,
        emoji=data.emoji,
        color_hex=data.color_hex,
        sort_order=data.sort_order,
        is_default=data.is_default,
    )
    session.add(new_prio)
    await session.flush()

    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=project.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.PRIORITY_CREATED,
        payload={
            "priority_id": str(new_prio.id),
            "slug": new_prio.slug,
            "label": new_prio.label,
            "sort_order": new_prio.sort_order,
            "is_default": new_prio.is_default,
        },
    )

    return PriorityResponse(
        id=new_prio.id,
        project_id=new_prio.project_id,
        slug=new_prio.slug,
        label=new_prio.label,
        emoji=new_prio.emoji,
        color_hex=new_prio.color_hex,
        sort_order=new_prio.sort_order,
        is_default=new_prio.is_default,
    )


async def update_priority(  # noqa: C901
    session: AsyncSession,
    caller: PrincipalContext,
    project_ref: str,
    priority_id: uuid.UUID,
    data: PriorityPatch,
) -> PriorityResponse:
    """Update mutable fields of a project priority."""
    project = await get_project_or_404(session, caller, project_ref)
    await require_capability(session, caller, project.id, Capability.ADMIN)

    res = await session.execute(
        select(ProjectPriority).where(
            ProjectPriority.project_id == project.id,
            ProjectPriority.id == priority_id,
        )
    )
    prio = res.scalar_one_or_none()
    if prio is None:
        not_found()

    if data.slug is not None and data.slug != prio.slug:
        existing = await session.execute(
            select(ProjectPriority.id).where(
                ProjectPriority.project_id == project.id,
                ProjectPriority.id != priority_id,
                ProjectPriority.slug == data.slug,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ProblemException(
                status=409,
                code="PRIORITY_SLUG_TAKEN",
                title="Priority Slug Taken",
                detail=None,
            )

    if data.is_default is True:
        await session.execute(
            update(ProjectPriority)
            .where(
                ProjectPriority.project_id == project.id,
                ProjectPriority.id != priority_id,
            )
            .values(is_default=False)
        )

    changes: dict[str, dict[str, Any]] = {}

    if data.slug is not None and data.slug != prio.slug:
        changes["slug"] = {"old": prio.slug, "new": data.slug}
        prio.slug = data.slug

    if data.label is not None and data.label != prio.label:
        changes["label"] = {"old": prio.label, "new": data.label}
        prio.label = data.label

    if (data.emoji is not None or "emoji" in data.model_fields_set) and data.emoji != prio.emoji:
        changes["emoji"] = {"old": prio.emoji, "new": data.emoji}
        prio.emoji = data.emoji

    if data.color_hex is not None and data.color_hex != prio.color_hex:
        changes["color_hex"] = {"old": prio.color_hex, "new": data.color_hex}
        prio.color_hex = data.color_hex

    if data.sort_order is not None and data.sort_order != prio.sort_order:
        changes["sort_order"] = {"old": prio.sort_order, "new": data.sort_order}
        prio.sort_order = data.sort_order

    if data.is_default is not None and data.is_default != prio.is_default:
        changes["is_default"] = {"old": prio.is_default, "new": data.is_default}
        prio.is_default = data.is_default

    await session.flush()

    if changes:
        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=project.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.PRIORITY_UPDATED,
            payload={
                "priority_id": str(prio.id),
                "changes": changes,
            },
        )

    return PriorityResponse(
        id=prio.id,
        project_id=prio.project_id,
        slug=prio.slug,
        label=prio.label,
        emoji=prio.emoji,
        color_hex=prio.color_hex,
        sort_order=prio.sort_order,
        is_default=prio.is_default,
    )


async def delete_priority(
    session: AsyncSession,
    caller: PrincipalContext,
    project_ref: str,
    priority_id: uuid.UUID,
    migrate_to: uuid.UUID | None = None,
) -> None:
    """Delete a custom priority, optionally migrating issues."""
    project = await get_project_or_404(session, caller, project_ref)
    await require_capability(session, caller, project.id, Capability.ADMIN)

    res = await session.execute(
        select(ProjectPriority).where(
            ProjectPriority.project_id == project.id,
            ProjectPriority.id == priority_id,
        )
    )
    prio = res.scalar_one_or_none()
    if prio is None:
        not_found()

    # Validate migrate_to if provided
    if migrate_to is not None:
        if migrate_to == priority_id:
            raise ProblemException(
                status=422,
                code="MIGRATE_TARGET_INVALID",
                title="Invalid Migration Target",
                detail=None,
            )
        target_res = await session.execute(
            select(ProjectPriority).where(
                ProjectPriority.project_id == project.id,
                ProjectPriority.id == migrate_to,
            )
        )
        if target_res.scalar_one_or_none() is None:
            raise ProblemException(
                status=422,
                code="MIGRATE_TARGET_INVALID",
                title="Invalid Migration Target",
                detail=None,
            )

    # Rule: cannot delete default priority
    if prio.is_default:
        raise ProblemException(
            status=409,
            code="DEFAULT_PRIORITY",
            title="Default Priority Cannot Be Deleted",
            detail=None,
        )

    issues_res = await session.execute(
        select(Issue).where(
            Issue.project_id == project.id,
            Issue.priority_id == priority_id,
        )
    )
    issues = issues_res.scalars().all()

    if issues:
        if migrate_to is None:
            raise ProblemException(
                status=409,
                code="PRIORITY_IN_USE",
                title="Priority In Use",
                detail=None,
            )
        if len(issues) > MAX_MIGRATION_ISSUES:
            raise ProblemException(
                status=409,
                code="MIGRATION_TOO_LARGE",
                title="Migration Too Large",
                detail=None,
            )

        for issue in issues:
            issue.priority_id = migrate_to
            await record_activity(
                session,
                workspace_id=caller.workspace_id,
                object_id=issue.id,
                actor_principal_id=caller.principal_id,
                event_type=ActivityEventType.ISSUE_FIELD_CHANGED,
                payload={
                    "field": "priority_id",
                    "old": str(priority_id),
                    "new": str(migrate_to),
                    "reason": "priority_deleted",
                },
            )

    await session.delete(prio)
    await session.flush()

    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=project.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.PRIORITY_DELETED,
        payload={
            "priority_id": str(priority_id),
            "migrated_issue_count": len(issues),
            "migrate_to": str(migrate_to) if migrate_to else None,
        },
    )


# ---------------------------------------------------------------------------
# Project Labels
# ---------------------------------------------------------------------------


async def list_labels(
    session: AsyncSession,
    caller: PrincipalContext,
    project_ref: str,
) -> list[LabelResponse]:
    """List labels for a project ordered by name."""
    project = await get_project_or_404(session, caller, project_ref)
    await require_capability(session, caller, project.id, Capability.VIEW)

    res = await session.execute(
        select(ProjectLabel)
        .where(ProjectLabel.project_id == project.id)
        .order_by(ProjectLabel.name)
    )
    labels = res.scalars().all()

    return [
        LabelResponse(
            id=lbl.id,
            project_id=lbl.project_id,
            name=lbl.name,
            color_hex=lbl.color_hex,
            exclusive_group=lbl.exclusive_group,
        )
        for lbl in labels
    ]


async def create_label(
    session: AsyncSession,
    caller: PrincipalContext,
    project_ref: str,
    data: LabelCreate,
) -> LabelResponse:
    """Create a project label. Requires EDIT capability (S7.2 8i instant creation)."""
    project = await get_project_or_404(session, caller, project_ref)
    await require_capability(session, caller, project.id, Capability.EDIT)

    existing = await session.execute(
        select(ProjectLabel.id).where(
            ProjectLabel.project_id == project.id,
            func.lower(ProjectLabel.name) == data.name.lower(),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ProblemException(
            status=409,
            code="LABEL_NAME_TAKEN",
            title="Label Name Taken",
            detail=None,
        )

    new_label = ProjectLabel(
        workspace_id=project.workspace_id,
        project_id=project.id,
        name=data.name,
        color_hex=data.color_hex,
        exclusive_group=data.exclusive_group,
    )
    session.add(new_label)
    await session.flush()

    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=project.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.LABEL_CREATED,
        payload={
            "label_id": str(new_label.id),
            "name": new_label.name,
            "exclusive_group": new_label.exclusive_group,
        },
    )

    return LabelResponse(
        id=new_label.id,
        project_id=new_label.project_id,
        name=new_label.name,
        color_hex=new_label.color_hex,
        exclusive_group=new_label.exclusive_group,
    )


async def update_label(
    session: AsyncSession,
    caller: PrincipalContext,
    project_ref: str,
    label_id: uuid.UUID,
    data: LabelPatch,
) -> LabelResponse:
    """Update a project label (project ADMIN only)."""
    project = await get_project_or_404(session, caller, project_ref)
    await require_capability(session, caller, project.id, Capability.ADMIN)

    res = await session.execute(
        select(ProjectLabel).where(
            ProjectLabel.project_id == project.id,
            ProjectLabel.id == label_id,
        )
    )
    label = res.scalar_one_or_none()
    if label is None:
        not_found()

    if data.name is not None and data.name.lower() != label.name.lower():
        existing = await session.execute(
            select(ProjectLabel.id).where(
                ProjectLabel.project_id == project.id,
                ProjectLabel.id != label_id,
                func.lower(ProjectLabel.name) == data.name.lower(),
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ProblemException(
                status=409,
                code="LABEL_NAME_TAKEN",
                title="Label Name Taken",
                detail=None,
            )

    changes: dict[str, dict[str, Any]] = {}

    if data.name is not None and data.name != label.name:
        changes["name"] = {"old": label.name, "new": data.name}
        label.name = data.name

    if data.color_hex is not None and data.color_hex != label.color_hex:
        changes["color_hex"] = {"old": label.color_hex, "new": data.color_hex}
        label.color_hex = data.color_hex

    if (
        data.exclusive_group is not None or "exclusive_group" in data.model_fields_set
    ) and data.exclusive_group != label.exclusive_group:
        changes["exclusive_group"] = {
            "old": label.exclusive_group,
            "new": data.exclusive_group,
        }
        label.exclusive_group = data.exclusive_group

    await session.flush()

    if changes:
        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=project.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.LABEL_UPDATED,
            payload={
                "label_id": str(label.id),
                "changes": changes,
            },
        )

    return LabelResponse(
        id=label.id,
        project_id=label.project_id,
        name=label.name,
        color_hex=label.color_hex,
        exclusive_group=label.exclusive_group,
    )


async def get_label_audit_impact(
    session: AsyncSession,
    caller: PrincipalContext,
    project_ref: str,
    label_id: uuid.UUID,
) -> LabelAuditImpactResponse:
    """Compute reverse-audit impact of deleting a project label."""
    project = await get_project_or_404(session, caller, project_ref)
    await require_capability(session, caller, project.id, Capability.ADMIN)

    res = await session.execute(
        select(ProjectLabel).where(
            ProjectLabel.project_id == project.id,
            ProjectLabel.id == label_id,
        )
    )
    label = res.scalar_one_or_none()
    if label is None:
        not_found()

    # 1. Issues count and sample keys
    issues_res = await session.execute(
        select(Issue.sequence_id)
        .join(IssueLabel, IssueLabel.issue_id == Issue.id)
        .join(ObjectRecord, ObjectRecord.id == Issue.id)
        .where(
            Issue.project_id == project.id,
            IssueLabel.label_id == label_id,
            ObjectRecord.archived_at.is_(None),
            ObjectRecord.deleted_at.is_(None),
        )
        .order_by(Issue.sequence_id.desc())
    )
    issue_seqs = issues_res.scalars().all()
    issues_count = len(issue_seqs)
    sample_issue_keys = [f"{project.identifier}-{seq}" for seq in issue_seqs[:5]]

    # 2. Saved views referencing this label
    views_res = await session.execute(select(View).where(View.project_id == project.id))
    views = views_res.scalars().all()
    saved_views = [
        SavedViewSummary(id=v.id, name=v.name)
        for v in views
        if _view_references_id(v, "label_ids", label_id)
    ]

    # 3. Blocking reasons (labels have no hard invariants blocking delete)
    blocking_reasons: list[str] = []

    # 4. Valid replacement labels
    other_labels = await list_labels(session, caller, project_ref)
    valid_replacement_labels = [lbl for lbl in other_labels if lbl.id != label_id]

    return LabelAuditImpactResponse(
        label_id=label.id,
        project_id=project.id,
        issues_count=issues_count,
        sample_issue_keys=sample_issue_keys,
        saved_views=saved_views,
        blocking_reasons=blocking_reasons,
        valid_replacement_labels=valid_replacement_labels,
    )


async def delete_label(
    session: AsyncSession,
    caller: PrincipalContext,
    project_ref: str,
    label_id: uuid.UUID,
    replacement_label_id: uuid.UUID | None = None,
) -> None:
    """Delete a project label and optionally reassign tagged issues (project ADMIN only)."""
    project = await get_project_or_404(session, caller, project_ref)
    await require_capability(session, caller, project.id, Capability.ADMIN)

    res = await session.execute(
        select(ProjectLabel).where(
            ProjectLabel.project_id == project.id,
            ProjectLabel.id == label_id,
        )
    )
    label = res.scalar_one_or_none()
    if label is None:
        not_found()

    replacement_label: ProjectLabel | None = None
    if replacement_label_id is not None:
        if replacement_label_id == label_id:
            raise ProblemException(
                status=422,
                code="MIGRATE_TARGET_INVALID",
                title="Invalid Migration Target",
                detail=None,
            )
        repl_res = await session.execute(
            select(ProjectLabel).where(
                ProjectLabel.project_id == project.id,
                ProjectLabel.id == replacement_label_id,
            )
        )
        replacement_label = repl_res.scalar_one_or_none()
        if replacement_label is None:
            raise ProblemException(
                status=422,
                code="MIGRATE_TARGET_INVALID",
                title="Invalid Migration Target",
                detail=None,
            )

    # Find issues tagged with this label
    tagged_rows = await session.execute(
        select(IssueLabel.issue_id, IssueLabel.workspace_id)
        .join(Issue, Issue.id == IssueLabel.issue_id)
        .where(
            Issue.project_id == project.id,
            IssueLabel.label_id == label_id,
        )
    )
    tagged_issues = tagged_rows.all()

    if replacement_label is not None:
        for iss_id, _ in tagged_issues:
            # 1. If issue already has replacement_label_id,
            # simply delete the old (issue_id, label_id)
            existing_repl = await session.execute(
                select(IssueLabel).where(
                    IssueLabel.issue_id == iss_id,
                    IssueLabel.label_id == replacement_label.id,
                )
            )
            if existing_repl.scalar_one_or_none() is not None:
                await session.execute(
                    delete(IssueLabel).where(
                        IssueLabel.issue_id == iss_id,
                        IssueLabel.label_id == label_id,
                    )
                )
                continue

            # 2. If replacement_label has exclusive_group,
            # delete any conflicting label in that group on this issue
            if replacement_label.exclusive_group:
                conflict_rows = await session.execute(
                    select(IssueLabel.label_id)
                    .join(ProjectLabel, ProjectLabel.id == IssueLabel.label_id)
                    .where(
                        IssueLabel.issue_id == iss_id,
                        ProjectLabel.project_id == project.id,
                        ProjectLabel.exclusive_group == replacement_label.exclusive_group,
                        IssueLabel.label_id != label_id,
                    )
                )
                conflict_label_ids = conflict_rows.scalars().all()
                if conflict_label_ids:
                    await session.execute(
                        delete(IssueLabel).where(
                            IssueLabel.issue_id == iss_id,
                            IssueLabel.label_id.in_(conflict_label_ids),
                        )
                    )

            # 3. Update the IssueLabel to replacement_label.id
            await session.execute(
                update(IssueLabel)
                .where(
                    IssueLabel.issue_id == iss_id,
                    IssueLabel.label_id == label_id,
                )
                .values(label_id=replacement_label.id)
            )
    else:
        # Detach label from all issues in this project
        await session.execute(delete(IssueLabel).where(IssueLabel.label_id == label_id))

    # Saved views update
    views_res = await session.execute(select(View).where(View.project_id == project.id))
    views = views_res.scalars().all()
    _update_views_for_deleted_id(views, "label_ids", label_id, replacement_label_id)

    await session.delete(label)
    await session.flush()

    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=project.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.LABEL_DELETED,
        payload={
            "label_id": str(label_id),
            "name": label.name,
            "reassigned_to": str(replacement_label_id) if replacement_label_id else None,
            "reassigned_issue_count": len(tagged_issues) if replacement_label_id else 0,
        },
    )
