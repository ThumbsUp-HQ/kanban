"""Filter DSL compiler and validation rules for saved views and issue queries (S6.4, S3.4)."""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import exists, func, literal, or_, select, text
from sqlalchemy.orm import aliased

from database.models import (
    Cycle,
    Issue,
    IssueAssignee,
    IssueLabel,
    IssueModule,
    ObjectLink,
    ObjectRecord,
    Project,
    WorkflowState,
)
from kanban.api.problems import ProblemException
from kanban.api.v1.schemas.views import FilterSpec, GateStatus, GroupAxis, LabelMatch

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def validate_group_axes(
    project: Project,
    group_by: str | GroupAxis | None,
    sub_group_by: str | GroupAxis | None,
    filters: FilterSpec | None = None,
) -> None:
    """Validate grouping axes uniqueness and project feature gates."""
    gb = str(group_by.value if isinstance(group_by, GroupAxis) else (group_by or "none")).lower()
    sgb = str(
        sub_group_by.value if isinstance(sub_group_by, GroupAxis) else (sub_group_by or "none")
    ).lower()

    if sgb != "none" and sgb == gb:
        raise ProblemException(
            code="DUPLICATE_GROUP_AXIS",
            status=422,
            title="Duplicate Group Axis",
            detail="sub_group_by cannot match group_by unless both are none",
        )

    if not project.modules_enabled:
        if gb == "module" or sgb == "module":
            raise ProblemException(
                code="MODULES_DISABLED",
                status=422,
                title="Modules Disabled",
                detail="Modules feature is disabled on this project",
            )
        if filters is not None and filters.module_ids:
            raise ProblemException(
                code="MODULES_DISABLED",
                status=422,
                title="Modules Disabled",
                detail="Modules feature is disabled on this project",
            )


def _compile_state_predicates(project: Project, filters: FilterSpec) -> list[Any]:
    """Compile state and priority filter conditions."""
    predicates: list[Any] = []
    if filters.state_ids:
        predicates.append(Issue.state_id.in_(filters.state_ids))

    if filters.state_groups:
        predicates.append(
            Issue.state_id.in_(
                select(WorkflowState.id).where(
                    WorkflowState.project_id == project.id,
                    WorkflowState.state_group.in_(filters.state_groups),
                )
            )
        )

    if filters.priority_ids:
        predicates.append(Issue.priority_id.in_(filters.priority_ids))

    if filters.overdue_only:
        predicates.append(Issue.due_date < func.current_date())
        predicates.append(
            Issue.state_id.in_(
                select(WorkflowState.id).where(
                    WorkflowState.project_id == project.id,
                    WorkflowState.state_group.notin_(["completed", "cancelled"]),
                )
            )
        )
    return predicates


def _compile_assignee_predicates(filters: FilterSpec, caller_principal_id: uuid.UUID) -> list[Any]:
    """Compile assignee filter conditions."""
    predicates: list[Any] = []
    if filters.assignee_ids:
        assignee_clauses: list[Any] = []
        for a_id in filters.assignee_ids:
            clean = a_id.strip().lower()
            if clean == "me":
                assignee_clauses.append(
                    exists().where(
                        IssueAssignee.issue_id == Issue.id,
                        IssueAssignee.principal_id == caller_principal_id,
                    )
                )
            elif clean == "unassigned":
                assignee_clauses.append(~exists().where(IssueAssignee.issue_id == Issue.id))
            else:
                try:
                    p_uuid = uuid.UUID(a_id)
                    assignee_clauses.append(
                        exists().where(
                            IssueAssignee.issue_id == Issue.id,
                            IssueAssignee.principal_id == p_uuid,
                        )
                    )
                except ValueError:
                    pass
        if assignee_clauses:
            predicates.append(or_(*assignee_clauses))

    if filters.has_free_text_assignee is True:
        predicates.append(
            exists().where(
                IssueAssignee.issue_id == Issue.id,
                IssueAssignee.free_text_assignee.isnot(None),
                IssueAssignee.free_text_assignee != "",
            )
        )
    elif filters.has_free_text_assignee is False:
        predicates.append(
            ~exists().where(
                IssueAssignee.issue_id == Issue.id,
                IssueAssignee.free_text_assignee.isnot(None),
                IssueAssignee.free_text_assignee != "",
            )
        )
    return predicates


def _compile_labels_predicates(filters: FilterSpec) -> list[Any]:
    """Compile label match predicates."""
    if not filters.label_ids:
        return []
    if filters.label_match == LabelMatch.ALL:
        return [
            exists().where(
                IssueLabel.issue_id == Issue.id,
                IssueLabel.label_id == lbl_id,
            )
            for lbl_id in filters.label_ids
        ]
    return [
        exists().where(
            IssueLabel.issue_id == Issue.id,
            IssueLabel.label_id.in_(filters.label_ids),
        )
    ]


def _compile_cycle_predicates(project: Project, filters: FilterSpec) -> list[Any]:
    """Compile cycle filter predicates."""
    if not filters.cycle_ids:
        return []
    cycle_clauses: list[Any] = []
    for c_id in filters.cycle_ids:
        clean = c_id.strip().lower()
        if clean == "none":
            cycle_clauses.append(Issue.cycle_id.is_(None))
        elif clean == "active":
            cycle_clauses.append(
                Issue.cycle_id.in_(
                    select(Cycle.id).where(
                        Cycle.project_id == project.id,
                        Cycle.status == "active",
                    )
                )
            )
        else:
            try:
                c_uuid = uuid.UUID(c_id)
                cycle_clauses.append(Issue.cycle_id == c_uuid)
            except ValueError:
                pass
    return [or_(*cycle_clauses)] if cycle_clauses else []


def _compile_module_parent_predicates(filters: FilterSpec) -> list[Any]:
    """Compile module and parent issue predicates."""
    predicates: list[Any] = []
    if filters.module_ids:
        module_clauses: list[Any] = []
        for m_id in filters.module_ids:
            clean = m_id.strip().lower()
            if clean == "none":
                module_clauses.append(~exists().where(IssueModule.issue_id == Issue.id))
            else:
                try:
                    m_uuid = uuid.UUID(m_id)
                    module_clauses.append(
                        exists().where(
                            IssueModule.issue_id == Issue.id,
                            IssueModule.module_id == m_uuid,
                        )
                    )
                except ValueError:
                    pass
        if module_clauses:
            predicates.append(or_(*module_clauses))

    if filters.parent_issue_id is not None:
        clean = filters.parent_issue_id.strip().lower()
        if clean in ("null", "none"):
            predicates.append(Issue.parent_issue_id.is_(None))
        else:
            try:
                p_uuid = uuid.UUID(filters.parent_issue_id)
                predicates.append(Issue.parent_issue_id == p_uuid)
            except ValueError:
                pass
    return predicates


def _compile_dates_predicates(filters: FilterSpec) -> list[Any]:
    """Compile start and due date bounds."""
    predicates: list[Any] = []
    if filters.start_date_from:
        predicates.append(Issue.start_date >= filters.start_date_from)
    if filters.start_date_to:
        predicates.append(Issue.start_date <= filters.start_date_to)
    if filters.due_date_from:
        predicates.append(Issue.due_date >= filters.due_date_from)
    if filters.due_date_to:
        predicates.append(Issue.due_date <= filters.due_date_to)
    return predicates


def _compile_blocked_predicate(filters: FilterSpec) -> list[Any]:
    """Compile blocked dependency predicate."""
    if filters.blocked is None:
        return []
    blocker_issue = aliased(Issue, name="blocker_issue")
    blocker_state = aliased(WorkflowState, name="blocker_state")
    blocks_pred = exists().where(
        ObjectLink.target_id == Issue.id,
        ObjectLink.link_type == "BLOCKS",
        ObjectLink.link_state == "ACTIVE",
        ObjectLink.source_id == blocker_issue.id,
        blocker_issue.state_id == blocker_state.id,
        blocker_state.state_group.notin_(["completed", "cancelled"]),
    )
    blocked_by_pred = exists().where(
        ObjectLink.source_id == Issue.id,
        ObjectLink.link_type == "BLOCKED_BY",
        ObjectLink.link_state == "ACTIVE",
        ObjectLink.target_id == blocker_issue.id,
        blocker_issue.state_id == blocker_state.id,
        blocker_state.state_group.notin_(["completed", "cancelled"]),
    )
    is_blocked = or_(blocks_pred, blocked_by_pred)
    return [is_blocked if filters.blocked else ~is_blocked]


def _compile_search_gate_predicates(filters: FilterSpec) -> list[Any]:
    """Compile search and gate status predicates."""
    predicates: list[Any] = []
    if filters.gate_status is not None:
        if filters.gate_status == GateStatus.PENDING:
            predicates.append(Issue.pending_transition_exec_id.isnot(None))
        else:
            predicates.append(literal(1) == 0)

    if filters.search_query:
        clean_q = filters.search_query.strip()
        if clean_q:
            predicates.append(
                text("issues.search_tsv @@ websearch_to_tsquery('simple', :q)").bindparams(
                    q=clean_q
                )
            )
    return predicates


def compile_issue_filter_predicates(
    session: AsyncSession,
    project: Project | None,
    filters: FilterSpec,
    caller_principal_id: uuid.UUID,
) -> list[Any]:
    """Compile a FilterSpec DSL into a list of SQLAlchemy filter predicates."""
    _ = session
    if project is not None:
        validate_group_axes(project, None, None, filters)

    obj_alias = aliased(ObjectRecord, name="issue_object")
    archived_clause = (
        obj_alias.archived_at.is_(None) if not filters.include_archived else (literal(1) == 1)
    )

    predicates: list[Any] = [
        exists().where(
            obj_alias.id == Issue.id,
            obj_alias.deleted_at.is_(None),
            archived_clause,
        ),
    ]

    if project is not None:
        predicates.append(Issue.project_id == project.id)
        predicates.extend(_compile_state_predicates(project, filters))
        predicates.extend(_compile_cycle_predicates(project, filters))
    else:
        if filters.state_ids:
            predicates.append(Issue.state_id.in_(filters.state_ids))
        if filters.priority_ids:
            predicates.append(Issue.priority_id.in_(filters.priority_ids))

    predicates.extend(_compile_assignee_predicates(filters, caller_principal_id))
    predicates.extend(_compile_labels_predicates(filters))
    predicates.extend(_compile_module_parent_predicates(filters))
    predicates.extend(_compile_dates_predicates(filters))
    predicates.extend(_compile_blocked_predicate(filters))
    predicates.extend(_compile_search_gate_predicates(filters))

    return predicates
